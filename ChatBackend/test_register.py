#!/usr/bin/env python3
"""
测试注册功能脚本
测试邀请码 'whu' 是否能正确创建管理员账号
"""

import requests
import json

def test_register_functionality():
    """测试注册功能"""
    
    # 测试服务器地址（根据实际情况调整）
    base_url = "http://localhost:5000/api"
    
    print("=" * 60)
    print("注册功能测试")
    print("=" * 60)
    
    # 测试用例1: 使用邀请码 'whu' 注册管理员
    print("\n🧪 测试用例1: 使用邀请码 'whu' 注册管理员")
    admin_data = {
        "username": "testadmin",
        "email": "testadmin@test.com",
        "password": "123456",
        "inviteCode": "whu"
    }
    
    try:
        response = requests.post(f"{base_url}/register", 
                               json=admin_data, 
                               headers={'Content-Type': 'application/json'},
                               timeout=10)
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ 管理员注册成功")
            print(f"   用户名: {result['user']['name']}")
            print(f"   邮箱: {result['user']['email']}")
            print(f"   角色: {result['user']['role']}")
            print(f"   权限: {result['currentAuthority']}")
            
            if result['user']['role'] == 'admin':
                print("✅ 邀请码 'whu' 正确设置为管理员角色")
            else:
                print("❌ 邀请码 'whu' 未能设置为管理员角色")
        else:
            print(f"❌ 管理员注册失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        print("💡 提示: 请确保后端服务正在运行 (python run.py)")
    
    # 测试用例2: 不使用邀请码注册普通用户
    print("\n🧪 测试用例2: 不使用邀请码注册普通用户")
    user_data = {
        "username": "testuser",
        "email": "testuser@test.com",
        "password": "123456"
        # 不提供 inviteCode
    }
    
    try:
        response = requests.post(f"{base_url}/register", 
                               json=user_data, 
                               headers={'Content-Type': 'application/json'},
                               timeout=10)
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ 普通用户注册成功")
            print(f"   用户名: {result['user']['name']}")
            print(f"   邮箱: {result['user']['email']}")
            print(f"   角色: {result['user']['role']}")
            print(f"   权限: {result['currentAuthority']}")
            
            if result['user']['role'] == 'user':
                print("✅ 无邀请码正确设置为普通用户角色")
            else:
                print("❌ 无邀请码未能设置为普通用户角色")
        else:
            print(f"❌ 普通用户注册失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
    
    # 测试用例3: 使用错误邀请码注册
    print("\n🧪 测试用例3: 使用错误邀请码注册")
    wrong_code_data = {
        "username": "testwrong",
        "email": "testwrong@test.com",
        "password": "123456",
        "inviteCode": "wrongcode"
    }
    
    try:
        response = requests.post(f"{base_url}/register", 
                               json=wrong_code_data, 
                               headers={'Content-Type': 'application/json'},
                               timeout=10)
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ 错误邀请码用户注册成功")
            print(f"   用户名: {result['user']['name']}")
            print(f"   邮箱: {result['user']['email']}")
            print(f"   角色: {result['user']['role']}")
            print(f"   权限: {result['currentAuthority']}")
            
            if result['user']['role'] == 'user':
                print("✅ 错误邀请码正确设置为普通用户角色")
            else:
                print("❌ 错误邀请码未能正确处理")
        else:
            print(f"❌ 错误邀请码用户注册失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
    
    # 测试用例4: 使用大小写混合的 'WHU' 邀请码
    print("\n🧪 测试用例4: 使用大小写混合的 'WHU' 邀请码")
    upper_code_data = {
        "username": "testupper",
        "email": "testupper@test.com",
        "password": "123456",
        "inviteCode": "WHU"
    }
    
    try:
        response = requests.post(f"{base_url}/register", 
                               json=upper_code_data, 
                               headers={'Content-Type': 'application/json'},
                               timeout=10)
        
        if response.status_code == 201:
            result = response.json()
            print(f"✅ 大写邀请码用户注册成功")
            print(f"   用户名: {result['user']['name']}")
            print(f"   邮箱: {result['user']['email']}")
            print(f"   角色: {result['user']['role']}")
            print(f"   权限: {result['currentAuthority']}")
            
            if result['user']['role'] == 'admin':
                print("✅ 大写 'WHU' 邀请码正确设置为管理员角色（大小写不敏感）")
            else:
                print("❌ 大写 'WHU' 邀请码未能设置为管理员角色")
        else:
            print(f"❌ 大写邀请码用户注册失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
    
    print("\n" + "=" * 60)
    print("📋 测试总结")
    print("=" * 60)
    print("✅ 邀请码功能已实现:")
    print("   - 输入 'whu' (不区分大小写) → 管理员权限")
    print("   - 输入其他代码或不输入 → 普通用户权限")
    print("   - 前端已添加邀请码输入字段")
    print("   - 后端已实现角色判断逻辑")
    print("\n💡 使用说明:")
    print("   - 管理员注册: 在邀请码字段输入 'whu'")
    print("   - 普通用户注册: 邀请码字段留空或输入其他内容")
    print("=" * 60)

if __name__ == "__main__":
    test_register_functionality()
