import os
import sys
from typing import List

import fire
import torch
import transformers
from datasets import load_dataset,dataset_dict

"""
Unused imports:
import torch.nn as nn
import bitsandbytes as bnb
"""

from peft import (
    LoraConfig,
    get_peft_model,
    get_peft_model_state_dict,
    prepare_model_for_kbit_training,
    set_peft_model_state_dict,
)
from transformers import DataCollatorForLanguageModeling
from utils.prompter import Prompter

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--model_name", type=str, default="DeepSeek-R1-Distill-Llama-8B")  # 设置默认值
args = parser.parse_args()

os.environ["CUDA_VISIBLE_DEVICES"] = "0,1,2"
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def get_data_path(data_name):
    current_path = os.getcwd()
    while True:
        data_root = os.path.join(current_path, "datasets")
        if os.path.exists(data_root) and os.path.isdir(data_root):
            for root, dirs, files in os.walk(data_root):
                for file in files:
                    if file == f"{data_name}.json" or file == f"{data_name}.csv" or file == f"{data_name}.pt":
                        return os.path.join(root, file)
        
        if current_path == os.path.dirname(current_path):
            return None
        
        current_path = os.path.dirname(current_path)

def train(
    # model/data params
    base_model: str = "",  # the only required argument
    data_path: str = "yahma/alpaca-cleaned",
    output_dir: str = "./lora-alpaca",
    # training hyperparams
    batch_size: int = 128,
    micro_batch_size: int = 4,          # 每次卡上放到数据量
    num_epochs: int = 8,                  # 训练轮数 4轮！
    learning_rate: float = 3e-4,        # 学习率
    cutoff_len: int = 256,              # 截断长度
    val_set_size: int = 500,           # 验证集大小 
    # lora hyperparams
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.05,         # 均匀学习，防止单一分支过学习
    lora_target_modules: List[str] = [
        # "query_key_value",
        "q_proj",
        "v_proj",
    ],
    
    # llm hyperparams
    train_on_inputs: bool = True,  # if False, masks out inputs in loss
    add_eos_token: bool = False,
    group_by_length: bool = False,  # faster, but produces an odd training loss curve
    # wandb params
    wandb_project: str = "",
    wandb_run_name: str = "",
    wandb_watch: str = "",  # options: false | gradients | all
    wandb_log_model: str = "",  # options: false | true
    resume_from_checkpoint: str = None,  # either training checkpoint or final adapter
    prompt_template_name: str = "alpaca",  # The prompt template to use, will default to alpaca.
    
    # ——————————————————
    new_template: bool = True,  # 默认使用alpaca模板
    # ——————————————————  
):
    if int(os.environ.get("LOCAL_RANK", 0)) == 0:
        print(
            f"Training Alpaca-LoRA model with params:\n"
            f"base_model: {base_model}\n"
            f"data_path: {data_path}\n"
            f"output_dir: {output_dir}\n"
            # f"batch_size: {batch_size}\n"
            f"micro_batch_size: {micro_batch_size}\n"
            f"num_epochs: {num_epochs}\n"
            f"learning_rate: {learning_rate}\n"
            f"cutoff_len: {cutoff_len}\n"
            f"val_set_size: {val_set_size}\n"
            f"lora_r: {lora_r}\n"
            f"lora_alpha: {lora_alpha}\n"
            f"lora_dropout: {lora_dropout}\n"
            f"lora_target_modules: {lora_target_modules}\n"
            f"train_on_inputs: {train_on_inputs}\n"
            f"add_eos_token: {add_eos_token}\n"
            f"group_by_length: {group_by_length}\n"
            f"wandb_project: {wandb_project}\n"
            f"wandb_run_name: {wandb_run_name}\n"
            f"wandb_watch: {wandb_watch}\n"
            f"wandb_log_model: {wandb_log_model}\n"
            f"resume_from_checkpoint: {resume_from_checkpoint or False}\n"
            f"prompt template: {prompt_template_name}\n"
        )
    assert (
        base_model
    ), "Please specify a --base_model, e.g. --base_model='huggyllama/llama-7b'"
    gradient_accumulation_steps = batch_size // micro_batch_size
    # gradient_accumulation_steps = 32

    prompter = Prompter(prompt_template_name)

    device_map = "auto"
    world_size = int(os.environ.get("WORLD_SIZE", 1))
    ddp = world_size != 1
    if ddp:
        device_map = {"": int(os.environ.get("LOCAL_RANK") or 0)}
        gradient_accumulation_steps = gradient_accumulation_steps // world_size

    # Check if parameter passed or if set within environ
    use_wandb = len(wandb_project) > 0 or (
        "WANDB_PROJECT" in os.environ and len(os.environ["WANDB_PROJECT"]) > 0
    )
    # Only overwrite environ if wandb param passed
    if len(wandb_project) > 0:
        os.environ["WANDB_PROJECT"] = wandb_project
    if len(wandb_watch) > 0:
        os.environ["WANDB_WATCH"] = wandb_watch
    if len(wandb_log_model) > 0:
        os.environ["WANDB_LOG_MODEL"] = wandb_log_model

    from transformers import AutoModelForCausalLM, AutoTokenizer
    if "Phi" in base_model:
        print("step into phi model")
        model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.float16, device_map=device_map, trust_remote_code=True)
        tokenizer = AutoTokenizer.from_pretrained(base_model, add_eos_token=True ,trust_remote_code=True, use_fast=True)
    else:
        print("step into normal model")
        model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.float16, device_map=device_map)
        tokenizer = AutoTokenizer.from_pretrained(base_model)
    
    # —————————————————————— alpaca
    tokenizer.pad_token_id = (
        0  # unk. we want this to be different from the eos token
    )
    # print(tokenizer.pad_token_id)
    # print(type(tokenizer.pad_token_id))
    
    # ——————————————————————

    if new_template:
        print("in here!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!11")
        def tokenize(prompt, add_eos_token=True):
            # there's probably a way to do this with the tokenizer settings
            # but again, gotta move fast
            result = tokenizer(
                prompt,
                truncation=True,
                max_length=cutoff_len,
                padding=False,
                return_tensors=None,
            )
            if (
                result["input_ids"][-1] != tokenizer.eos_token_id
                and len(result["input_ids"]) < cutoff_len
                and add_eos_token
            ):
                result["input_ids"].append(tokenizer.eos_token_id)
                result["attention_mask"].append(1)

            result["labels"] = result["input_ids"].copy()

            return result

        def generate_and_tokenize_prompt(data_point):
            full_prompt = prompter.generate_prompt(
                data_point["instruction"],
                data_point["input"],
                data_point["output"],
            )
            tokenized_full_prompt = tokenize(full_prompt)
            if not train_on_inputs:
                user_prompt = prompter.generate_prompt(
                    data_point["instruction"], data_point["input"]
                )
                tokenized_user_prompt = tokenize(
                    user_prompt, add_eos_token=add_eos_token
                )
                user_prompt_len = len(tokenized_user_prompt["input_ids"])

                if add_eos_token:
                    user_prompt_len -= 1

                tokenized_full_prompt["labels"] = [
                    -100
                ] * user_prompt_len + tokenized_full_prompt["labels"][
                    user_prompt_len:
                ]  # could be sped up, probably
                # print(tokenized_full_prompt)
                # raise ValueError("stop here")
            return tokenized_full_prompt
    else:
        def tokenize(data_point, add_eos_token=True):
            sys_input = "Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.\n\n"
            sys_no_input = "Below is an instruction that describes a task. Write a response that appropriately completes the request.\n\n"
            if data_point['input']:    # 有input
                messages = [{"role": "system", "content": sys_input},
                            {"role": "user", "content": f"### Instruction:\n{data_point['instruction']}\n\n### Input:\n{data_point['input']}\n\n"},
                            {"role": "assistant", "content": f"### Response:\n{data_point['output']}"}]
            else:
                messages = [{"role": "system", "content": sys_no_input},
                            {"role": "user", "content": f"### Instruction:\n{data_point['instruction']}\n\n"},
                            {"role": "assistant", "content": f"### Response:\n{data_point['output']}"}]
                
            result = tokenizer.apply_chat_template(
                messages, 
                tokenize=True, 
                add_generation_prompt=True, 
                truncation=True,
                max_length=cutoff_len,
                padding="max_length",
                return_tensors=None,
                return_dict=True
            )
            if (
                result["input_ids"][-1] != tokenizer.eos_token_id
                and len(result["input_ids"]) < cutoff_len
                and add_eos_token
            ):
                result["input_ids"].append(tokenizer.eos_token_id)
                result["attention_mask"].append(1)

            result["labels"] = result["input_ids"].copy()
            return result
        
        def generate_and_tokenize_prompt(data_point):
            tokenized_full_prompt = tokenize(data_point)
            return tokenized_full_prompt

    model = prepare_model_for_kbit_training(model)

    config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=lora_target_modules,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        init_lora_weights='gaussian',
    )
    model = get_peft_model(model, config)

    if data_path.endswith(".json") or data_path.endswith(".jsonl"):
        print("JSON")
        data = load_dataset("json", data_files=data_path)
    elif data_path.endswith(".csv"):
        data = load_dataset("csv", data_files=data_path)
    else:
        data = load_dataset(data_path)

    # if resume_from_checkpoint: 原本就是none所以本段可以考虑删除
    model.print_trainable_parameters()  # Be more transparent about the % of trainable params.

    if val_set_size > 0:
        train_val = data["train"].train_test_split(
            test_size=val_set_size, shuffle=True, seed=42
        )
        train_data = (
            train_val["train"].shuffle().map(generate_and_tokenize_prompt)
        )
        val_data = (
            train_val["test"].shuffle().map(generate_and_tokenize_prompt)
        )
    else:
        train_data = data["train"].shuffle().map(generate_and_tokenize_prompt)
        val_data = None

    if not ddp and torch.cuda.device_count() > 1:
        # keeps Trainer from trying its own DataParallelism when more than 1 gpu is available
        model.is_parallelizable = True
        model.model_parallel = True
    
    output_dir = output_dir+f"__ral_{lora_r}_{lora_alpha}_{learning_rate}_{num_epochs}"
    trainer = transformers.Trainer(
        model=model,
        train_dataset=train_data,
        eval_dataset=val_data,
        args=transformers.TrainingArguments(
            push_to_hub=True,
            hub_model_id="0Strelitzia2/Intelligent_wanxiang",
            per_device_train_batch_size=micro_batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            warmup_steps=10,
            num_train_epochs=num_epochs,
            learning_rate=learning_rate,
            fp16=True,
            logging_steps=5,
            optim="adamw_torch",
            eval_strategy="steps" if val_set_size > 0 else "no",
            save_strategy="steps",
            eval_steps=25 if val_set_size > 0 else None,
            save_steps=25,
            output_dir=output_dir,
            save_total_limit=5,
            load_best_model_at_end=True if val_set_size > 0 else False,
            ddp_find_unused_parameters=False if ddp else None,
            group_by_length=group_by_length,
            report_to="wandb" if use_wandb else None,
            run_name=wandb_run_name if use_wandb else None,
            # max_grad_norm=5,        # 新加
        ),  
        data_collator=transformers.DataCollatorForSeq2Seq(
            tokenizer, pad_to_multiple_of=8, return_tensors="pt", padding=True
        ),
        # data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    )

    model.config.use_cache = False

    print(f"processing finetune, model: {base_model}, data: {data_path}")

    trainer.train(resume_from_checkpoint=resume_from_checkpoint)

    model.save_pretrained(output_dir)

    print(
        "\n If there's a warning about missing keys above, please disregard :)"
    )

# 一般需要修改的参数：模型，数据集，r，a，l，学习率，训练轮数，验证集大小

if __name__ == "__main__":
    
    model_dict = {
        "Mistral-7B-Instruct-v0.3": "/mnt/data/MODEL/mistralai/Mistral-7B-Instruct-v0.3",       # 0 mistr
        "Meta-Llama-3-8B-Instruct": "/mnt/data/MODEL/meta-llama/Meta-Llama-3-8B-Instruct",       # 1 llama
        "Qwen2-7B": "/mnt/data/MODEL/Qwen/Qwen2-7B",
        "Qwen2-7B-Instruct": "/mnt/data/MODEL/Qwen/Qwen2-7B-Instruct",
        "Qwen2.5-7B-Instruct": "/mnt/data/MODEL/Qwen/Qwen2.5-7B-Instruct",       # 2 qwen
        "llama-7b-hf": "/mnt/data/MODEL/yahma/llama-7b-hf",
        "Phi-3-small-8k-instruct": "/mnt/data/MODEL/microsoft/Phi-3-small-8k-instruct",
        "DeepSeek-R1-Distill-Llama-8B": "/mnt/data/MODEL/deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
    }
    
    """ 在这里修改你的训练数据集, 以alpaca形式! """
    # train_data_arr = [
    #     "emotion_chinese_2k",
    #     # "news-summarizer-reasoner",
    #     "news-summarizer-noreason",
    # ]
    
    model_name = args.model_name        # 现在默认是 DeepSeek-R1-Distill-Llama-8B
    print("model_name: ", model_name)
        
    new_template: bool = True
    # for data_id in train_data_arr:
    data_id = "emotion_chinese_2k"
    data_path = get_data_path(data_id)
    print("training data: ", data_id)
    print("data_path: ", data_path)
    
    # if new_template:
    output_dir = f"/mnt/data/computer_design/lora_checkpoints/{model_name}__{data_id}"
    train(
        base_model=model_dict.get(model_name),
        output_dir=output_dir,
        data_path=data_path,
        new_template=new_template,
        num_epochs=6,
    )

    data_id = "news-summarizer-noreason"
    # for data_id in train_data_arr:
    data_path = get_data_path(data_id)
    print("training data: ", data_id)
    print("data_path: ", data_path)
    
    # if new_template:
    output_dir = f"/mnt/data/computer_design/lora_checkpoints/{model_name}__{data_id}"
    train(
        base_model=model_dict.get(model_name),
        output_dir=output_dir,
        data_path=data_path,
        new_template=new_template,
        num_epochs=8,
    )