#!/usr/bin/env python3
"""
手动测试Celery任务脚本
使用方法: python test_celery_tasks.py [task_name]
"""

import sys
import time
from celery_app import celery
from app.tasks import (
    heartbeat, 
    collect_news_task, 
    batch_analyze_news_task, 
    full_process_task
)

def test_heartbeat():
    """测试心跳任务"""
    print("🔄 测试心跳任务...")
    try:
        result = heartbeat.delay()
        print(f"任务ID: {result.id}")
        
        # 等待结果
        task_result = result.get(timeout=30)
        print(f"✅ 心跳任务完成: {task_result}")
        return True
    except Exception as e:
        print(f"❌ 心跳任务失败: {str(e)}")
        return False

def test_collect_news():
    """测试新闻采集任务"""
    print("📰 测试新闻采集任务...")
    try:
        result = collect_news_task.delay()
        print(f"任务ID: {result.id}")
        
        # 等待结果（给更多时间）
        task_result = result.get(timeout=120)
        print(f"✅ 新闻采集完成: {task_result}")
        return True
    except Exception as e:
        print(f"❌ 新闻采集失败: {str(e)}")
        return False

def test_analyze_news(limit=5):
    """测试新闻分析任务"""
    print(f"🤖 测试新闻分析任务（限制{limit}条）...")
    try:
        result = batch_analyze_news_task.delay(limit=limit)
        print(f"任务ID: {result.id}")
        
        # 等待结果（分析需要更多时间）
        task_result = result.get(timeout=300)
        print(f"✅ 新闻分析完成: {task_result}")
        return True
    except Exception as e:
        print(f"❌ 新闻分析失败: {str(e)}")
        return False

def test_full_process():
    """测试完整流程任务"""
    print("🚀 测试完整流程任务（采集 -> 分析）...")
    try:
        result = full_process_task.delay(collect_limit=30, analyze_limit=5)
        print(f"任务ID: {result.id}")
        
        # 等待结果（完整流程需要最多时间）
        task_result = result.get(timeout=600)
        print(f"✅ 完整流程完成: {task_result}")
        return True
    except Exception as e:
        print(f"❌ 完整流程失败: {str(e)}")
        return False

def check_celery_status():
    """检查Celery状态"""
    print("🔍 检查Celery状态...")
    try:
        # 检查活跃的工作进程
        inspect = celery.control.inspect()
        active = inspect.active()
        if active:
            print(f"✅ 找到活跃的工作进程: {list(active.keys())}")
        else:
            print("⚠️  没有找到活跃的工作进程")
        
        # 检查已注册的任务
        registered = inspect.registered()
        if registered:
            for worker, tasks in registered.items():
                print(f"📋 工作进程 {worker} 已注册任务: {len(tasks)} 个")
        
        return bool(active)
    except Exception as e:
        print(f"❌ 检查Celery状态失败: {str(e)}")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("🧪 Celery任务测试工具")
    print("=" * 50)
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        task_name = sys.argv[1].lower()
    else:
        task_name = "all"
    
    # 检查Celery状态
    if not check_celery_status():
        print("\n⚠️  警告: Celery似乎没有运行。请确保:")
        print("   1. Redis正在运行")
        print("   2. Celery worker已启动: celery -A celery_app worker --loglevel=info")
        print("   3. 或者使用docker-compose启动服务")
        return
    
    print("\n" + "─" * 30)
    
    # 根据参数运行不同的测试
    if task_name == "heartbeat":
        test_heartbeat()
    elif task_name == "collect":
        test_collect_news()
    elif task_name == "analyze":
        test_analyze_news()
    elif task_name == "full":
        test_full_process()
    elif task_name == "all":
        print("🔄 运行所有测试...")
        
        # 1. 心跳测试
        if test_heartbeat():
            print("✅ 心跳测试通过\n")
        
        # 2. 采集测试
        if test_collect_news():
            print("✅ 采集测试通过\n")
            
            # 等待一点时间让数据保存
            time.sleep(2)
            
            # 3. 分析测试
            if test_analyze_news(limit=3):
                print("✅ 分析测试通过\n")
        
        print("🎉 所有测试完成!")
    else:
        print(f"❌ 未知任务: {task_name}")
        print("可用任务: heartbeat, collect, analyze, full, all")

if __name__ == "__main__":
    main()
