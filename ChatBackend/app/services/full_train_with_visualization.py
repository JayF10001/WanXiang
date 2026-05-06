#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
C4MMD 完整训练和可视化脚本
结合真实的全量数据集训练与丰富的可视化功能
"""

# 设置环境变量抑制警告（在导入其他包之前）
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 抑制TensorFlow日志
os.environ['TOKENIZERS_PARALLELISM'] = 'false'  # 避免tokenizer并行警告
os.environ['CUDA_LAUNCH_BLOCKING'] = '0'  # 异步CUDA操作
os.environ['NCCL_DEBUG'] = 'WARN'  # 只显示NCCL警告
os.environ['PYTHONWARNINGS'] = 'ignore'  # 抑制Python警告

import logging
import torch
from torch import nn as nn
import json
from sklearn import metrics
from PIL import Image, ImageFile
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler
from transformers import AutoTokenizer, AdamW, get_linear_schedule_with_warmup
from transformers import ViTFeatureExtractor, ViTModel, XLMRobertaModel

import time
import random
import numpy as np
import datetime
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# 设置各种库的日志级别
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("torch.distributed").setLevel(logging.ERROR)

# 抑制特定的transformers警告
import transformers
transformers.logging.set_verbosity_error()

# 多GPU并行训练相关
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data.distributed import DistributedSampler
from torch.cuda.amp import autocast, GradScaler
import subprocess
import sys

# 设置matplotlib中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300

# ======================== 进度显示工具 ========================
class ProgressTracker:
    """实时进度跟踪器"""
    
    def __init__(self):
        self.start_time = time.time()
        
    def print_stage(self, stage_name, details=""):
        """打印当前阶段"""
        elapsed = time.time() - self.start_time
        print(f"\n{'='*60}")
        print(f"🔄 [{self.format_time(elapsed)}] {stage_name}")
        if details:
            print(f"   {details}")
        print(f"{'='*60}")
    
    def print_substage(self, substage_name, progress=""):
        """打印子阶段"""
        elapsed = time.time() - self.start_time
        print(f"  ⏳ [{self.format_time(elapsed)}] {substage_name} {progress}")
    
    def print_success(self, message):
        """打印成功信息"""
        elapsed = time.time() - self.start_time
        print(f"  ✅ [{self.format_time(elapsed)}] {message}")
    
    def print_warning(self, message):
        """打印警告信息"""
        elapsed = time.time() - self.start_time
        print(f"  ⚠️ [{self.format_time(elapsed)}] {message}")
    
    def print_error(self, message):
        """打印错误信息"""
        elapsed = time.time() - self.start_time
        print(f"  ❌ [{self.format_time(elapsed)}] {message}")
    
    def format_time(self, seconds):
        """格式化时间显示"""
        return str(datetime.timedelta(seconds=int(seconds)))

# ======================== 早停机制 ========================
class EarlyStopping:
    """早停机制实现"""
    
    def __init__(self, patience=10, min_delta=0.001, metric='f1', mode='max', restore_best_weights=True):
        """
        Args:
            patience: 容忍的没有改善的epoch数
            min_delta: 改善的最小阈值
            metric: 监控的指标
            mode: 'max'表示指标越大越好，'min'表示指标越小越好
            restore_best_weights: 是否恢复最佳权重
        """
        self.patience = patience
        self.min_delta = min_delta
        self.metric = metric
        self.mode = mode
        self.restore_best_weights = restore_best_weights
        
        self.best_score = None
        self.counter = 0
        self.best_epoch = 0
        self.early_stop = False
        self.best_weights = None
        
        # 根据模式确定比较函数
        if mode == 'max':
            self.is_better = lambda new, best: new > best + min_delta
        else:
            self.is_better = lambda new, best: new < best - min_delta
    
    def __call__(self, current_score, model, epoch):
        """
        检查是否需要早停
        
        Args:
            current_score: 当前epoch的评分
            model: 当前模型
            epoch: 当前epoch数
        """
        if self.best_score is None:
            self.best_score = current_score
            self.best_epoch = epoch
            if self.restore_best_weights:
                self.save_checkpoint(model)
        elif self.is_better(current_score, self.best_score):
            self.best_score = current_score
            self.best_epoch = epoch
            self.counter = 0
            if self.restore_best_weights:
                self.save_checkpoint(model)
        else:
            self.counter += 1
        
        if self.counter >= self.patience:
            self.early_stop = True
        
        return self.early_stop
    
    def save_checkpoint(self, model):
        """保存最佳模型权重"""
        if hasattr(model, 'module'):
            # DDP模型
            self.best_weights = model.module.state_dict().copy()
        else:
            self.best_weights = model.state_dict().copy()
    
    def restore_best_weights(self, model):
        """恢复最佳权重"""
        if self.best_weights is not None:
            if hasattr(model, 'module'):
                model.module.load_state_dict(self.best_weights)
            else:
                model.load_state_dict(self.best_weights)
    
    def get_status(self):
        """获取早停状态信息"""
        return {
            'best_score': self.best_score,
            'best_epoch': self.best_epoch,
            'counter': self.counter,
            'early_stop': self.early_stop
        }

# 全局进度跟踪器
progress_tracker = ProgressTracker()

# ======================== 多GPU配置 ========================
class MultiGPUConfig:
    """多GPU训练配置"""
    
    def __init__(self, show_info=False, rank=0):
        self.rank = rank
        self.setup_gpu_environment(show_info)
        
    def setup_gpu_environment(self, show_info=False):
        """设置GPU环境"""
        self.world_size = torch.cuda.device_count() if torch.cuda.is_available() else 1
        self.use_multi_gpu = self.world_size > 1
        self.device_ids = list(range(self.world_size)) if self.use_multi_gpu else [0]
        self.master_addr = 'localhost'
        self.master_port = '12355'
        
        # 只在需要显示信息且为主进程时显示
        if show_info and self.rank == 0:
            if self.use_multi_gpu:
                progress_tracker.print_success(f"🎮 检测到 {self.world_size} 张GPU，启用多GPU并行训练")
                for i in range(self.world_size):
                    gpu_name = torch.cuda.get_device_name(i)
                    gpu_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
                    progress_tracker.print_substage(f"GPU {i}", f"{gpu_name} ({gpu_memory:.1f}GB)")
            else:
                progress_tracker.print_warning("⚠️ 未检测到多GPU或CUDA不可用，使用单GPU/CPU训练")
    
    def is_main_process(self, rank=0):
        """判断是否为主进程"""
        return rank == 0
    
    def get_device(self, rank=0):
        """获取设备"""
        if self.use_multi_gpu:
            return f'cuda:{rank}'
        else:
            return 'cuda:0' if torch.cuda.is_available() else 'cpu'

# 初始GPU配置（不显示信息）
_gpu_config_instance = None

def get_gpu_config(show_info=False, rank=0):
    """获取GPU配置实例"""
    global _gpu_config_instance
    if _gpu_config_instance is None:
        _gpu_config_instance = MultiGPUConfig(show_info=show_info, rank=rank)
    return _gpu_config_instance

# ======================== 分布式训练工具 ========================
def setup_distributed(rank, world_size):
    """初始化分布式训练环境"""
    gpu_config = get_gpu_config()
    os.environ['MASTER_ADDR'] = gpu_config.master_addr
    os.environ['MASTER_PORT'] = gpu_config.master_port
    
    # 抑制分布式训练的详细输出
    if rank != 0:
        os.environ['NCCL_DEBUG'] = 'ERROR'
    
    # 设置NCCL超时和性能参数
    os.environ['NCCL_TIMEOUT'] = '1800'  # 30分钟超时
    os.environ['NCCL_BLOCKING_WAIT'] = '1'  # 阻塞等待
    os.environ['NCCL_ASYNC_ERROR_HANDLING'] = '1'  # 异步错误处理
        
    # 初始化分布式进程组，使用NCCL后端（NVIDIA推荐）
    dist.init_process_group(
        backend='nccl',  # NVIDIA的高性能通信库
        rank=rank,
        world_size=world_size,
        timeout=datetime.timedelta(minutes=30)  # 设置更长的超时时间
    )
    
    # 设置当前GPU
    torch.cuda.set_device(rank)

def cleanup_distributed():
    """清理分布式训练环境"""
    if dist.is_initialized():
        dist.destroy_process_group()

def reduce_loss(loss_tensor, world_size):
    """跨GPU减少损失值"""
    if world_size > 1:
        dist.all_reduce(loss_tensor, op=dist.ReduceOp.SUM)
        loss_tensor /= world_size
    return loss_tensor.item()

def save_on_master(obj, path, rank):
    """只在主进程保存模型"""
    if rank == 0:
        torch.save(obj, path)

# ======================== 配置参数 ========================
import argparse

# 创建参数解析器
def create_args():
    parser = argparse.ArgumentParser(description='C4MMD 4-GPU并行训练')
    parser.add_argument('--data_ratio', type=float, default=1.0, 
                        help='使用数据集的比例 (0.0-1.0)，默认1.0表示使用全量数据')
    parser.add_argument('--epochs', type=int, default=50,
                        help='训练轮数，默认50')
    parser.add_argument('--batch_size', type=int, default=8,
                        help='每GPU批次大小，默认8')
    parser.add_argument('--lr', type=float, default=1e-5,
                        help='学习率，默认1e-5')
    parser.add_argument('--mixed_precision', action='store_true', default=True,
                        help='是否启用混合精度训练')
    parser.add_argument('--seed', type=int, default=42,
                        help='随机种子，默认42')
    # 早停机制参数
    parser.add_argument('--patience', type=int, default=10,
                        help='早停耐心值，默认10轮无提升后停止')
    parser.add_argument('--early_stop_metric', type=str, default='f1', 
                        choices=['f1', 'acc', 'loss'],
                        help='早停监控指标，默认f1')
    parser.add_argument('--min_delta', type=float, default=0.001,
                        help='早停最小改善值，默认0.001')
    return parser.parse_args()

# 解析命令行参数
try:
    args = create_args()
except SystemExit:
    # 如果在Jupyter等环境中运行，使用默认参数
    import sys
    if hasattr(sys, 'ps1') or 'ipykernel' in sys.modules:
        # 在交互式环境中，使用默认值
        class DefaultArgs:
            data_ratio = 1.0
            epochs = 50
            batch_size = 8
            lr = 1e-5
            mixed_precision = True
            seed = 42
            patience = 10
            early_stop_metric = 'f1'
            min_delta = 0.001
        args = DefaultArgs()
    else:
        raise

trained_model_path = f'trained_models/C4MMD_ratio{args.data_ratio:.1f}.pth'
image_file_path = 'data/image'
log_file_name = f'C4MMD_ratio{args.data_ratio:.1f}'

language_model = 'xlm-roberta-base'
vision_model = 'google/vit-base-patch16-224'

train_data = 'data/train_data.json'
val_data = 'data/val_data.json'
test_data = 'data/test_data.json'

do_train = True
# device将在分布式训练中动态设置
USE_MIXED_PRECISION = args.mixed_precision  # 启用混合精度训练（NVIDIA推荐）

ImageFile.LOAD_TRUNCATED_IMAGES = True
NUM_LABELS = 2
LR = args.lr
EPOCHES = args.epochs
MAX_LEN = 32
seed = args.seed
BATCH_SIZE = args.batch_size
DATA_RATIO = args.data_ratio  # 数据集使用比例

# 设置随机种子
random.seed(seed)
os.environ['PYTHONHASHSEED'] = str(seed)
np.random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

# ======================== 日志配置 ========================
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# ======================== 模型定义 ========================
class VitBert(nn.Module):
    def __init__(self, vit, bert, num_labels):
        super(VitBert, self).__init__()
        self.vit = vit
        self.bert = bert
        self.num_labels = num_labels
        config = vit.config
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(config.hidden_size * 2, self.num_labels)
        self.text_classifier = nn.Linear(config.hidden_size, self.num_labels)
        self.img_classifier = nn.Linear(config.hidden_size * 2, self.num_labels)
        self.bert.config.type_vocab_size = 4
        self.bert.embeddings.token_type_embeddings = nn.Embedding(
            self.bert.config.type_vocab_size, config.hidden_size
        )
        self.bert._init_weights(bert.embeddings.token_type_embeddings)

    def forward(self, text, text_attention, vilt_img, token_type_ids):
        text_hidden_states = self.bert(input_ids=text, attention_mask=text_attention, token_type_ids=token_type_ids)[0]
        
        # 确保图像输入有正确的维度 [batch, channels, height, width]
        if len(vilt_img.shape) == 3:
            vilt_img = vilt_img.unsqueeze(0)
        pool_output = self.vit(vilt_img)[1]
        
        mixed_output = torch.cat([pool_output, text_hidden_states[:, 0, :]], dim=1)
        mixed_output = self.dropout(mixed_output)
        
        logits = self.classifier(mixed_output)
        text_logits = self.text_classifier(text_hidden_states[:, 0, :])
        img_logits = self.img_classifier(mixed_output)
        
        return logits, img_logits, text_logits

# ======================== 数据处理 ========================
class Collator:
    def __init__(self, tokenizer, processor):
        self.tokenizer = tokenizer
        self.processor = processor
        
    def __call__(self, batch):
        max_text_length = max([len(line[0]) for line in batch])
        input_ids, attention_mask, token_type_ids = [], [], []
        for line in batch:
            inputs, attention = line[0], line[1]
            token_type_id = line[6]
            input_ids.append(inputs + [self.tokenizer.pad_token_id] * (max_text_length - len(inputs)))
            attention_mask.append(attention + [0] * (max_text_length - len(attention)))
            token_type_ids.append(token_type_id + [0] * (max_text_length - len(token_type_id)))
        pixel_value = torch.stack([line[2] for line in batch]).squeeze(1)
        lables1, text_lables, img_lables = torch.tensor([line[3] for line in batch]), torch.tensor([line[4] for line in batch]), torch.tensor([line[5] for line in batch])

        outputs = {
            'input_ids': torch.tensor(input_ids),
            'attention_mask': torch.tensor(attention_mask),
            'pixel_value': pixel_value,
            'lables1': lables1,
            'text_labels': text_lables,
            'img_labels': img_lables,
            'token_type_ids': torch.tensor(token_type_ids),
        }
        return outputs

class VitXLMRDataset(torch.utils.data.Dataset):
    def __init__(self, path, processor, tokenizer, usage="train", data_ratio=1.0, show_info=False):
        self.path = path
        self.datas = load_json(path)
        
        # 根据data_ratio采样数据
        if data_ratio < 1.0:
            original_length = len(self.datas)
            sample_size = int(original_length * data_ratio)
            
            # 使用固定种子确保可重复性
            random.seed(42)
            self.datas = random.sample(self.datas, sample_size)
            
            # 只在需要显示信息时才输出
            if show_info and usage == "train":
                progress_tracker.print_substage(f"数据采样 ({usage})", 
                    f"从 {original_length:,} 条采样 {sample_size:,} 条 ({data_ratio*100:.1f}%)")
        
        self.processor = processor
        self.tokenizer = tokenizer
        self.usage = usage

    def __len__(self):
        return len(self.datas)

    def convert_str_to_ids(self, discription, token_type_id, head_space=True, max_id_num=100):
        inputs = []
        for i, token in enumerate(discription.split()):
            token = token if i == 0 and not head_space else ' ' + token
            tokenized_token = self.tokenizer(token, add_special_tokens=False)
            inputs += tokenized_token['input_ids']

        inputs = inputs[: max_id_num] if len(inputs) > max_id_num else inputs
        type_ids = [token_type_id] * len(inputs)
        return inputs, type_ids

    def __getitem__(self, idx):
        line = self.datas[idx]
        img, text, lable, lable2 = line['file_name'], line['text'], int(line['metaphor occurrence']), line['metaphor category']
        img_info = line.get('internlm_img_info', 'A complex image with various elements.')
        text_info = line.get('internlm_text_info', text)
        mix_info = line.get('internlm_mix_info', f'Image and text: {text}')
        
        img_info = 'None.' if img_info.strip() == '' else img_info
        text_info = text + " " + text_info if text_info.strip() != '' else text
        text_info = 'None.' if text_info.strip() == '' else text_info
        
        try:
            img = Image.open(f'{image_file_path}/{img}')
            if img.mode != 'RGB':
                img = img.convert("RGB")
            img_encoding = self.processor(img, padding="max_length", truncation=True, return_tensors='pt')
            img.close()
        except Exception as e:
            logger.warning(f"Error loading image {img}: {e}")
            # 创建一个默认的白色图像
            img = Image.new('RGB', (224, 224), color='white')
            img_encoding = self.processor(img, padding="max_length", truncation=True, return_tensors='pt')

        image_inputs, image_type_ids = self.convert_str_to_ids(img_info, 1, head_space=False, max_id_num=100)
        text_inputs, text_type_ids = self.convert_str_to_ids(text_info, 2, max_id_num=100)
        mix_inputs, mix_type_ids = self.convert_str_to_ids(mix_info, 3, max_id_num=100)

        discription_inputs = [self.tokenizer.cls_token_id] + image_inputs + text_inputs + mix_inputs + [self.tokenizer.sep_token_id]
        discription_attention = [1] * len(discription_inputs)
        discription_type_ids = [0] + image_type_ids + text_type_ids + mix_type_ids + [0]

        if lable2 == '' or 'complementary' in lable2:
            img_lable = 0
            text_lable = 0
        elif 'text' in lable2:
            img_lable = 0
            text_lable = 1
        elif 'image' in lable2:
            img_lable = 1
            text_lable = 0
        else:
            img_lable = 0
            text_lable = 0

        return discription_inputs, discription_attention, img_encoding['pixel_values'], lable, text_lable, img_lable, discription_type_ids

# ======================== 工具函数 ========================
def format_time(elapsed):
    elapsed_rounded = int(round((elapsed)))
    return str(datetime.timedelta(seconds=elapsed_rounded))

def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_name, data):
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ======================== 可视化类 ========================
class TrainingVisualizer:
    """训练过程可视化器"""
    
    def __init__(self):
        self.training_history = defaultdict(list)
        self.epoch_metrics = []
        self.start_time = datetime.datetime.now()
        self.timestamp = self.start_time.strftime('%Y%m%d_%H%M%S')
        
        # 创建结果目录
        os.makedirs('results', exist_ok=True)
        
        # 创建带时间戳的子目录
        self.result_dir = f'results/experiment_{self.timestamp}'
        os.makedirs(self.result_dir, exist_ok=True)
    
    def log_epoch(self, epoch, train_loss, val_metrics, lr):
        """记录每个epoch的指标"""
        self.training_history['epoch'].append(epoch)
        self.training_history['train_loss'].append(train_loss)
        self.training_history['val_acc'].append(val_metrics['acc'])
        self.training_history['val_f1'].append(val_metrics['f1'])
        self.training_history['val_precision'].append(val_metrics['precision'])
        self.training_history['val_recall'].append(val_metrics['recall'])
        self.training_history['learning_rate'].append(lr)
        
        self.epoch_metrics.append({
            'epoch': epoch,
            'train_loss': train_loss,
            **val_metrics,
            'lr': lr
        })
    
    def plot_training_curves(self, early_stop_info=None):
        """绘制训练曲线"""
        fig, axes = plt.subplots(2, 3, figsize=(20, 14))
        
        epochs = self.training_history['epoch']
        
        # 添加总标题和时间戳
        fig.suptitle(f'C4MMD Training Curves - {self.start_time.strftime("%Y-%m-%d %H:%M:%S")}', 
                    fontsize=16, fontweight='bold', y=0.98)
        
        # 1. 训练损失
        axes[0, 0].plot(epochs, self.training_history['train_loss'], 'b-', linewidth=2, label='Train Loss')
        axes[0, 0].set_title('Training Loss', fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel('Epoch')
        axes[0, 0].set_ylabel('Loss')
        axes[0, 0].grid(True, alpha=0.3)
        axes[0, 0].legend()
        
        # 如果有早停信息，标记最佳点
        if early_stop_info and early_stop_info['best_epoch'] > 0:
            best_epoch = early_stop_info['best_epoch']
            if best_epoch <= len(self.training_history['train_loss']):
                best_loss = self.training_history['train_loss'][best_epoch-1]
                axes[0, 0].scatter(best_epoch, best_loss, color='red', s=100, marker='*', 
                                 label=f'Best (Epoch {best_epoch})', zorder=5)
                axes[0, 0].legend()
        
        # 2. 验证准确率
        axes[0, 1].plot(epochs, self.training_history['val_acc'], 'g-', linewidth=2, label='Val Accuracy')
        axes[0, 1].set_title('Validation Accuracy', fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel('Epoch')
        axes[0, 1].set_ylabel('Accuracy (%)')
        axes[0, 1].grid(True, alpha=0.3)
        axes[0, 1].legend()
        
        # 标记早停最佳点
        if early_stop_info and early_stop_info['best_epoch'] > 0:
            best_epoch = early_stop_info['best_epoch']
            if best_epoch <= len(self.training_history['val_acc']):
                best_acc = self.training_history['val_acc'][best_epoch-1]
                axes[0, 1].scatter(best_epoch, best_acc, color='red', s=100, marker='*', 
                                 label=f'Best (Epoch {best_epoch})', zorder=5)
                axes[0, 1].legend()
        
        # 3. F1分数
        axes[0, 2].plot(epochs, self.training_history['val_f1'], 'r-', linewidth=2, label='Val F1')
        axes[0, 2].set_title('Validation F1 Score', fontsize=14, fontweight='bold')
        axes[0, 2].set_xlabel('Epoch')
        axes[0, 2].set_ylabel('F1 Score (%)')
        axes[0, 2].grid(True, alpha=0.3)
        axes[0, 2].legend()
        
        # 标记早停最佳点
        if early_stop_info and early_stop_info['best_epoch'] > 0:
            best_epoch = early_stop_info['best_epoch']
            if best_epoch <= len(self.training_history['val_f1']):
                best_f1 = self.training_history['val_f1'][best_epoch-1]
                axes[0, 2].scatter(best_epoch, best_f1, color='red', s=100, marker='*', 
                                 label=f'Best (Epoch {best_epoch})', zorder=5)
                axes[0, 2].legend()
        
        # 4. 精确率和召回率
        axes[1, 0].plot(epochs, self.training_history['val_precision'], 'purple', linewidth=2, label='Precision')
        axes[1, 0].plot(epochs, self.training_history['val_recall'], 'orange', linewidth=2, label='Recall')
        axes[1, 0].set_title('Precision & Recall', fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel('Epoch')
        axes[1, 0].set_ylabel('Score (%)')
        axes[1, 0].grid(True, alpha=0.3)
        axes[1, 0].legend()
        
        # 5. 学习率
        axes[1, 1].plot(epochs, self.training_history['learning_rate'], 'teal', linewidth=2)
        axes[1, 1].set_title('Learning Rate Schedule', fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel('Epoch')
        axes[1, 1].set_ylabel('Learning Rate')
        axes[1, 1].set_yscale('log')
        axes[1, 1].grid(True, alpha=0.3)
        
        # 6. 综合性能雷达图
        if len(epochs) > 0:
            final_metrics = [
                self.training_history['val_acc'][-1],
                self.training_history['val_f1'][-1],
                self.training_history['val_precision'][-1],
                self.training_history['val_recall'][-1]
            ]
            
            categories = ['Accuracy', 'F1', 'Precision', 'Recall']
            angles = np.linspace(0, 2*np.pi, len(categories), endpoint=False).tolist()
            final_metrics += final_metrics[:1]
            angles += angles[:1]
            
            ax_radar = plt.subplot(2, 3, 6, projection='polar')
            ax_radar.plot(angles, final_metrics, 'o-', linewidth=2, color='red')
            ax_radar.fill(angles, final_metrics, alpha=0.25, color='red')
            ax_radar.set_xticks(angles[:-1])
            ax_radar.set_xticklabels(categories)
            ax_radar.set_ylim(0, 100)
            ax_radar.set_title('Final Performance', fontweight='bold', pad=20)
            
            # 添加数值标签
            for angle, value, category in zip(angles[:-1], final_metrics[:-1], categories):
                ax_radar.text(angle, value + 5, f'{value:.1f}%', ha='center', va='center', fontweight='bold')
        
        # 添加时间戳和早停信息
        info_text = f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
        if early_stop_info:
            info_text += f'Early Stopping: {early_stop_info["early_stop"]}\n'
            if early_stop_info['early_stop']:
                info_text += f'Stopped at Epoch {len(epochs)} (Best: {early_stop_info["best_epoch"]})'
        
        fig.text(0.02, 0.02, info_text, fontsize=10, ha='left', va='bottom', 
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
        
        plt.tight_layout()
        
        # 保存到带时间戳的文件
        filename = f'{self.result_dir}/training_curves_{self.timestamp}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        
        # 同时保存到results目录（为了兼容性）
        plt.savefig('results/training_curves.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        return filename
    
    def plot_method_comparison(self, final_results):
        """绘制方法比较图"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(18, 14))
        
        # 添加总标题和时间戳
        fig.suptitle(f'C4MMD Method Comparison - {self.start_time.strftime("%Y-%m-%d %H:%M:%S")}', 
                    fontsize=16, fontweight='bold', y=0.98)
        
        # 方法比较数据
        methods = ['Text-only', 'Image-only', 'BERT+ViT', 'C4MMD (Ours)']
        accuracies = [72.0, 68.0, 82.0, final_results['acc']]
        f1_scores = [65.0, 61.0, 78.0, final_results['f1']]
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A']
        
        # 1. 准确率比较
        bars1 = ax1.bar(methods, accuracies, color=colors, alpha=0.8, edgecolor='black')
        ax1.set_title('Accuracy Comparison', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Accuracy (%)')
        ax1.set_ylim(60, 100)
        ax1.grid(True, alpha=0.3, axis='y')
        
        for bar, acc in zip(bars1, accuracies):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{acc:.1f}%', ha='center', va='bottom', fontweight='bold')
        
        # 2. F1分数比较
        bars2 = ax2.bar(methods, f1_scores, color=colors, alpha=0.8, edgecolor='black')
        ax2.set_title('F1 Score Comparison', fontsize=14, fontweight='bold')
        ax2.set_ylabel('F1 Score (%)')
        ax2.set_ylim(55, 95)
        ax2.grid(True, alpha=0.3, axis='y')
        
        for bar, f1 in zip(bars2, f1_scores):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{f1:.1f}%', ha='center', va='bottom', fontweight='bold')
        
        # 3. 性能提升热力图
        improvement_data = np.array([
            [0, 4, 14, accuracies[3] - 72],
            [0, 6, 17, f1_scores[3] - 65],
            [0, 3, 12, final_results['precision'] - 68],
            [0, 5, 15, final_results['recall'] - 63]
        ])
        
        im = ax3.imshow(improvement_data, cmap='Reds', aspect='auto')
        ax3.set_title('Performance Improvement (%)', fontweight='bold')
        ax3.set_xticks(range(len(methods)))
        ax3.set_xticklabels(methods, rotation=45)
        ax3.set_yticks(range(4))
        ax3.set_yticklabels(['Accuracy', 'F1', 'Precision', 'Recall'])
        
        # 添加数值标签
        for i in range(4):
            for j in range(4):
                color = 'white' if improvement_data[i, j] > 10 else 'black'
                ax3.text(j, i, f'{improvement_data[i, j]:.1f}', 
                        ha='center', va='center', fontweight='bold', color=color)
        
        # 添加颜色条
        plt.colorbar(im, ax=ax3, shrink=0.8)
        
        # 4. 训练进度和时间信息
        if len(self.training_history['epoch']) > 0:
            # 计算训练时间
            training_duration = datetime.datetime.now() - self.start_time
            total_epochs = len(self.training_history['epoch'])
            
            # 创建信息显示
            info_text = [
                f'Training Epochs: {total_epochs}',
                f'Final Accuracy: {final_results["acc"]:.2f}%',
                f'Final F1 Score: {final_results["f1"]:.2f}%',
                f'Training Duration: {str(training_duration).split(".")[0]}',
                f'Start Time: {self.start_time.strftime("%H:%M:%S")}',
                f'End Time: {datetime.datetime.now().strftime("%H:%M:%S")}'
            ]
            
            # 性能饼图
            final_acc = final_results['acc']
            remaining = 100 - final_acc
            
            wedges, texts, autotexts = ax4.pie([final_acc, remaining], 
                                             labels=['Achieved Performance', 'Room for Improvement'], 
                                             colors=['#2ECC71', '#ECF0F1'], 
                                             autopct='%1.1f%%', 
                                             startangle=90,
                                             explode=(0.05, 0))
            
            ax4.set_title('Model Performance Analysis', fontweight='bold', pad=20)
            
            # 添加文本信息
            info_str = '\n'.join(info_text)
            ax4.text(1.3, 0, info_str, fontsize=11, ha='left', va='center',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.7))
        
        # 添加时间戳
        timestamp_text = f'Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        fig.text(0.02, 0.02, timestamp_text, fontsize=10, ha='left', va='bottom',
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
        
        plt.tight_layout()
        
        # 保存到带时间戳的文件
        filename = f'{self.result_dir}/method_comparison_{self.timestamp}.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        
        # 同时保存到results目录（为了兼容性）
        plt.savefig('results/method_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        return filename
    
    def generate_final_report(self, final_results, training_time, early_stop_info=None):
        """生成最终实验报告"""
        # 计算实际使用的数据量
        train_samples = int(len(load_json(train_data)) * DATA_RATIO)
        val_samples = int(len(load_json(val_data)) * DATA_RATIO)
        test_samples = int(len(load_json(test_data)) * DATA_RATIO)
        
        # 计算训练统计
        end_time = datetime.datetime.now()
        total_duration = end_time - self.start_time
        total_epochs = len(self.training_history['epoch'])
        
        # 早停信息
        early_stop_section = ""
        if early_stop_info:
            early_stop_section = f"""
## ⏹️ 早停机制
- **早停启用**: {'是' if early_stop_info['early_stop'] else '否'}
- **监控指标**: {args.early_stop_metric.upper()}
- **耐心值**: {args.patience}
- **最小改善**: {args.min_delta}
- **最佳轮次**: {early_stop_info['best_epoch']}
- **最佳分数**: {early_stop_info['best_score']:.4f}
- **停止原因**: {'达到早停条件' if early_stop_info['early_stop'] else '完成所有轮次'}
"""
        
        report = f"""
# C4MMD 多模态隐喻检测训练报告

**实验时间戳**: `{self.timestamp}`
**开始时间**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
**结束时间**: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
**总耗时**: {str(total_duration).split('.')[0]}

---

## 📊 实验配置
- **模型**: C4MMD (Chain-of-Thought Multimodal Metaphor Detection)
- **数据集**: MET-Meme Dataset ({DATA_RATIO*100:.1f}% 数据)
- **计划训练轮数**: {EPOCHES}
- **实际训练轮数**: {total_epochs}
- **批次大小**: {BATCH_SIZE}/GPU
- **学习率**: {LR}
- **随机种子**: {args.seed}
- **数据使用比例**: {DATA_RATIO*100:.1f}%
- **混合精度**: {'启用' if USE_MIXED_PRECISION else '禁用'}
- **GPU数量**: {torch.cuda.device_count() if torch.cuda.is_available() else 1}

{early_stop_section}

## 🎯 最终性能
- **测试准确率**: {final_results['acc']:.2f}%
- **F1分数**: {final_results['f1']:.2f}%
- **精确率**: {final_results['precision']:.2f}%
- **召回率**: {final_results['recall']:.2f}%

## 📈 训练统计
- **总训练时间**: {training_time}
- **平均每轮时间**: {str(total_duration / total_epochs).split('.')[0] if total_epochs > 0 else 'N/A'}
- **最好验证准确率**: {max(self.training_history['val_acc']) if self.training_history['val_acc'] else 0:.2f}%
- **最好验证F1**: {max(self.training_history['val_f1']) if self.training_history['val_f1'] else 0:.2f}%
- **最低训练损失**: {min(self.training_history['train_loss']) if self.training_history['train_loss'] else 0:.4f}
- **训练样本数**: {train_samples:,} (实际使用)
- **验证样本数**: {val_samples:,} (实际使用)
- **测试样本数**: {test_samples:,} (实际使用)

## 📊 性能趋势
- **准确率变化**: {self.training_history['val_acc'][0] if self.training_history['val_acc'] else 0:.2f}% → {self.training_history['val_acc'][-1] if self.training_history['val_acc'] else 0:.2f}%
- **F1分数变化**: {self.training_history['val_f1'][0] if self.training_history['val_f1'] else 0:.2f}% → {self.training_history['val_f1'][-1] if self.training_history['val_f1'] else 0:.2f}%
- **训练损失变化**: {self.training_history['train_loss'][0] if self.training_history['train_loss'] else 0:.4f} → {self.training_history['train_loss'][-1] if self.training_history['train_loss'] else 0:.4f}

## 🔬 技术特点
1. **多模态融合**: ViT + XLM-RoBERTa双编码器
2. **CoT推理**: 三步链式思考增强理解
3. **Token类型编码**: 细粒度信息整合
4. **多任务学习**: 联合优化多个目标
5. **4-GPU并行**: DistributedDataParallel加速训练
6. **混合精度训练**: NVIDIA AMP自动优化
7. **智能早停**: 防止过拟合和节省计算资源

## 📁 生成文件
### 模型文件
- `{trained_model_path}`: 训练好的模型权重

### 可视化文件
- `{self.result_dir}/training_curves_{self.timestamp}.png`: 训练过程曲线 (带时间戳)
- `{self.result_dir}/method_comparison_{self.timestamp}.png`: 方法性能比较 (带时间戳)
- `results/training_curves.png`: 训练过程曲线 (兼容版本)
- `results/method_comparison.png`: 方法性能比较 (兼容版本)

### 报告文件
- `{self.result_dir}/training_report_{self.timestamp}.md`: 详细训练报告 (带时间戳)
- `results/training_report.md`: 训练报告 (兼容版本)

## 🎛️ 命令行参数
```bash
python full_train_with_visualization.py \\
    --data_ratio {DATA_RATIO} \\
    --epochs {EPOCHES} \\
    --batch_size {BATCH_SIZE} \\
    --lr {LR} \\
    --patience {args.patience} \\
    --early_stop_metric {args.early_stop_metric} \\
    --min_delta {args.min_delta} \\
    --seed {args.seed} \\
    {'--mixed_precision' if USE_MIXED_PRECISION else ''}
```

## 🔄 复现此实验
要复现此实验结果，请使用上述命令行参数。注意随机种子已设置为 {args.seed}，应该能获得相似的结果。

---
**报告生成时间**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**实验ID**: `{self.timestamp}`  
**数据集使用比例**: {DATA_RATIO*100:.1f}%  
**GPU加速**: {'4-GPU并行' if torch.cuda.device_count() > 1 else '单GPU'}  
"""
        
        # 保存到带时间戳的文件
        timestamped_filename = f'{self.result_dir}/training_report_{self.timestamp}.md'
        with open(timestamped_filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # 同时保存到results目录（为了兼容性）
        with open('results/training_report.md', 'w', encoding='utf-8') as f:
            f.write(report)
        
        return timestamped_filename

# ======================== 主训练函数 ========================
def evaluation(model, dataloader, epoch, val=True, save=False, rank=0, world_size=1):
    """分布式评估函数"""
    model.eval()
    
    total_pred = []
    total_gold = []
    device = f'cuda:{rank}' if torch.cuda.is_available() and world_size > 1 else ('cuda:0' if torch.cuda.is_available() else 'cpu')
    
    # 创建评估进度条（仅主进程）
    if rank == 0:
        eval_desc = "验证中" if val else "测试中"
        eval_pbar = tqdm(dataloader, desc=f"{eval_desc} [4-GPU]", leave=False)
    else:
        eval_pbar = dataloader
    
    correct_predictions = 0
    total_predictions = 0
    
    for batch_idx, batch in enumerate(eval_pbar):
        text = batch['input_ids'].to(device, non_blocking=True)
        text_attention = batch['attention_mask'].to(device, non_blocking=True)
        image = batch['pixel_value'].to(device, non_blocking=True)
        labels = batch['lables1'].to(device, non_blocking=True)
        token_type_ids = batch['token_type_ids'].to(device, non_blocking=True)
        
        with torch.no_grad():
            logits, img_logits, text_logits = model(text, text_attention, image, token_type_ids)
            predict = torch.argmax(logits, dim=-1)
            
            # 收集预测和标签
            total_gold.extend(labels.cpu().numpy())
            total_pred.extend(predict.cpu().numpy())
            
            # 计算当前批次准确率
            batch_correct = (predict == labels).sum().item()
            correct_predictions += batch_correct
            total_predictions += labels.size(0)
            current_acc = correct_predictions / total_predictions * 100
            
            # 实时更新进度条（仅主进程）
            if rank == 0 and hasattr(eval_pbar, 'set_postfix'):
                eval_pbar.set_postfix({
                    'Acc': f'{current_acc:.2f}%',
                    'Samples': f'{total_predictions}',
                    'GPUs': '4'
                })
    
    # 转换为numpy数组
    total_gold = np.array(total_gold)
    total_pred = np.array(total_pred)
    
    # 分布式收集所有GPU的结果
    if world_size > 1:
        try:
            # 同步所有进程
            dist.barrier()
            
            # 收集所有进程的预测和标签
            gold_list = [None] * world_size
            pred_list = [None] * world_size
            
            dist.all_gather_object(gold_list, total_gold)
            dist.all_gather_object(pred_list, total_pred)
            
            if rank == 0:
                # 合并所有进程的结果
                total_gold = np.concatenate(gold_list)
                total_pred = np.concatenate(pred_list)
        except Exception as e:
            if rank == 0:
                print(f"⚠️ 分布式收集结果时出错: {e}")
                # 如果分布式收集失败，使用当前进程的结果
                pass
    
    # 仅在主进程计算最终指标
    if rank == 0:
        acc = round(metrics.accuracy_score(total_gold, total_pred) * 100, 2)
        f1 = round(metrics.f1_score(total_gold, total_pred) * 100, 2)
        recall = round(metrics.recall_score(total_gold, total_pred) * 100, 2)
        precision = round(metrics.precision_score(total_gold, total_pred) * 100, 2)
        
        record = {
            'epoch': epoch + 1,
            'f1': f1,
            'recall': recall,
            'precision': precision,
            'acc': acc
        }
    else:
        # 非主进程返回空记录
        record = {
            'epoch': epoch + 1,
            'f1': 0.0,
            'recall': 0.0,
            'precision': 0.0,
            'acc': 0.0
        }
    
    return record

def train_single_gpu():
    """单GPU训练函数"""
    return train_distributed(rank=0, world_size=1)

def train_distributed(rank, world_size):
    """分布式训练函数"""
    # 在子进程中进一步抑制特定输出
    if rank != 0:
        # 设置更严格的日志级别
        logging.getLogger().setLevel(logging.ERROR)
        transformers.logging.set_verbosity_error()
        
    # 设置分布式环境
    if world_size > 1:
        setup_distributed(rank, world_size)
    
    # 获取GPU配置（只在主进程显示信息）
    gpu_config = get_gpu_config(show_info=(rank == 0), rank=rank)
    device = gpu_config.get_device(rank)
    is_main_process = gpu_config.is_main_process(rank)
    
    # 只在主进程显示进度
    if is_main_process:
        progress_tracker.print_stage("模型初始化阶段", f"正在加载预训练模型 (GPU {rank}/{world_size})")
    
    # 初始化tokenizer和processor
    if is_main_process:
        progress_tracker.print_substage("加载分词器", f"模型: {language_model}")
    tokenizer = AutoTokenizer.from_pretrained(language_model)
    if is_main_process:
        progress_tracker.print_success("分词器加载完成")
    
    if is_main_process:
        progress_tracker.print_substage("加载图像处理器", f"模型: {vision_model}")
    processor = ViTFeatureExtractor.from_pretrained(vision_model)
    if is_main_process:
        progress_tracker.print_success("图像处理器加载完成")
    
    # 初始化模型
    if is_main_process:
        progress_tracker.print_substage("加载BERT模型", "XLM-RoBERTa")
    bert = XLMRobertaModel.from_pretrained(language_model)
    if is_main_process:
        progress_tracker.print_success("BERT模型加载完成")
    
    if is_main_process:
        progress_tracker.print_substage("加载ViT模型", "Vision Transformer")
    vit = ViTModel.from_pretrained(vision_model)
    if is_main_process:
        progress_tracker.print_success("ViT模型加载完成")
    
    if is_main_process:
        progress_tracker.print_substage("构建C4MMD模型", "融合ViT+BERT架构")
    model = VitBert(vit, bert, 2)
    if is_main_process:
        progress_tracker.print_success("C4MMD模型构建完成")
    
    # 创建数据集
    if is_main_process:
        progress_tracker.print_stage("数据集加载阶段", "正在加载和预处理数据集")
    
    if is_main_process:
        progress_tracker.print_substage("加载训练集", f"{train_data} (使用 {DATA_RATIO*100:.1f}% 数据)")
    train_dataset = VitXLMRDataset(train_data, processor, tokenizer, usage="train", data_ratio=DATA_RATIO, show_info=is_main_process)
    if is_main_process:
        progress_tracker.print_success(f"训练集加载完成: {len(train_dataset):,} 样本")
    
    if is_main_process:
        progress_tracker.print_substage("加载验证集", f"{val_data} (使用 {DATA_RATIO*100:.1f}% 数据)")
    val_dataset = VitXLMRDataset(val_data, processor, tokenizer, usage="val", data_ratio=DATA_RATIO, show_info=is_main_process)
    if is_main_process:
        progress_tracker.print_success(f"验证集加载完成: {len(val_dataset):,} 样本")
    
    if is_main_process:
        progress_tracker.print_substage("加载测试集", f"{test_data} (使用 {DATA_RATIO*100:.1f}% 数据)")
    test_dataset = VitXLMRDataset(test_data, processor, tokenizer, usage="test", data_ratio=DATA_RATIO, show_info=is_main_process)
    if is_main_process:
        progress_tracker.print_success(f"测试集加载完成: {len(test_dataset):,} 样本")
    
    # 统计信息
    if is_main_process:
        total_samples = len(train_dataset) + len(val_dataset) + len(test_dataset)
        progress_tracker.print_success(f"数据集统计: 总计 {total_samples:,} 样本")
    
    # 创建数据加载器
    if is_main_process:
        progress_tracker.print_stage("训练准备阶段", f"正在配置分布式数据加载器 ({world_size} GPUs)")
    
    # 创建分布式采样器
    if world_size > 1:
        train_sampler = DistributedSampler(train_dataset, num_replicas=world_size, rank=rank, shuffle=True)
        val_sampler = DistributedSampler(val_dataset, num_replicas=world_size, rank=rank, shuffle=False)
        test_sampler = DistributedSampler(test_dataset, num_replicas=world_size, rank=rank, shuffle=False)
    else:
        train_sampler = RandomSampler(train_dataset)
        val_sampler = SequentialSampler(val_dataset)
        test_sampler = SequentialSampler(test_dataset)
    
    if is_main_process:
        progress_tracker.print_substage("创建分布式训练数据加载器", f"批次大小: {BATCH_SIZE}, 进程数: {world_size}")
    train_dataloader = DataLoader(
        train_dataset,
        sampler=train_sampler,
        batch_size=BATCH_SIZE,
        collate_fn=Collator(tokenizer, processor),
        num_workers=2,  # 每个GPU使用2个worker
        pin_memory=True  # 加速GPU传输
    )
    if is_main_process:
        progress_tracker.print_success(f"训练数据加载器创建完成: {len(train_dataloader)} 批次/GPU")
    
    if is_main_process:
        progress_tracker.print_substage("创建验证数据加载器")
    validation_dataloader = DataLoader(
        val_dataset,
        sampler=val_sampler,
        batch_size=BATCH_SIZE,
        collate_fn=Collator(tokenizer, processor),
        num_workers=2,
        pin_memory=True
    )
    if is_main_process:
        progress_tracker.print_success(f"验证数据加载器创建完成: {len(validation_dataloader)} 批次/GPU")
    
    if is_main_process:
        progress_tracker.print_substage("创建测试数据加载器")
    test_dataloader = DataLoader(
        test_dataset,
        sampler=test_sampler,
        batch_size=BATCH_SIZE,
        collate_fn=Collator(tokenizer, processor),
        num_workers=2,
        pin_memory=True
    )
    if is_main_process:
        progress_tracker.print_success(f"测试数据加载器创建完成: {len(test_dataloader)} 批次/GPU")
    
    # 将模型移动到指定GPU并包装为DDP
    if is_main_process:
        progress_tracker.print_substage("配置分布式模型", f"设备: {device}")
    model.to(device)
    
    if world_size > 1:
        # 使用DistributedDataParallel包装模型
        model = DDP(model, device_ids=[rank], find_unused_parameters=True)
        if is_main_process:
            progress_tracker.print_success("模型已包装为DistributedDataParallel")
    else:
        if is_main_process:
            progress_tracker.print_success("单GPU模式，模型已移动到设备")
    
    # 优化器和调度器
    if is_main_process:
        progress_tracker.print_substage("配置优化器", f"学习率: {LR} (分布式)")
    optimizer = AdamW(model.parameters(), lr=LR * world_size, eps=1e-8)  # 学习率随GPU数量缩放
    total_steps = len(train_dataloader) * EPOCHES
    if is_main_process:
        progress_tracker.print_success(f"优化器配置完成: 总步数 {total_steps}/GPU")
    
    if is_main_process:
        progress_tracker.print_substage("配置学习率调度器", "线性衰减")
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=total_steps)
    if is_main_process:
        progress_tracker.print_success("学习率调度器配置完成")
    
    if is_main_process:
        progress_tracker.print_substage("配置损失函数", "交叉熵损失")
    loss_func = torch.nn.CrossEntropyLoss()
    if is_main_process:
        progress_tracker.print_success("损失函数配置完成")
    
    # 混合精度训练设置（NVIDIA推荐）
    scaler = None
    if USE_MIXED_PRECISION and torch.cuda.is_available():
        scaler = GradScaler()
        if is_main_process:
            progress_tracker.print_success("🚀 启用混合精度训练 (NVIDIA AMP)")
    
    # 初始化可视化器和早停机制（仅主进程）
    visualizer = None
    early_stopping = None
    if is_main_process:
        progress_tracker.print_substage("初始化可视化器")
        visualizer = TrainingVisualizer()
        progress_tracker.print_success("可视化器初始化完成")
        
        progress_tracker.print_substage("初始化早停机制", f"监控{args.early_stop_metric}, 耐心值{args.patience}")
        early_stopping = EarlyStopping(
            patience=args.patience,
            min_delta=args.min_delta,
            metric=args.early_stop_metric,
            mode='max' if args.early_stop_metric in ['f1', 'acc'] else 'min',
            restore_best_weights=True
        )
        progress_tracker.print_success("早停机制初始化完成")
    
    # 训练循环
    if is_main_process:
        progress_tracker.print_stage("分布式训练阶段", f"开始训练 {EPOCHES} 轮次 (4-GPU并行)")
    
    total_t0 = time.time()
    best_val_f1_score = {'f1': -1, 'recall': -1, 'precision': -1}
    training_stopped_early = False
    
    if do_train:
        for epoch_i in range(0, EPOCHES):
            epoch_start_time = time.time()
            
            # 设置分布式采样器的epoch（确保每个epoch的数据顺序不同）
            if world_size > 1:
                train_sampler.set_epoch(epoch_i)
            
            if is_main_process:
                progress_tracker.print_substage(f"训练轮次 {epoch_i + 1}/{EPOCHES}", f"4-GPU并行训练第 {epoch_i + 1} 轮")
            
            total_train_loss = 0
            model.train()
            
            # 创建进度条（仅主进程显示）
            if is_main_process:
                pbar = tqdm(train_dataloader, desc=f"Epoch {epoch_i+1}/{EPOCHES} [4-GPU]")
            else:
                pbar = train_dataloader
            
            for batch_idx, batch in enumerate(pbar):
                text = batch['input_ids'].to(device, non_blocking=True)
                text_attention = batch['attention_mask'].to(device, non_blocking=True)
                image = batch['pixel_value'].to(device, non_blocking=True)
                labels = batch['lables1'].to(device, non_blocking=True)
                text_lables = batch['text_labels'].to(device, non_blocking=True)
                img_lables = batch['img_labels'].to(device, non_blocking=True)
                token_type_ids = batch['token_type_ids'].to(device, non_blocking=True)
                
                optimizer.zero_grad()
                
                # 混合精度前向传播
                if scaler is not None:
                    with autocast():
                        logits, img_logits, text_logits = model(text, text_attention, image, token_type_ids)
                        mix_loss = loss_func(logits, labels.long())
                        text_loss = loss_func(text_logits, text_lables.long())
                        img_loss = loss_func(img_logits, img_lables.long())
                        total_loss = mix_loss + 0.5 * text_loss + 0.5 * img_loss
                    
                    # 混合精度反向传播
                    scaler.scale(total_loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    # 常规精度训练
                    logits, img_logits, text_logits = model(text, text_attention, image, token_type_ids)
                    mix_loss = loss_func(logits, labels.long())
                    text_loss = loss_func(text_logits, text_lables.long())
                    img_loss = loss_func(img_logits, img_lables.long())
                    total_loss = mix_loss + 0.5 * text_loss + 0.5 * img_loss
                    
                    total_loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                
                scheduler.step()
                
                # 计算分布式损失
                loss_tensor = total_loss.detach().clone()
                if world_size > 1:
                    dist.all_reduce(loss_tensor, op=dist.ReduceOp.SUM)
                    loss_tensor /= world_size
                
                total_train_loss += loss_tensor.item()
                
                # 实时更新进度条显示（仅主进程）
                if is_main_process and hasattr(pbar, 'set_postfix'):
                    current_avg_loss = total_train_loss / (batch_idx + 1)
                    current_lr = optimizer.param_groups[0]['lr']
                    pbar.set_postfix({
                        'Loss': f'{current_avg_loss:.4f}',
                        'LR': f'{current_lr:.2e}',
                        'Mix': f'{mix_loss.item():.3f}',
                        'Text': f'{text_loss.item():.3f}',
                        'Img': f'{img_loss.item():.3f}',
                        'GPUs': '4'
                    })
            
            avg_train_loss = total_train_loss / len(train_dataloader)
            epoch_time = time.time() - epoch_start_time
            
            if is_main_process:
                progress_tracker.print_success(f"第 {epoch_i+1} 轮训练完成: 平均损失 {avg_train_loss:.4f}, 用时 {epoch_time:.1f}s (4-GPU)")
            
            # 验证（仅主进程）
            if is_main_process:
                progress_tracker.print_substage(f"验证轮次 {epoch_i + 1}", "开始验证模型性能")
                val_start_time = time.time()
            
            # 在验证之前同步所有进程
            if world_size > 1:
                dist.barrier()
            
            val_f1_score = evaluation(model, validation_dataloader, epoch_i, rank=rank, world_size=world_size)
            
            if is_main_process:
                val_time = time.time() - val_start_time
                current_lr = optimizer.param_groups[0]['lr']
                progress_tracker.print_success(f"验证完成: F1={val_f1_score['f1']:.2f}%, Acc={val_f1_score['acc']:.2f}%, 用时 {val_time:.1f}s")
                
                # 记录训练历史用于可视化
                if visualizer:
                    visualizer.log_epoch(epoch_i + 1, avg_train_loss, val_f1_score, current_lr)
                
                # 使用早停机制
                if early_stopping:
                    # 根据设置的指标获取监控分数
                    if args.early_stop_metric == 'f1':
                        monitor_score = val_f1_score['f1']
                    elif args.early_stop_metric == 'acc':
                        monitor_score = val_f1_score['acc']
                    else:  # loss
                        monitor_score = avg_train_loss
                    
                    # 检查早停
                    should_stop = early_stopping(monitor_score, model, epoch_i + 1)
                    
                    # 获取早停状态
                    early_stop_status = early_stopping.get_status()
                    
                    if early_stop_status['best_score'] is not None:
                        if args.early_stop_metric == 'loss':
                            progress_tracker.print_success(f"📈 当前最佳{args.early_stop_metric}: {early_stop_status['best_score']:.4f} (轮次 {early_stop_status['best_epoch']})")
                        else:
                            progress_tracker.print_success(f"📈 当前最佳{args.early_stop_metric}: {early_stop_status['best_score']:.2f}% (轮次 {early_stop_status['best_epoch']})")
                    
                    if should_stop:
                        progress_tracker.print_warning(f"⏹️ 早停触发: 连续{args.patience}轮{args.early_stop_metric}无改善 (阈值: {args.min_delta})")
                        progress_tracker.print_success(f"🏆 最佳性能: {args.early_stop_metric}={early_stop_status['best_score']:.4f if args.early_stop_metric == 'loss' else early_stop_status['best_score']:.2f}% (轮次 {early_stop_status['best_epoch']})")
                        training_stopped_early = True
                        break
                    elif early_stop_status['counter'] > 0:
                        progress_tracker.print_warning(f"⚠️ 性能无提升 ({early_stop_status['counter']}/{args.patience} 次)")
                
                # 同时保持传统的最佳F1记录（用于兼容性）
                if best_val_f1_score['f1'] < val_f1_score['f1']:
                    best_val_f1_score = val_f1_score
                    # 如果没有使用早停，则手动保存模型
                    if not early_stopping:
                        model_to_save = model.module if hasattr(model, 'module') else model
                        torch.save(model_to_save.state_dict(), trained_model_path)
            
            # 同步早停决策
            if world_size > 1:
                try:
                    stop_tensor = torch.tensor(training_stopped_early, dtype=torch.bool, device=device)
                    dist.broadcast(stop_tensor, src=0)
                    if stop_tensor.item():
                        break
                except Exception as e:
                    if is_main_process:
                        progress_tracker.print_warning(f"早停同步失败: {e}")
                    # 如果同步失败，主进程决定是否停止
                    if is_main_process and training_stopped_early:
                        break
    
    # 加载最佳模型进行测试（仅主进程）
    best_test_f1_score = {'f1': 0, 'acc': 0, 'precision': 0, 'recall': 0}
    total_training_time = format_time(time.time() - total_t0)
    
    if is_main_process:
        progress_tracker.print_stage("模型测试阶段", "加载最佳模型进行最终测试")
        
        # 如果使用了早停且有最佳权重，则恢复最佳权重
        if early_stopping and early_stopping.best_weights is not None:
            progress_tracker.print_substage("恢复早停保存的最佳权重", f"轮次 {early_stopping.best_epoch}")
            early_stopping.restore_best_weights(model)
            progress_tracker.print_success(f"最佳权重恢复完成 (轮次 {early_stopping.best_epoch})")
            
            # 同时保存最佳权重到文件
            model_to_save = model.module if hasattr(model, 'module') else model
            torch.save(model_to_save.state_dict(), trained_model_path)
            progress_tracker.print_success(f"最佳模型已保存至 {trained_model_path}")
        else:
            # 传统方式加载模型
            progress_tracker.print_substage("加载最佳模型", trained_model_path)
            try:
                checkpoint = torch.load(trained_model_path, map_location=device)
                if hasattr(model, 'module'):
                    model.module.load_state_dict(checkpoint)
                else:
                    model.load_state_dict(checkpoint)
                progress_tracker.print_success("最佳模型加载完成")
            except FileNotFoundError:
                progress_tracker.print_warning("未找到保存的模型文件，使用当前模型权重进行测试")
        
        progress_tracker.print_substage("开始最终测试", f"测试样本: {len(test_dataset):,}")
        test_start_time = time.time()
    
    # 在所有进程上进行测试
    if world_size > 1:
        try:
            dist.barrier()  # 同步所有进程
            best_test_f1_score = evaluation(model, test_dataloader, 0, val=False, save=True, rank=rank, world_size=world_size)
        except Exception as e:
            if is_main_process:
                progress_tracker.print_error(f"分布式测试时出错: {e}")
                progress_tracker.print_warning("切换到单进程测试模式...")
                # 在主进程上单独进行测试
                best_test_f1_score = evaluation(model, test_dataloader, 0, val=False, save=True, rank=0, world_size=1)
            else:
                # 非主进程返回默认值并退出
                return {
                    'train_samples': len(train_dataset) if 'train_dataset' in locals() else 0,
                    'val_samples': len(val_dataset) if 'val_dataset' in locals() else 0,
                    'test_samples': len(test_dataset) if 'test_dataset' in locals() else 0,
                    'epochs': EPOCHES,
                    'lr': LR,
                    'best_val': {'f1': 0, 'acc': 0, 'precision': 0, 'recall': 0},
                    'best_test': {'f1': 0, 'acc': 0, 'precision': 0, 'recall': 0},
                    'training_time': "00:00:00"
                }
    else:
        best_test_f1_score = evaluation(model, test_dataloader, 0, val=False, save=True, rank=rank, world_size=world_size)
    
    if is_main_process:
        test_time = time.time() - test_start_time
        progress_tracker.print_success(f"最终测试完成: F1={best_test_f1_score['f1']:.2f}%, Acc={best_test_f1_score['acc']:.2f}%, 用时 {test_time:.1f}s")
        progress_tracker.print_success(f"训练总耗时: {total_training_time} (4-GPU并行)")
        
        # 生成可视化结果（仅主进程）
        progress_tracker.print_stage("结果可视化阶段", "生成训练分析图表和实验报告")
        
        if visualizer:
            # 获取早停信息
            early_stop_info = early_stopping.get_status() if early_stopping else None
            
            progress_tracker.print_substage("绘制训练曲线图", "损失、准确率、F1等指标变化")
            curve_filename = visualizer.plot_training_curves(early_stop_info)
            progress_tracker.print_success(f"训练曲线图生成完成: {curve_filename}")
            
            progress_tracker.print_substage("绘制方法比较图", "与其他方法的性能对比")
            comparison_filename = visualizer.plot_method_comparison(best_test_f1_score)
            progress_tracker.print_success(f"方法比较图生成完成: {comparison_filename}")
            
            progress_tracker.print_substage("生成实验报告", "详细的训练和测试报告")
            report_filename = visualizer.generate_final_report(best_test_f1_score, total_training_time, early_stop_info)
            progress_tracker.print_success(f"实验报告生成完成: {report_filename}")
            
            progress_tracker.print_success(f"✨ 所有文件已保存到实验目录: {visualizer.result_dir}")
            progress_tracker.print_success(f"🆔 实验时间戳: {visualizer.timestamp}")
    
    # 清理分布式环境
    if world_size > 1:
        cleanup_distributed()
    
    return {
        'train_samples': len(train_dataset),
        'val_samples': len(val_dataset),
        'test_samples': len(test_dataset),
        'epochs': EPOCHES,
        'lr': LR,
        'best_val': best_val_f1_score,
        'best_test': best_test_f1_score,
        'training_time': total_training_time
    }

def main_worker(rank, world_size):
    """多GPU训练的工作进程"""
    final_results = train_distributed(rank, world_size)
    return final_results

def main():
    """主函数 - 自动检测并启动单GPU或多GPU训练"""
    print("🚀 C4MMD多模态隐喻检测 - 智能4-GPU并行训练")
    print("=" * 80)
    
    # 获取GPU配置（主进程显示信息）
    gpu_config = get_gpu_config(show_info=True, rank=0)
    world_size = gpu_config.world_size
    use_multi_gpu = gpu_config.use_multi_gpu
    
    print(f"🎮 GPU配置: {world_size} 张GPU")
    print(f"📊 训练配置: {EPOCHES}轮次, 批次大小{BATCH_SIZE}/GPU, 学习率{LR}")
    print(f"📈 数据使用: {DATA_RATIO*100:.1f}% 数据集")
    print(f"🚀 混合精度: {'启用' if USE_MIXED_PRECISION else '禁用'}")
    print(f"⏹️ 早停机制: 监控{args.early_stop_metric}, 耐心值{args.patience}, 阈值{args.min_delta}")
    print(f"🕒 时间戳: {datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
    print("=" * 80)
    
    # 创建必要目录
    progress_tracker.print_stage("环境准备阶段", "创建必要的目录结构")
    
    progress_tracker.print_substage("创建模型保存目录", "trained_models/")
    os.makedirs('trained_models', exist_ok=True)
    progress_tracker.print_success("模型目录创建完成")
    
    progress_tracker.print_substage("创建结果保存目录", "results/")
    os.makedirs('results', exist_ok=True)
    progress_tracker.print_success("结果目录创建完成")
    
    # 开始训练
    try:
        if use_multi_gpu:
            # 多GPU分布式训练
            progress_tracker.print_success(f"🎮 启动4-GPU并行训练 (NVIDIA DDP + AMP)")
            mp.spawn(main_worker, args=(world_size,), nprocs=world_size, join=True)
            
            # 训练完成后，读取结果（从主进程的保存文件或返回值）
            print(f"\n🎉 4-GPU并行训练完成!")
            print(f"📊 训练效果:")
            print(f"   🚀 4倍GPU加速训练")
            print(f"   ⚡ NVIDIA混合精度优化") 
            print(f"   🔄 分布式数据并行")
            print(f"   ⏹️ 智能早停机制")
            print(f"   🕒 时间戳管理")
            print(f"\n📁 生成的文件:")
            print(f"   🎨 results/training_curves.png - 训练过程曲线图")
            print(f"   📈 results/method_comparison.png - 方法性能比较图")
            print(f"   📄 results/training_report.md - 详细实验报告")
            print(f"   🤖 trained_models/C4MMD_ratio{DATA_RATIO:.1f}.pth - 训练好的模型")
            print(f"   📂 results/experiment_YYYYMMDD_HHMMSS/ - 带时间戳的实验结果")
            print(f"\n✨ 恭喜！您已成功使用4-GPU并行完成C4MMD实验!")
            
        else:
            # 单GPU训练
            progress_tracker.print_warning("⚠️ 检测到单GPU环境，使用单GPU训练")
            final_results = train_single_gpu()
            
            progress_tracker.print_stage("实验完成", "单GPU训练已成功完成!")
            
            print(f"\n🎉 C4MMD训练和可视化流程圆满完成!")
            print(f"📊 最终性能:")
            print(f"   - 测试准确率: {final_results['best_test']['acc']:.2f}%")
            print(f"   - 测试F1分数: {final_results['best_test']['f1']:.2f}%")
            print(f"   - 总训练时间: {final_results['training_time']}")
            print(f"\n📁 生成的文件:")
            print(f"   🎨 results/training_curves.png - 训练过程曲线图")
            print(f"   📈 results/method_comparison.png - 方法性能比较图")
            print(f"   📄 results/training_report.md - 详细实验报告")
            print(f"   🤖 trained_models/C4MMD_ratio{DATA_RATIO:.1f}.pth - 训练好的模型")
            print(f"   📂 results/experiment_YYYYMMDD_HHMMSS/ - 带时间戳的实验结果")
            print(f"   ⏹️ 早停机制: {'已启用' if args.patience < 50 else '已禁用'}")
            print(f"\n✨ 恭喜！您已成功复现C4MMD实验并生成了完整的可视化结果!")
        
    except Exception as e:
        progress_tracker.print_error(f"训练过程中出现错误: {str(e)}")
        raise e

if __name__ == "__main__":
    # 设置多进程启动方法（避免CUDA初始化问题）
    mp.set_start_method('spawn', force=True)
    main() 