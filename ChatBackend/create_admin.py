#!/usr/bin/env python3
"""
创建管理员账号脚本
用法: python create_admin.py
"""

import os
import sys
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import User
from app.extensions import db
from app import create_app

def create_admin_user():
    """创建管理员用户"""
    
    # 管理员信息
    admin_email = "admin@whu.cn"
    admin_username = "admin"
    admin_password = "ant.design"
    
    print(f"开始创建管理员账号...")
    print(f"邮箱: {admin_email}")
    print(f"用户名: {admin_username}")
    
    try:
        # 创建Flask应用上下文
        app = create_app()
        
        with app.app_context():
            # 检查数据库连接状态
            if isinstance(db.db, dict):
                print("⚠️  MongoDB 连接失败，使用内存存储模式")
                # 初始化内存存储的集合
                if 'users' not in db.db:
                    db.db['users'] = {}
                    print("✅ 初始化内存用户集合")
            
            # 检查是否已存在该邮箱的用户
            existing_user = User.find_by_email(admin_email)
            if existing_user:
                print(f"⚠️  邮箱 {admin_email} 已存在用户")
                
                # 更新为管理员权限
                existing_user.role = 'admin'
                existing_user.set_password(admin_password)
                result = existing_user.save()
                
                if result:
                    print(f"✅ 已将现有用户更新为管理员权限")
                    print(f"用户ID: {existing_user._id}")
                    print(f"角色: {existing_user.role}")
                else:
                    print(f"❌ 更新用户失败")
                    return False
            else:
                # 检查用户名是否已存在
                existing_username = User.find_by_username(admin_username)
                if existing_username:
                    print(f"⚠️  用户名 {admin_username} 已存在，使用邮箱作为用户名")
                    admin_username = admin_email
                
                # 创建新的管理员用户
                admin_user = User(
                    username=admin_username,
                    email=admin_email,
                    role='admin'
                )
                
                # 设置密码
                admin_user.set_password(admin_password)
                
                # 保存到数据库
                result = admin_user.save()
                
                if result:
                    print(f"✅ 管理员账号创建成功!")
                    print(f"用户ID: {admin_user._id}")
                    print(f"用户名: {admin_user.username}")
                    print(f"邮箱: {admin_user.email}")
                    print(f"角色: {admin_user.role}")
                else:
                    print(f"❌ 管理员账号创建失败")
                    return False
            
            # 验证创建结果
            print("\n验证账号信息...")
            verify_user = User.find_by_email(admin_email)
            if verify_user and verify_user.role == 'admin':
                print(f"✅ 验证成功: 管理员账号已正确创建")
                
                # 测试密码
                if verify_user.check_password(admin_password):
                    print(f"✅ 密码验证成功")
                else:
                    print(f"❌ 密码验证失败")
                    return False
            else:
                print(f"❌ 验证失败: 无法找到管理员账号或角色不正确")
                return False
            
            return True
            
    except Exception as e:
        print(f"❌ 创建管理员账号时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("管理员账号创建工具")
    print("=" * 50)
    
    success = create_admin_user()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 管理员账号创建完成!")
        print("\n登录信息:")
        print("邮箱: admin@whu.cn")
        print("密码: ant.design")
        print("角色: admin")
    else:
        print("❌ 管理员账号创建失败!")
        sys.exit(1)
    print("=" * 50)

if __name__ == "__main__":
    main()
