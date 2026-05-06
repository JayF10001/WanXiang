from datetime import datetime
from flask_login import UserMixin
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from bson import ObjectId
import os
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db # Import the db object from Flask-PyMongo

class User(UserMixin):
    def __init__(self, username, email, password_hash=None, id=None, role='user'):
        self.username = username
        self.email = email
        self.password_hash = password_hash
        if id is None:
            self._id = ObjectId()
        elif isinstance(id, ObjectId):
            self._id = id
        else:
            try:
                self._id = ObjectId(id)
            except Exception:
                # In fallback in-memory mode, IDs are plain strings.
                self._id = str(id)
        self.role = role

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash and check_password_hash(self.password_hash, password)

    def save(self):
        user_data = self.__dict__.copy() # Use copy to avoid modifying original dict
        user_data['_id'] = self._id # Ensure _id is ObjectId
        if 'role' not in user_data: user_data['role'] = 'user' 
        
        print(f"[DEBUG] User.save: Attempting to save/update user with data: {user_data}") # Log data
        try:
            # 尝试先查找用户是否存在
            existing_user = db.users.find_one({"_id": self._id})
            if existing_user:
                # 用户存在，更新用户信息
                result = db.users.update_one({"_id": self._id}, {"$set": user_data})
                print(f"[DEBUG] User.save: update_one result: matched={result.matched_count}, modified={result.modified_count}")
            else:
                # 用户不存在，插入新用户
                result = db.users.insert_one(user_data)
                print(f"[DEBUG] User.save: insert_one result: inserted_id={result.inserted_id}")
                if result.inserted_id:
                    self._id = result.inserted_id
            return result
        except Exception as e:
            print(f"[DEBUG] User.save: Error during save: {e}") # Log errors
            # 尝试使用内存存储模式作为后备
            try:
                print(f"[DEBUG] User.save: Trying in-memory storage as fallback")
                # 检查是否使用内存存储模式
                if hasattr(db.db, '_collections') and 'users' in db.db._collections:
                    users_collection = db.db._collections['users']
                    # 检查用户是否存在
                    existing_user = users_collection.find_one({"_id": str(self._id)})
                    if existing_user:
                        # 更新用户
                        users_collection.update_one({"_id": str(self._id)}, {"$set": user_data})
                    else:
                        # 插入新用户
                        user_data['_id'] = str(self._id)
                        users_collection.insert_one(user_data)
                    print(f"[DEBUG] User.save: Saved to in-memory storage")
                    return True
            except Exception as fallback_e:
                print(f"[DEBUG] User.save: Fallback to in-memory storage failed: {fallback_e}")
            # Optionally re-raise the exception or return an error indicator
            return None 
        
    @classmethod
    def find_by_username(cls, username):
        user_data = db.users.find_one({"username": username})
        if user_data:
            user_data['role'] = user_data.get('role', 'user') 
            return cls(**user_data)
        return None

    @classmethod
    def find_by_email(cls, email):
        # 处理内存模式和MongoDB模式
        if hasattr(db.db, '_collections'):
            users_collection = getattr(db.db, 'users', None)
            if not users_collection:
                return None

            user_data = users_collection.find_one({"email": email})
            if user_data:
                filtered_data = {
                    'username': user_data.get('username'),
                    'email': user_data.get('email'),
                    'password_hash': user_data.get('password_hash'),
                    'role': user_data.get('role', 'user'),
                    'id': user_data.get('_id'),
                }
                return cls(**filtered_data)
            return None

        # MongoDB模式
        user_data = db.users.find_one({"email": email})
        if user_data:
            user_data['role'] = user_data.get('role', 'user')
            return cls(**user_data)
        return None

    @classmethod
    def get(cls, user_id):
        print(f"[DEBUG] User.get called with user_id (string): {user_id}") # Log input string ID
        try:
            # 处理内存模式和MongoDB模式
            if hasattr(db.db, '_collections'):
                # 内存模式
                users_collection = getattr(db.db, 'users', None)
                if not users_collection:
                    print(f"[DEBUG] User.get: No users collection in memory mode")
                    return None

                user_data = users_collection.find_one({"_id": user_id})
                if not user_data and str(user_id) != user_id:
                    user_data = users_collection.find_one({"_id": str(user_id)})

                if user_data:
                    user_data = user_data.copy()  # 复制以避免修改原数据
                    print(f"[DEBUG] User.get: Found user in memory mode: {user_data}")

                    # 提取_id并设置role
                    db_id = user_data.pop('_id', None)
                    if db_id is None:
                        print(f"[DEBUG] User.get: Warning - _id field missing in user_data")
                        return None

                    # 只保留User.__init__需要的参数
                    filtered_data = {
                        'username': user_data.get('username'),
                        'email': user_data.get('email'),
                        'password_hash': user_data.get('password_hash'),
                        'role': user_data.get('role', 'user'),
                        'id': db_id
                    }
                    instance = cls(**filtered_data)
                    print(f"[DEBUG] User.get: User object created successfully in memory mode: {instance}")
                    return instance
                else:
                    print(f"[DEBUG] User.get: User {user_id} not found in memory mode")
                    return None
            else:
                # MongoDB模式
                query_id = ObjectId(user_id) # Attempt conversion first
                print(f"[DEBUG] User.get: Attempting find_one with _id (ObjectId): {query_id}") # Log the ObjectId being used
                
                user_data = db.users.find_one({"_id": query_id})
                
                print(f"[DEBUG] User.get: find_one result for _id {query_id}: {user_data}") # Log the raw find_one result

                if user_data:
                    print(f"[DEBUG] User.get: User data found. Preparing to instantiate User object.")
                    try:
                        # --- Correct instantiation --- 
                        # 1. Extract the _id value
                        db_id = user_data.pop('_id', None) # Use pop to remove _id from the dict
                        if db_id is None:
                             print(f"[DEBUG] User.get: Warning - _id field missing in user_data retrieved from DB.")
                             return None # Cannot proceed without ID
                        
                        # 2. Ensure role exists
                        user_data['role'] = user_data.get('role', 'user') 
                        
                        # 3. Instantiate User, passing db_id to the 'id' parameter
                        instance = cls(id=db_id, **user_data) 
                        # ----------------------------- 
                        
                        print(f"[DEBUG] User.get: User object instantiated successfully: {instance}")
                        return instance
                    except Exception as instantiation_error:
                        print(f"[DEBUG] User.get: Error during User object instantiation: {instantiation_error}") # Log instantiation error
                        # print(f"[DEBUG] User.get: Data causing instantiation error: {user_data}") # user_data no longer has _id here
                        return None # Instantiation failed
                else:
                    print(f"[DEBUG] User.get: No user found in db for _id {query_id}")
                    return None # Explicitly return None if user_data is None

        except Exception as e:
            print(f"[DEBUG] User.get: General error (e.g., ObjectId conversion) for user_id {user_id}: {e}") # Log conversion or other errors
            return None

    def get_id(self):
        return str(self._id)

    @property
    def is_admin(self):
        return hasattr(self, 'role') and self.role == 'admin'

class News:
    def __init__(self, title, content, url, source=None, published_at=None, 
                 sentiment_score=None, category=None, keywords=None, _id=None):
        self.title = title
        self.content = content
        self.url = url
        self.source = source
        self.published_at = published_at or datetime.utcnow()
        self.sentiment_score = sentiment_score
        self.category = category
        self.keywords = keywords or []
        self._id = _id

    def save(self):
        if not self._id:
            result = db.news.insert_one({
                'title': self.title,
                'content': self.content,
                'url': self.url,
                'source': self.source,
                'published_at': self.published_at,
                'sentiment_score': self.sentiment_score,
                'category': self.category,
                'keywords': self.keywords,
                'created_at': datetime.utcnow()
            })
            self._id = result.inserted_id
        else:
            db.news.update_one(
                {'_id': self._id},
                {'$set': {
                    'title': self.title,
                    'content': self.content,
                    'url': self.url,
                    'source': self.source,
                    'published_at': self.published_at,
                    'sentiment_score': self.sentiment_score,
                    'category': self.category,
                    'keywords': self.keywords
                }}
            )

class Chat:
    def __init__(self, user_id, query, response, related_news=None, _id=None):
        self.user_id = user_id
        self.query = query
        self.response = response
        self.related_news = related_news or []
        self._id = _id
        self.created_at = datetime.utcnow()

    def save(self):
        if not self._id:
            result = db.chats.insert_one({
                'user_id': self.user_id,
                'query': self.query,
                'response': self.response,
                'related_news': self.related_news,
                'created_at': self.created_at
            })
            self._id = result.inserted_id
        else:
            db.chats.update_one(
                {'_id': self._id},
                {'$set': {
                    'user_id': self.user_id,
                    'query': self.query,
                    'response': self.response,
                    'related_news': self.related_news
                }}
            )

class Trend:
    def __init__(self, keyword, frequency=0, category=None, _id=None):
        self.keyword = keyword
        self.frequency = frequency
        self.category = category
        self._id = _id
        self.last_updated = datetime.utcnow()

    def save(self):
        if not self._id:
            result = db.trends.insert_one({
                'keyword': self.keyword,
                'frequency': self.frequency,
                'category': self.category,
                'last_updated': self.last_updated
            })
            self._id = result.inserted_id
        else:
            db.trends.update_one(
                {'_id': self._id},
                {'$set': {
                    'keyword': self.keyword,
                    'frequency': self.frequency,
                    'category': self.category,
                    'last_updated': self.last_updated
                }}
            )
