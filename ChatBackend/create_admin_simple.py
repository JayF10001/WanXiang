#!/usr/bin/env python3
"""
简单的管理员账号创建脚本 - 适配内存存储模式
用法: python create_admin_simple.py
"""

import os
import sys
from datetime import datetime
from bson import ObjectId
from werkzeug.security import generate_password_hash

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.extensions import db
from app import create_app

def create_admin_user_simple():
    """创建管理员用户 - 简单版本"""
    
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
                
                # 生成用户ID
                user_id = ObjectId()
                
                # 创建用户数据
                user_data = {
                    '_id': user_id,
                    'username': admin_username,
                    'email': admin_email,
                    'password_hash': generate_password_hash(admin_password),
                    'role': 'admin',
                    'created_at': datetime.utcnow()
                }
                
                # 检查邮箱是否已存在
                existing_user = None
                for uid, udata in db.db['users'].items():
                    if udata.get('email') == admin_email:
                        existing_user = (uid, udata)
                        break
                
                if existing_user:
                    uid, udata = existing_user
                    print(f"⚠️  邮箱 {admin_email} 已存在用户，更新为管理员权限")
                    
                    # 更新现有用户
                    db.db['users'][uid].update({
                        'password_hash': generate_password_hash(admin_password),
                        'role': 'admin',
                        'updated_at': datetime.utcnow()
                    })
                    
                    print(f"✅ 已将现有用户更新为管理员权限")
                    print(f"用户ID: {uid}")
                    print(f"角色: admin")
                else:
                    # 检查用户名是否已存在
                    existing_username = None
                    for uid, udata in db.db['users'].items():
                        if udata.get('username') == admin_username:
                            existing_username = True
                            break
                    
                    if existing_username:
                        print(f"⚠️  用户名 {admin_username} 已存在，使用邮箱作为用户名")
                        user_data['username'] = admin_email
                    
                    # 保存新用户到内存存储
                    db.db['users'][str(user_id)] = user_data
                    
                    print(f"✅ 管理员账号创建成功!")
                    print(f"用户ID: {user_id}")
                    print(f"用户名: {user_data['username']}")
                    print(f"邮箱: {user_data['email']}")
                    print(f"角色: {user_data['role']}")
                
                # 验证创建结果
                print("\n验证账号信息...")
                verify_user = None
                for uid, udata in db.db['users'].items():
                    if udata.get('email') == admin_email:
                        verify_user = udata
                        break
                
                if verify_user and verify_user.get('role') == 'admin':
                    print(f"✅ 验证成功: 管理员账号已正确创建")
                    print(f"✅ 密码已加密存储")
                    
                    # 显示当前所有用户
                    print(f"\n当前内存中的用户数量: {len(db.db['users'])}")
                    for uid, udata in db.db['users'].items():
                        print(f"  - {udata.get('username', 'N/A')} ({udata.get('email', 'N/A')}) - {udata.get('role', 'user')}")
                else:
                    print(f"❌ 验证失败: 无法找到管理员账号或角色不正确")
                    return False
                
            else:
                print("✅ MongoDB 连接正常")
                # 这里可以添加 MongoDB 模式下的用户创建逻辑
                print("⚠️  MongoDB 模式下的用户创建功能待实现")
                return False
            
            return True
            
    except Exception as e:
        print(f"❌ 创建管理员账号时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("管理员账号创建工具 (简化版)")
    print("=" * 60)
    
    success = create_admin_user_simple()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 管理员账号创建完成!")
        print("\n登录信息:")
        print("邮箱: admin@whu.cn")
        print("密码: ant.design")
        print("角色: admin")
        print("\n⚠️  注意: 当前使用内存存储，重启应用后数据将丢失!")
        print("建议在 MongoDB 连接正常后重新创建管理员账号。")
    else:
        print("❌ 管理员账号创建失败!")
        sys.exit(1)
    print("=" * 60)

if __name__ == "__main__":
    main()
