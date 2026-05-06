# -*- coding:utf-8 -*-
"""
POFHP (Point Process with Heterogeneous Propagation) 核心代码整合
包含模型定义、数据处理、训练逻辑等所有核心功能
不考虑多GPU功能，专注于单GPU/CPU训练
"""

import argparse
import collections
import copy
import pickle
import random
import time
import os

import numpy as np
import torch
import torch_scatter
import gc
import networkx as nx
from sklearn.metrics import mean_squared_error, mean_squared_log_error, mean_absolute_percentage_error
from sklearn.metrics import r2_score
import matplotlib
import matplotlib.pyplot as plt
from torch import nn
import torch.nn.functional as F
import torch.sparse as sparse
from torch_geometric.nn import GATConv, SAGEConv, GCNConv
from torch_geometric.utils import add_self_loops, to_networkx
from torch_geometric.data import HeteroData, Data
from torch_geometric.nn import Node2Vec
from torch_geometric.utils import bipartite_subgraph, to_undirected
from torch_geometric.transforms import RandomNodeSplit
from torch.optim.lr_scheduler import ExponentialLR, StepLR
from torch.cuda.amp import autocast, GradScaler
from tqdm import tqdm

# 设置设备
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
gain = nn.init.calculate_gain('relu')


class EarlyStopping:
    """Early stops the training if validation loss doesn't improve after a given patience."""

    def __init__(self, patience=7, verbose=False, delta=0, path='checkpoint.pt', trace_func=print):
        """
        Args:
            patience (int): How long to wait after last time validation loss improved.
                            Default: 7
            verbose (bool): If True, prints a message for each validation loss improvement.
                            Default: False
            delta (float): Minimum change in the monitored quantity to qualify as an improvement.
                            Default: 0
            path (str): Path for the checkpoint to be saved to.
                            Default: 'checkpoint.pt'
            trace_func (function): trace print function.
                            Default: print
        """
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.val_loss_min = np.Inf
        self.delta = delta
        self.path = path
        self.trace_func = trace_func

    def __call__(self, val_loss, model):
        score = -val_loss

        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
        elif score < self.best_score + self.delta:
            self.counter += 1
            self.trace_func(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
            self.counter = 0

    def save_checkpoint(self, val_loss, model):
        """Saves model when validation loss decrease."""
        if self.verbose:
            self.trace_func(
                f'Validation loss decreased ({self.val_loss_min:.6f} --> {val_loss:.6f}).  Saving model ...')
        self.val_loss_min = val_loss


def args_parser():
    """参数解析器"""
    parser = argparse.ArgumentParser()

    parser.add_argument('--data_name', type=str, default='android', help='data name')
    parser.add_argument('--epochs', type=int, default=200, help='epochs')
    parser.add_argument('--min_epochs', type=int, default=5, help='epochs')

    parser.add_argument('--in_feats', type=int, default=64, help='input dimension')
    parser.add_argument('--h_feats', type=int, default=64, help='h_feats')
    parser.add_argument('--out_feats', type=int, default=64, help='output feats')

    parser.add_argument('--user_dim', type=int, default=32, help='')
    parser.add_argument('--message_dim', type=int, default=32, help='')
    parser.add_argument('--num_users', type=int, default=0, help='')
    parser.add_argument('--num_messages', type=int, default=0, help='')

    parser.add_argument('--heads', type=int, default=4, help='attention heads')
    parser.add_argument('--lr', type=float, default=0.001, help='learning rate')
    parser.add_argument('--gpu_id', type=int, default=0, help='GPU ID to use')
    parser.add_argument('--weight_decay', type=float, default=5e-4, help='weight decay')
    parser.add_argument('--step_size', type=int, default=100, help='step size')
    parser.add_argument('--gamma', type=float, default=0.5, help='gamma')
    parser.add_argument('--patience', type=int, default=30, help='')

    parser.add_argument('--rho', type=int, default=0.001, help='')

    args = parser.parse_args()
    
    # 根据gpu_id设置device
    if torch.cuda.is_available():
        args.device = torch.device(f"cuda:{args.gpu_id}")
    else:
        args.device = torch.device("cpu")

    return args


def setup_seed(seed):
    """设置随机种子"""
    import random, os
    random.seed(seed)
    np.random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def get_activation(activation_str):
    """获取激活函数"""
    if activation_str == 'relu':
        return nn.ReLU()
    elif activation_str == 'sigmoid':
        return nn.Sigmoid()
    elif activation_str == 'leaky_relu':
        return nn.LeakyReLU()
    elif activation_str == 'elu':
        return nn.ELU()
    elif activation_str == 'prelu':
        return nn.PReLU()
    elif activation_str == 'silu':
        return nn.SiLU()
    elif activation_str == 'gelu':
        return nn.GELU()
    elif activation_str == 'tanh':
        return nn.Tanh()
    elif activation_str == 'softplus':
        return nn.Softplus()
    elif activation_str == 'softsign':
        return nn.Softsign()
    else:
        raise ValueError("Unsupported activation function: " + activation_str)


def save_pickle(dataset, file_name):
    """保存pickle文件"""
    f = open(file_name, "wb")
    pickle.dump(dataset, f)
    f.close()


def load_pickle(file_name):
    """加载pickle文件"""
    f = open(file_name, "rb+")
    dataset = pickle.load(f)
    f.close()
    return dataset


def align_lists(matrix, data_type, t_o=None):
    """对齐列表数据"""
    # cascade or timestamp
    max_length = max(len(row) for row in matrix)
    if data_type == "cascade":
        aligned_matrix = [
            row + [0] * (max_length - len(row))  # pad 0
            for row in matrix
        ]
        user_series = torch.tensor(aligned_matrix)
        return aligned_matrix, user_series
    else:
        min_timestamp = min(min(lst) for lst in matrix)
        matrix = [[timestamp - min_timestamp for timestamp in lst] for lst in matrix]
        t_o = t_o - min_timestamp
        # get mask
        aligned_matrix = [
            row + [-1] * (max_length - len(row))
            for row in matrix
        ]
        _matrix = torch.tensor(aligned_matrix)
        mask = torch.ones_like(_matrix)
        mask = torch.where(_matrix == -1, torch.tensor(-5e9, device=_matrix.device), mask)
        # normalize
        aligned_matrix = [
            row + [0] * (max_length - len(row))
            for row in matrix
        ]
        global_min = min(min(lst) for lst in aligned_matrix if lst)
        global_max = max(max(lst) for lst in aligned_matrix if lst)
        global_min = min(global_min, t_o)
        global_max = max(global_max, t_o)
        # print(global_min, global_max, t_o)
        aligned_matrix = [[(value - global_min) / (global_max - global_min) for value in lst] for lst in aligned_matrix]
        t_o = (t_o - global_min) / (global_max - global_min)
        return aligned_matrix, mask, t_o


def find_last_below_threshold(data, threshold):
    """找到最后一个低于阈值的索引"""
    result = []
    for row in data:
        if row[0] > threshold:
            result.append(0)
        elif row[-1] <= threshold:
            result.append(len(row))
        else:
            for index, value in enumerate(row):
                position = index
                if value <= threshold:
                    continue
                else:
                    break
            result.append(position)

    return result


def get_social_hetero_graph(args, cascades, timestamps, all_users, edge_index):
    """构建社交异构图"""
    users_dict = dict(zip(all_users, [idx for idx in range(len(all_users))]))
    # user
    cascades = [[users_dict[x] for x in y] for y in cascades]
    cascades = [x for x in cascades if len(x) > 5]
    timestamps = [x for x in timestamps if len(x) > 5]
    # 
    order = [i[0] for i in sorted(enumerate(timestamps), key=lambda x: x[1])]
    cascades = [cascades[i] for i in order]
    timestamps = [timestamps[i] for i in order]
    # set t_o and t_p
    flat_list = [item for sublist in timestamps for item in sublist]
    t_o = np.median(flat_list)  # median time
    # 
    label_idx = find_last_below_threshold(timestamps, threshold=t_o)
    labels = [len(timestamp) - idx for timestamp, idx in zip(timestamps, label_idx)]

    delete_idx = [index for index, value in enumerate(labels) if value == 0 or value == len(timestamps[index])]
    # delete_idx = [index for index, value in enumerate(labels) if value == len(timestamps[index])]
    cascades = [row for idx, row in enumerate(cascades) if idx not in delete_idx]
    timestamps = [row for idx, row in enumerate(timestamps) if idx not in delete_idx]
    label_idx = [row for idx, row in enumerate(label_idx) if idx not in delete_idx]
    labels = [row for idx, row in enumerate(labels) if idx not in delete_idx]

    num_users = len(all_users)
    edge_index = [[users_dict[x] for x in edge_index[0]],
                  [users_dict[x] for x in edge_index[1]]]
    user_edge_index = torch.tensor(edge_index)

    cascades = [cascade[:label_idx[item_id]] for item_id, cascade in enumerate(cascades)]
    timestamps = [timestamp[:label_idx[item_id]] for item_id, timestamp in enumerate(timestamps)]

    seq_last_idx = torch.tensor([len(x) - 1 for x in cascades])
    cascades, user_series = align_lists(cascades, data_type="cascade")
    timestamps, mask, t_o = align_lists(timestamps, data_type="timestamp", t_o=t_o)
    seq_last_time = [timestamp[idx] for timestamp, idx in zip(timestamps, seq_last_idx)]

    # construct graph
    num_messages = len(cascades)
    user_to_message_edge_index = [[], []]
    message_to_user_edge_index = [[], []]
    user_propagate_user_edge_index = [[], []]
    # 
    user_retweet_message_times = []
    for item_id, users in enumerate(cascades):
        users = users[:label_idx[item_id]]
        for idx, user in enumerate(users):
            if idx != 0:
                user_propagate_user_edge_index[0].append(users[idx - 1])
                user_propagate_user_edge_index[1].append(users[idx])

            user_retweet_message_times.append(timestamps[item_id][idx])
            user_to_message_edge_index[0].append(user)
            user_to_message_edge_index[1].append(item_id)
            message_to_user_edge_index[0].append(item_id)
            message_to_user_edge_index[1].append(user)

    user_to_message_edge_index = torch.tensor(user_to_message_edge_index)
    message_to_user_edge_index = torch.tensor(message_to_user_edge_index)
    user_propagate_user_edge_index = torch.tensor(user_propagate_user_edge_index)
    # user_to_item_edge_index, _ = add_self_loops(user_to_item_edge_index)
    #
    graph = HeteroData()
    graph['user'].x = torch.randn(num_users, args.user_dim)
    graph['message'].x = torch.randn(num_messages, args.message_dim)
    graph['message'].y = torch.FloatTensor(labels)

    num_of_per_cascade = [1 for _ in range(num_messages)]

    total_nums = np.sum(num_of_per_cascade)
    seq_idx = []
    for i in range(total_nums):
        for j in range(num_of_per_cascade[i]):
            seq_idx.append(i)
    seq_idx = torch.tensor(seq_idx)
    #
    start_idx = 0
    message_first_time = []
    for i in range(num_messages):
        if i != 0:
            start_idx = start_idx + num_of_per_cascade[i - 1]
        cur_first_time = timestamps[start_idx][0]
        for j in range(num_of_per_cascade[i]):
            if timestamps[start_idx + j][0] < cur_first_time:
                cur_first_time = timestamps[start_idx + j][0]

        message_first_time.append(cur_first_time)

    graph.user_series = user_series
    graph.user_series_features = graph['user'].x[graph.user_series]
    graph.seq_idx = seq_idx
    graph.timestamps = torch.FloatTensor(timestamps)
    message_first_time = torch.tensor(message_first_time)
    graph.t_o = t_o
    graph.num_of_per_cascade = torch.tensor(num_of_per_cascade)
    graph.user_retweet_message_times = torch.FloatTensor(user_retweet_message_times)
    graph['message'].first_time = message_first_time
    # graph.seq_first_time = message_first_time[seq_idx]
    graph.seq_last_time = torch.tensor(seq_last_time)
    graph.seq_last_idx = seq_last_idx
    graph.mask = mask
    # supervised mask
    train_len = int(num_messages * 0.8)

    idx = np.arange(num_messages)
    train_mask = np.zeros(num_messages)
    train_mask[idx[:train_len]] = 1
    graph['message'].train_mask = torch.BoolTensor(train_mask)

    test_mask = np.zeros(num_messages)
    test_mask[idx[train_len:]] = 1
    graph['message'].test_mask = torch.BoolTensor(test_mask)

    # edge_index
    graph['user', 'friendship', 'user'].edge_index = user_edge_index
    graph['user', 'to', 'message'].edge_index = user_to_message_edge_index
    graph['message', 'to', 'user'].edge_index = message_to_user_edge_index
    graph['user', 'pr', 'user'].edge_index = user_propagate_user_edge_index

    graph['user', 'friendship', 'user'].edge_index = to_undirected(graph['user', 'friendship', 'user'].edge_index)
    graph['user', 'friendship', 'user'].edge_index, _ = add_self_loops(graph['user', 'friendship', 'user'].edge_index)

    print('train val test:', torch.sum(graph['message'].train_mask), torch.sum(graph['message'].test_mask))

    return graph


def count_roots(A):
    """计算根节点数量"""
    counter = {}
    for root, _ in A:
        if root in counter:
            counter[root] += 1
        else:
            counter[root] = 1
    max_root = max(counter.keys()) if counter else 0

    B = [counter.get(i, 0) for i in range(max_root + 1)]
    return B


def get_stackexchange_hetero_graph(args, se_cascades, se_timestamps, all_users, edge_index):
    """构建StackExchange异构图"""
    users_dict = dict(zip(all_users, [idx for idx in range(len(all_users))]))

    cascades, timestamps = [], []
    for k, v in se_cascades.items():
        se_cascades[k] = [[users_dict[x] for x in y] for y in v]
        se_cascades[k] = [x for x in se_cascades[k] if len(x) > 5]
        se_timestamps[k] = [x for x in se_timestamps[k] if len(x) > 5]
        # 
        sub_cascades = [(k, users) for users in se_cascades[k]]
        cascades.extend(sub_cascades)
        sub_timestamps = [(k, times) for times in se_timestamps[k]]
        timestamps.extend(sub_timestamps)

    # 
    order = [i[0] for i in sorted(enumerate(timestamps), key=lambda x: x[1][1])]
    cascades = [cascades[i] for i in order]
    timestamps = [timestamps[i] for i in order]

    flat_list = [item for _, sublist in timestamps for item in sublist]
    t_o = np.median(flat_list)
    only_timestamps = [timestamp for _, timestamp in timestamps]
    label_idx = find_last_below_threshold(only_timestamps, threshold=t_o)
    labels = [len(timestamp) - idx for timestamp, idx in zip(only_timestamps, label_idx)]

    delete_idx = [index for index, value in enumerate(labels) if value == 0 or value == len(only_timestamps[index])]
    cascades = [row for idx, row in enumerate(cascades) if idx not in delete_idx]
    timestamps = [row for idx, row in enumerate(timestamps) if idx not in delete_idx]
    label_idx = [row for idx, row in enumerate(label_idx) if idx not in delete_idx]
    labels = [row for idx, row in enumerate(labels) if idx not in delete_idx]

    num_users = len(all_users)
    edge_index = [[users_dict[x] for x in edge_index[0]],
                  [users_dict[x] for x in edge_index[1]]]
    user_edge_index = torch.tensor(edge_index)

    cascades = [cascade[1][:label_idx[item_id]] for item_id, cascade in enumerate(cascades)]
    timestamps = [timestamp[1][:label_idx[item_id]] for item_id, timestamp in enumerate(timestamps)]

    seq_last_idx = torch.tensor([len(x) - 1 for x in cascades])
    cascades, user_series = align_lists(cascades, data_type="cascade")
    timestamps, mask, t_o = align_lists(timestamps, data_type="timestamp", t_o=t_o)
    seq_last_time = [timestamp[idx] for timestamp, idx in zip(timestamps, seq_last_idx)]

    # construct graph
    num_messages = len(cascades)
    user_to_message_edge_index = [[], []]
    message_to_user_edge_index = [[], []]
    user_propagate_user_edge_index = [[], []]
    # 
    user_retweet_message_times = []
    for item_id, users in enumerate(cascades):
        users = users[:label_idx[item_id]]
        for idx, user in enumerate(users):
            if idx != 0:
                user_propagate_user_edge_index[0].append(users[idx - 1])
                user_propagate_user_edge_index[1].append(users[idx])

            user_retweet_message_times.append(timestamps[item_id][idx])
            user_to_message_edge_index[0].append(user)
            user_to_message_edge_index[1].append(item_id)
            message_to_user_edge_index[0].append(item_id)
            message_to_user_edge_index[1].append(user)

    user_to_message_edge_index = torch.tensor(user_to_message_edge_index)
    message_to_user_edge_index = torch.tensor(message_to_user_edge_index)
    user_propagate_user_edge_index = torch.tensor(user_propagate_user_edge_index)
    # user_to_item_edge_index, _ = add_self_loops(user_to_item_edge_index)
    #
    graph = HeteroData()
    graph['user'].x = torch.randn(num_users, args.user_dim)
    graph['message'].x = torch.randn(num_messages, args.message_dim)
    graph['message'].y = torch.FloatTensor(labels)

    num_of_per_cascade = [1 for _ in range(num_messages)]

    total_nums = np.sum(num_of_per_cascade)
    seq_idx = []
    for i in range(total_nums):
        for j in range(num_of_per_cascade[i]):
            seq_idx.append(i)
    seq_idx = torch.tensor(seq_idx)
    #
    start_idx = 0
    message_first_time = []
    for i in range(num_messages):
        if i != 0:
            start_idx = start_idx + num_of_per_cascade[i - 1]
        cur_first_time = timestamps[start_idx][0]
        for j in range(num_of_per_cascade[i]):
            if timestamps[start_idx + j][0] < cur_first_time:
                cur_first_time = timestamps[start_idx + j][0]

        message_first_time.append(cur_first_time)

    graph.user_series = user_series
    graph.user_series_features = graph['user'].x[graph.user_series]
    graph.seq_idx = seq_idx
    graph.timestamps = torch.FloatTensor(timestamps)
    message_first_time = torch.tensor(message_first_time)
    graph.t_o = t_o
    graph.num_of_per_cascade = torch.tensor(num_of_per_cascade)
    graph.user_retweet_message_times = torch.FloatTensor(user_retweet_message_times)
    graph['message'].first_time = message_first_time
    # graph.seq_first_time = message_first_time[seq_idx]
    graph.seq_last_time = torch.tensor(seq_last_time)
    graph.seq_last_idx = seq_last_idx
    graph.mask = mask
    # supervised mask
    train_len = int(num_messages * 0.8)

    idx = np.arange(num_messages)
    train_mask = np.zeros(num_messages)
    train_mask[idx[:train_len]] = 1
    graph['message'].train_mask = torch.BoolTensor(train_mask)

    test_mask = np.zeros(num_messages)
    test_mask[idx[train_len:]] = 1
    graph['message'].test_mask = torch.BoolTensor(test_mask)

    # edge_index
    graph['user', 'friendship', 'user'].edge_index = user_edge_index
    graph['user', 'to', 'message'].edge_index = user_to_message_edge_index
    graph['message', 'to', 'user'].edge_index = message_to_user_edge_index
    graph['user', 'pr', 'user'].edge_index = user_propagate_user_edge_index

    graph['user', 'friendship', 'user'].edge_index = to_undirected(graph['user', 'friendship', 'user'].edge_index)
    graph['user', 'friendship', 'user'].edge_index, _ = add_self_loops(graph['user', 'friendship', 'user'].edge_index)

    print('train val test:', torch.sum(graph['message'].train_mask), torch.sum(graph['message'].test_mask))

    return graph


def get_data(args):
    """获取数据"""
    if args.data_name == "android":
        cascades, timestamps, all_users, edge_index = load_data(args, "data/android/")
        graph = get_social_hetero_graph(args, cascades, timestamps, all_users, edge_index)
    elif args.data_name == "douban":
        cascades, timestamps, all_users, edge_index = load_data(args, "data/douban/")
        graph = get_social_hetero_graph(args, cascades, timestamps, all_users, edge_index)
    elif args.data_name == "stackexchange":
        se_cascades, se_timestamps, all_users, edge_index = load_data(args, "data/stackexchange/")
        graph = get_stackexchange_hetero_graph(args, se_cascades, se_timestamps, all_users, edge_index)
    elif args.data_name == "twitter":
        cascades, timestamps, all_users, edge_index = load_data(args, "data/twitter/")
        graph = get_social_hetero_graph(args, cascades, timestamps, all_users, edge_index)
    else:
        raise ValueError("Unsupported dataset: " + args.data_name)

    return graph


def get_pof(graph):
    """构建POF图"""
    # 
    num_users = graph['user'].x.size(0)
    num_messages = graph['message'].x.size(0)
    num_edges = graph['user', 'to', 'message'].edge_index.size(1)

    user_to_message_edge_index = graph['user', 'to', 'message'].edge_index
    message_to_user_edge_index = graph['message', 'to', 'user'].edge_index

    # 
    pof_edge_index = torch.cat([user_to_message_edge_index, message_to_user_edge_index], dim=1)
    pof_x = torch.cat([graph['user'].x, graph['message'].x], dim=0)

    pof_graph = Data(x=pof_x, edge_index=pof_edge_index)

    return pof_graph


def load_data(args, path):
    """加载数据"""
    if args.data_name == "android":
        cascades = load_pickle(path + "android_cascades.pkl")
        timestamps = load_pickle(path + "android_timestamps.pkl")
        all_users = load_pickle(path + "android_users.pkl")
        edge_index = load_pickle(path + "android_edges.pkl")
        return cascades, timestamps, all_users, edge_index
    elif args.data_name == "douban":
        cascades = load_pickle(path + "douban_cascades.pkl")
        timestamps = load_pickle(path + "douban_timestamps.pkl")
        all_users = load_pickle(path + "douban_users.pkl")
        edge_index = load_pickle(path + "douban_edges.pkl")
        return cascades, timestamps, all_users, edge_index
    elif args.data_name == "stackexchange":
        se_cascades = load_pickle(path + "stackexchange_cascades.pkl")
        se_timestamps = load_pickle(path + "stackexchange_timestamps.pkl")
        all_users = load_pickle(path + "stackexchange_users.pkl")
        edge_index = load_pickle(path + "stackexchange_edges.pkl")
        return se_cascades, se_timestamps, all_users, edge_index
    elif args.data_name == "twitter":
        cascades = load_pickle(path + "twitter_cascades.pkl")
        timestamps = load_pickle(path + "twitter_timestamps.pkl")
        all_users = load_pickle(path + "twitter_users.pkl")
        edge_index = load_pickle(path + "twitter_edges.pkl")
        return cascades, timestamps, all_users, edge_index
    else:
        raise ValueError("Unsupported dataset: " + args.data_name)

