#!/usr/bin/env python3
"""
运行所有任务测试的脚本
生成详细的测试报告
"""
import os
import sys
import unittest
import datetime
import HtmlTestRunner

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 导入测试用例
from test_scheduled_tasks import TestScheduledTasks, TestMockData

def run_tests():
    """
    运行所有测试并生成报告
    """
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加所有的测试用例
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestScheduledTasks))
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestMockData))
    
    # 设置报告输出目录
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
    
    # 设置报告文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"task_tests_report_{timestamp}"
    
    # 运行测试并生成报告
    runner = HtmlTestRunner.HTMLTestRunner(
        output=report_dir,
        report_name=report_name,
        report_title="定时任务测试报告",
        combine_reports=True,
        template_args={
            "favicon": False,
            "author": "News Backend System"
        }
    )
    
    result = runner.run(suite)
    return result

def run_single_test(test_case, test_method=None):
    """
    运行单个测试用例
    
    Args:
        test_case: 测试用例类
        test_method: 测试方法名（可选）
    """
    if test_method:
        suite = unittest.TestSuite()
        suite.addTest(test_case(test_method))
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_case)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result

def get_available_tests():
    """
    获取所有可用的测试
    
    Returns:
        dict: 包含所有测试类和方法的字典
    """
    tests = {}
    
    # 收集TestScheduledTasks的测试方法
    tests["TestScheduledTasks"] = []
    for method in dir(TestScheduledTasks):
        if method.startswith("test_"):
            tests["TestScheduledTasks"].append(method)
    
    # 收集TestMockData的测试方法
    tests["TestMockData"] = []
    for method in dir(TestMockData):
        if method.startswith("test_"):
            tests["TestMockData"].append(method)
    
    return tests

def print_usage():
    """
    打印使用说明
    """
    print("测试运行器使用说明:")
    print("-------------------------------")
    print("运行所有测试:")
    print("  python run_tests.py all")
    print()
    print("运行特定测试类:")
    print("  python run_tests.py TestScheduledTasks")
    print()
    print("运行特定测试方法:")
    print("  python run_tests.py TestScheduledTasks.test_heartbeat")
    print()
    print("可用的测试:")
    tests = get_available_tests()
    for test_class, methods in tests.items():
        print(f"  {test_class}:")
        for method in methods:
            print(f"    - {method}")

if __name__ == "__main__":
    # 查看是否有命令行参数
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print_usage()
        sys.exit(0)
    
    # 根据命令行参数运行测试
    test_target = sys.argv[1]
    
    if test_target == "all":
        # 运行所有测试
        result = run_tests()
        sys.exit(0 if result.wasSuccessful() else 1)
    
    # 运行特定测试类或方法
    if "." in test_target:
        # 运行特定测试方法
        class_name, method_name = test_target.split(".")
        if class_name == "TestScheduledTasks":
            result = run_single_test(TestScheduledTasks, method_name)
        elif class_name == "TestMockData":
            result = run_single_test(TestMockData, method_name)
        else:
            print(f"错误: 未知的测试类 '{class_name}'")
            print_usage()
            sys.exit(1)
    else:
        # 运行特定测试类
        if test_target == "TestScheduledTasks":
            result = run_single_test(TestScheduledTasks)
        elif test_target == "TestMockData":
            result = run_single_test(TestMockData)
        else:
            print(f"错误: 未知的测试目标 '{test_target}'")
            print_usage()
            sys.exit(1)
    
    sys.exit(0 if result.wasSuccessful() else 1) 