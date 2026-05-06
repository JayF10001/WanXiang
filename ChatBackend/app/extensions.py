from flask import Flask
from flask import current_app
import pymongo
from pymongo import MongoClient
import os
from flask_login import LoginManager
import logging

# 创建LoginManager实例
login_manager = LoginManager()

# Database object that will be used across the application
class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self._collections = {}
        self.mode = "uninitialized"
    
    def init_app(self, app):
        try:
            # 优先使用环境变量中的MongoDB URI
            mongodb_uri = os.environ.get('MONGODB_URI') or os.environ.get('MONGO_URI')
            
            # 如果环境变量不存在，尝试使用配置文件中的URI
            if not mongodb_uri:
                mongodb_uri = app.config.get('MONGODB_URI')
            
            # 如果配置也不存在，尝试使用默认URI
            if not mongodb_uri:
                # 本地环境默认连接
                mongodb_uri = 'mongodb://localhost:27017/'
            
            # Extract database name from URI or use a default
            try:
                db_name = pymongo.uri_parser.parse_uri(mongodb_uri)['database']
                if not db_name:
                    db_name = os.environ.get('DB_NAME') or app.config.get('DB_NAME') or 'chatdb'
            except Exception:
                db_name = os.environ.get('DB_NAME') or app.config.get('DB_NAME') or 'chatdb'
            
            app.logger.info(f"正在连接MongoDB: {mongodb_uri}, 数据库: {db_name}")
        
            # 创建MongoDB客户端，设置较短的超时时间
            self.client = pymongo.MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[db_name]
            
            # 测试连接
            self.db.command('ping')
            self.mode = "mongo"
            app.logger.info(f"MongoDB connection initialized to database '{db_name}'")
        except Exception as e:
            app.logger.error(f"MongoDB connection error: {str(e)}")
            app.logger.warning("Using fallback in-memory storage - data will not persist!")
            # 仅在开发模式下使用空字典作为后备存储
            if app.config.get('DEBUG', False):
                self.client = None
                # 在调试模式下，如果MongoDB连接失败，使用内存存储
                # 并且初始化一个空的 'users' 列表来模拟集合
                self.db = InMemoryDatabase()
                self.mode = "memory"
                app.logger.warning("Using fallback in-memory storage for Database - data will not persist!")
            else:
                raise
    
    def __getattr__(self, name):
        """Allow access to MongoDB collections as attributes dynamically."""
        # Check if client and db are initialized
        if self.db is None:
            raise RuntimeError("Database not initialized. Call init_app first.")

        # InMemoryDatabase uses attribute access, while pymongo database supports item access.
        if hasattr(self.db, '_collections'):
            return getattr(self.db, name)

        # Return the collection object
        # No need to cache in self._collections if accessed dynamically
        return self.db[name]
    
    @property
    def cx(self):
        """Provide access to the underlying MongoClient."""
        if self.client is None:
             raise RuntimeError("Database not initialized. Call init_app first.")
        return self.client

    @property
    def is_in_memory(self):
        return self.mode == "memory" or hasattr(self.db, '_collections')

    @property
    def is_mongo_connected(self):
        return self.mode == "mongo" and self.client is not None and self.db is not None

# 创建单例数据库实例
db = Database()

def init_extensions(app):
    """初始化应用扩展"""
    # 配置Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "api.login"
    login_manager.login_message = "请先登录"
    login_manager.login_message_category = "info"
    
    # 初始化MongoDB连接
    db.init_app(app)

class InMemoryCollection:
    def __init__(self, name):
        self.name = name
        self._documents = []
        self._next_id = 1

    def insert_one(self, document):
        if '_id' not in document:
            document['_id'] = str(self._next_id)
            self._next_id += 1
        self._documents.append(document)
        return type('InsertOneResult', (object,), {'inserted_id': document['_id']})()

    def insert_many(self, documents):
        inserted_ids = []
        for document in documents:
            result = self.insert_one(document)
            inserted_ids.append(result.inserted_id)
        return type('InsertManyResult', (object,), {'inserted_ids': inserted_ids})()

    def find_one(self, query=None):
        if query:
            for doc in self._documents:
                match = True
                for key, value in query.items():
                    if doc.get(key) != value:
                        match = False
                        break
                if match:
                    return doc
        return None

    def find(self, query=None, projection=None):
        # 简单的实现，只返回所有文档
        return self._documents
    
    def update_one(self, query, update):
        # 简单的实现
        doc = self.find_one(query)
        if doc:
            # $set 操作
            if '$set' in update:
                doc.update(update['$set'])
            # 其他更新操作可以根据需要添加
            return type('UpdateOneResult', (object,), {'matched_count': 1, 'modified_count': 1})()
        return type('UpdateOneResult', (object,), {'matched_count': 0, 'modified_count': 0})()

    def delete_many(self, query):
        original_count = len(self._documents)
        self._documents = [doc for doc in self._documents if not self.match_query(doc, query)]
        deleted_count = original_count - len(self._documents)
        return type('DeleteResult', (object,), {'deleted_count': deleted_count})()

    def create_index(self, *args, **kwargs):
        return None

    def delete_one(self, query):
        # 简单的实现
        original_count = len(self._documents)
        self._documents = [doc for doc in self._documents if not self.match_query(doc, query)]
        deleted_count = original_count - len(self._documents)
        return type('DeleteResult', (object,), {'deleted_count': deleted_count})()
    
    def replace_one(self, query, replacement, upsert=False):
        # 实现replace_one方法，支持upsert
        doc = self.find_one(query)
        if doc:
            # 替换现有文档
            index = self._documents.index(doc)
            self._documents[index] = replacement
            return type('UpdateResult', (object,), {'matched_count': 1, 'modified_count': 1, 'upserted_id': None})()
        elif upsert:
            # 如果upsert为True，且文档不存在，则插入新文档
            if '_id' not in replacement:
                replacement['_id'] = str(self._next_id)
                self._next_id += 1
            self._documents.append(replacement)
            return type('UpdateResult', (object,), {'matched_count': 0, 'modified_count': 0, 'upserted_id': replacement['_id']})()
        else:
            # 文档不存在且upsert为False，返回未匹配
            return type('UpdateResult', (object,), {'matched_count': 0, 'modified_count': 0, 'upserted_id': None})()
    
    def match_query(self, doc, query):
        for key, value in query.items():
            if doc.get(key) != value:
                return False
        return True


class InMemoryDatabase:
    def __init__(self):
        self._collections = {
            "users": InMemoryCollection("users"),
            "hot_news": InMemoryCollection("hot_news"), # 模拟 hot_news 集合
            "analyzed_news": InMemoryCollection("analyzed_news"), # 模拟 analyzed_news 集合
            "trend": InMemoryCollection("trend"), # 模拟 trend 集合
            "video_subtitles": InMemoryCollection("video_subtitles") # 模拟 video_subtitles 集合
        }
    
    def __getattr__(self, name):
        if name in self._collections:
            return self._collections[name]
        # 如果访问不存在的集合，则动态创建一个
        new_collection = InMemoryCollection(name)
        self._collections[name] = new_collection
        return new_collection
        
    # 模拟 MongoDB 的 command 方法，例如用于 ping
    def command(self, command_name, *args, **kwargs):
        if command_name == 'ping':
            return {'ok': 1}
        raise NotImplementedError(f"Command {command_name} not implemented in InMemoryDatabase")
