#!/usr/bin/env python3
"""
测试前端API接口脚本
验证重构后的API接口是否正常工作
"""

import requests
import json
import time

# 配置
BASE_URL = "http://localhost:5000/api"  # 根据实际部署调整
LOGIN_URL = f"{BASE_URL}/login/account"
HEADERS = {"Content-Type": "application/json"}

def login_and_get_token():
    """登录并获取会话"""
    login_data = {
        "email": "test@example.com",
        "password": "password123",
        "type": "account"
    }
    
    try:
        response = requests.post(LOGIN_URL, json=login_data, headers=HEADERS)
        print(f"登录状态: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ 登录成功")
            return response.cookies
        else:
            print("❌ 登录失败，使用匿名访问测试")
            return None
    except Exception as e:
        print(f"❌ 登录错误: {str(e)}")
        return None

def test_collect_news(cookies=None):
    """测试新闻采集接口"""
    print("\n📰 测试新闻采集接口...")
    try:
        response = requests.post(
            f"{BASE_URL}/collect_news", 
            headers=HEADERS,
            cookies=cookies,
            timeout=60
        )
        
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 采集成功: {result}")
            return True
        else:
            print(f"❌ 采集失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 采集请求错误: {str(e)}")
        return False

def test_analyze_news(cookies=None):
    """测试新闻分析接口"""
    print("\n🤖 测试新闻分析接口...")
    try:
        data = {"limit": 5}
        response = requests.post(
            f"{BASE_URL}/analyze_hot_news", 
            json=data,
            headers=HEADERS,
            cookies=cookies,
            timeout=120
        )
        
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 分析成功: {result}")
            return True
        else:
            print(f"❌ 分析失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 分析请求错误: {str(e)}")
        return False

def test_full_process(cookies=None):
    """测试完整流程接口"""
    print("\n🚀 测试完整流程接口...")
    try:
        data = {"collect_limit": 30, "analyze_limit": 5}
        response = requests.post(
            f"{BASE_URL}/full_process", 
            json=data,
            headers=HEADERS,
            cookies=cookies,
            timeout=180
        )
        
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 完整流程成功: {result}")
            return True
        else:
            print(f"❌ 完整流程失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 完整流程请求错误: {str(e)}")
        return False

def test_get_current_news(cookies=None):
    """测试获取当前新闻接口"""
    print("\n📋 测试获取当前新闻接口...")
    try:
        response = requests.get(
            f"{BASE_URL}/currentnews", 
            headers=HEADERS,
            cookies=cookies,
            timeout=30
        )
        
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            data = result.get("data", [])
            print(f"✅ 获取成功: 返回{len(data)}条新闻")
            
            # 显示前3条新闻的标题
            for i, news in enumerate(data[:3]):
                title = news.get("title", "无标题")
                print(f"   {i+1}. {title[:50]}...")
            
            return True
        else:
            print(f"❌ 获取失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 获取请求错误: {str(e)}")
        return False

def test_get_analyzed_news(cookies=None):
    """测试获取已分析新闻接口"""
    print("\n📊 测试获取已分析新闻接口...")
    try:
        response = requests.get(
            f"{BASE_URL}/analyze_news", 
            headers=HEADERS,
            cookies=cookies,
            timeout=30
        )
        
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            data = result.get("data", [])
            print(f"✅ 获取成功: 返回{len(data)}条已分析新闻")
            
            # 显示分析结果样例
            for i, news in enumerate(data[:2]):
                title = news.get("title", "无标题")
                participants = news.get("participants", 0)
                emotion = news.get("emotion", {})
                print(f"   {i+1}. {title[:30]}... (参与度: {participants:.3f})")
            
            return True
        else:
            print(f"❌ 获取失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 获取请求错误: {str(e)}")
        return False

def test_update_flow(cookies=None):
    """测试更新流程"""
    print("\n🔄 测试完整更新流程...")
    try:
        # 带update参数的currentnews请求会触发完整流程
        response = requests.get(
            f"{BASE_URL}/currentnews?update=true", 
            headers=HEADERS,
            cookies=cookies,
            timeout=300
        )
        
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            data = result.get("data", [])
            print(f"✅ 更新流程成功: 返回{len(data)}条新闻")
            return True
        else:
            print(f"❌ 更新流程失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 更新流程错误: {str(e)}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("🧪 前端API接口测试工具")
    print("=" * 60)
    
    # 尝试登录
    cookies = login_and_get_token()
    
    print("\n" + "─" * 40)
    
    # 运行测试
    results = []
    
    # 1. 测试基础接口
    results.append(("采集新闻", test_collect_news(cookies)))
    time.sleep(2)  # 等待数据保存
    
    results.append(("分析新闻", test_analyze_news(cookies)))
    time.sleep(2)  # 等待分析完成
    
    # 2. 测试获取接口
    results.append(("获取当前新闻", test_get_current_news(cookies)))
    results.append(("获取已分析新闻", test_get_analyzed_news(cookies)))
    
    # 3. 测试完整流程
    results.append(("完整流程", test_full_process(cookies)))
    
    # 4. 测试更新流程
    results.append(("更新流程", test_update_flow(cookies)))
    
    # 显示测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:<15} {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 项测试通过")
    
    if passed == len(results):
        print("🎉 所有API接口测试通过！")
    else:
        print("⚠️  部分测试失败，请检查服务状态")

if __name__ == "__main__":
    main()
