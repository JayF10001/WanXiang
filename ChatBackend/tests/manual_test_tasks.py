#!/usr/bin/env python3
"""
手动测试定时任务
此脚本用于在独立环境中测试各个任务的执行情况
"""
import os
import sys
import time
import argparse
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 导入Flask应用
from app import create_app
from app.tasks import (
    heartbeat,
    collect_news_task,
    smart_collect_news_task,
    analyze_trending_news_task,
    process_news_task
)

# 创建Flask应用实例
app = create_app()

def run_task(task_name, force=False):
    """
    运行指定的任务
    
    Args:
        task_name: 任务名称
        force: 是否强制执行（适用于智能采集任务）
    """
    print(f"\n{'='*50}")
    print(f"开始执行任务: {task_name}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    start_time = time.time()
    
    # 在应用上下文中运行任务
    with app.app_context():
        try:
            # 根据任务名称调用对应的函数
            if task_name == "heartbeat":
                result = heartbeat()
            elif task_name == "collect_news":
                result = collect_news_task()
            elif task_name == "smart_collect_news":
                # 如果强制执行，修改智能采集任务的实现
                if force:
                    from app.services.news_collection_service import NewsCollectionService
                    result = NewsCollectionService.smart_collect_news(force=True)
                else:
                    result = smart_collect_news_task()
            elif task_name == "analyze_trending_news":
                result = analyze_trending_news_task()
            elif task_name == "process_news":
                result = process_news_task()
            else:
                print(f"错误: 未知任务 '{task_name}'")
                return
            
            # 计算执行时间
            execution_time = time.time() - start_time
            
            # 打印结果和执行时间
            print(f"\n{'='*50}")
            print(f"任务执行完成: {task_name}")
            print(f"执行时间: {execution_time:.2f} 秒")
            print(f"结果: {result}")
            print(f"{'='*50}\n")
            
        except Exception as e:
            print(f"\n{'='*50}")
            print(f"任务执行出错: {task_name}")
            print(f"错误信息: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"{'='*50}\n")

def monitor_task_execution(task_name, interval=60, count=5):
    """
    以指定的间隔连续执行任务多次，用于监控任务行为
    
    Args:
        task_name: 任务名称
        interval: 执行间隔（秒）
        count: 执行次数
    """
    print(f"开始监控任务 {task_name}，每 {interval} 秒执行一次，共 {count} 次")
    
    for i in range(count):
        print(f"\n执行第 {i+1}/{count} 次:")
        run_task(task_name)
        
        if i < count - 1:
            print(f"等待 {interval} 秒...")
            time.sleep(interval)
    
    print(f"\n监控任务 {task_name} 完成，共执行 {count} 次")

def run_all_tasks():
    """运行所有任务"""
    tasks = [
        "heartbeat",
        "collect_news",
        "smart_collect_news",
        "analyze_trending_news",
        "process_news"
    ]
    
    for task in tasks:
        run_task(task)
        # 稍微等待一下，避免任务之间相互干扰
        time.sleep(3)

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="手动测试定时任务")
    
    # 添加任务参数
    parser.add_argument(
        "task",
        choices=["heartbeat", "collect_news", "smart_collect_news", 
                "analyze_trending_news", "process_news", "all", "monitor"],
        help="要执行的任务名称"
    )
    
    # 添加监控相关参数
    parser.add_argument(
        "--interval", 
        type=int, 
        default=60,
        help="监控模式下的执行间隔（秒），默认为60秒"
    )
    
    parser.add_argument(
        "--count", 
        type=int, 
        default=5,
        help="监控模式下的执行次数，默认为5次"
    )
    
    parser.add_argument(
        "--monitor-task", 
        choices=["heartbeat", "collect_news", "smart_collect_news", 
                "analyze_trending_news", "process_news"],
        default="smart_collect_news",
        help="监控模式下要执行的任务，默认为smart_collect_news"
    )
    
    # 添加强制执行标志
    parser.add_argument(
        "--force", 
        action="store_true",
        help="强制执行任务，忽略智能任务中的检查"
    )
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if args.task == "all":
        run_all_tasks()
    elif args.task == "monitor":
        monitor_task_execution(args.monitor_task, args.interval, args.count)
    else:
        run_task(args.task, args.force) 