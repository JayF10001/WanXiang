from openai import OpenAI
import os
import base64
import json

# 不同模型的价格配置（按每千tokens计费，单位：人民币元）
MODEL_PRICING = {
    "qwen2.5-vl-72b-instruct": {
        "input": 0.00413,  # 输入token价格（每千tokens）
        "output": 0.00413,  # 输出token价格（每千tokens）
    }
}

#  Base64 编码格式
def encode_video(video_path):
    with open(video_path, "rb") as video_file:
        return base64.b64encode(video_file.read()).decode("utf-8")

# 计算费用函数
def calculate_cost(model_name, input_tokens, output_tokens):
    if model_name not in MODEL_PRICING:
        return "未知模型，无法计算费用"
    
    pricing = MODEL_PRICING[model_name]
    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    total_cost = input_cost + output_cost
    
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost
    }

# 将xxxx/test.mp4替换为你本地视频的绝对路径
base64_video = encode_video("./video.mp4")
client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx"
    api_key="sk-f5c8b29174b9418990c391328eade261",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
completion = client.chat.completions.create(
    model="qwen2.5-vl-72b-instruct",
    messages=[
        {
            "role": "system",
            "content": [{"type":"text","text": "You are a helpful assistant."}]},
        {
            "role": "user",
            "content": [
                {
                    # 直接传入视频文件时，请将type的值设置为video_url
                    "type": "video_url",
                    "video_url": {"url": f"data:video/mp4;base64,{base64_video}"},
                },
                {"type": "text", "text": "分析下这段视频的不足?"},
            ],
        }
    ],
)

# 打印回答内容
print("\n=== 模型回答 ===")
print(completion.choices[0].message.content)

# 获取token使用情况
tokens_info = completion.usage
input_tokens = tokens_info.prompt_tokens
output_tokens = tokens_info.completion_tokens
total_tokens = tokens_info.total_tokens

# 计算费用
model_name = "qwen2.5-vl-72b-instruct"
cost = calculate_cost(model_name, input_tokens, output_tokens)

# 打印token和费用信息
print("\n=== Token使用情况 ===")
print(f"输入tokens: {input_tokens}")
print(f"输出tokens: {output_tokens}")
print(f"总tokens: {total_tokens}")

print("\n=== 费用计算(人民币) ===")
print(f"输入费用: {cost['input_cost']:.4f} 元")
print(f"输出费用: {cost['output_cost']:.4f} 元")
print(f"总费用: {cost['total_cost']:.4f} 元")