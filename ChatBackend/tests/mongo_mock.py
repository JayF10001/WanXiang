#!/usr/bin/env python3
"""
MongoDB mock helper for testing scheduled tasks.
"""
import unittest
from unittest.mock import MagicMock, patch
import copy

class TestMongoMock(unittest.TestCase):
    """Test the MongoDB mock functionality"""
    
    def test_mongo_collection_mock_find(self):
        """Test that the find method works correctly"""
        data = [{'id': 1, 'name': 'test1'}, {'id': 2, 'name': 'test2'}]
        collection = MongoCollectionMock(data)
        
        # Test find without filter
        result = list(collection.find())
        self.assertEqual(len(result), 2)
        
        # Test find with filter
        result = list(collection.find({'id': 1}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'test1')
    
    def test_mongo_collection_mock_insert(self):
        """Test that the insert methods work correctly"""
        collection = MongoCollectionMock([])
        
        # Test insert_one
        collection.insert_one({'id': 1, 'name': 'test1'})
        self.assertEqual(len(collection.data), 1)
        
        # Test insert_many
        collection.insert_many([{'id': 2, 'name': 'test2'}, {'id': 3, 'name': 'test3'}])
        self.assertEqual(len(collection.data), 3)
    
    def test_mongo_collection_mock_update(self):
        """Test that the update methods work correctly"""
        data = [{'id': 1, 'name': 'test1'}, {'id': 2, 'name': 'test2'}]
        collection = MongoCollectionMock(data)
        
        # Test update_one
        collection.update_one({'id': 1}, {'$set': {'name': 'updated'}})
        self.assertEqual(collection.data[0]['name'], 'updated')
        
        # Test update_many
        collection.update_many({}, {'$set': {'status': 'active'}})
        self.assertEqual(collection.data[0]['status'], 'active')
        self.assertEqual(collection.data[1]['status'], 'active')
        
        # Test find_one_and_update
        result = collection.find_one_and_update(
            {'id': 2}, 
            {'$set': {'name': 'updated2'}, '$inc': {'count': 1}},
            return_document=True
        )
        self.assertEqual(result['name'], 'updated2')
        self.assertEqual(result['count'], 1)

class MongoClientMock:
    """Mock for pymongo.MongoClient"""
    
    def __init__(self, db_name='test_db', collections=None):
        self.db_name = db_name
        self.collections = collections or {}
        self.db = MongoDBMock(self.db_name, self.collections)
    
    def __getitem__(self, db_name):
        """Support dictionary-style access: client[db_name]"""
        self.db_name = db_name
        return self.db

class MongoDBMock:
    """Mock for pymongo.Database"""
    
    def __init__(self, db_name, collections=None):
        self.db_name = db_name
        self.collections = collections or {}
    
    def __getitem__(self, collection_name):
        """Support dictionary-style access: db[collection_name]"""
        if collection_name not in self.collections:
            self.collections[collection_name] = MongoCollectionMock([])
        return self.collections[collection_name]
    
    def create_collection(self, collection_name):
        """Create a new collection"""
        if collection_name not in self.collections:
            self.collections[collection_name] = MongoCollectionMock([])
        return self.collections[collection_name]
    
    def list_collection_names(self):
        """List all collection names"""
        return list(self.collections.keys())

class MongoCollectionMock:
    """Mock for pymongo.Collection"""
    
    def __init__(self, data=None):
        self.data = data or []
        self.delete_result = MagicMock()
        self.update_result = MagicMock()
        self.insert_result = MagicMock()
    
    def find(self, filter_dict=None, projection=None, *args, **kwargs):
        """Mock the find method"""
        if filter_dict is None:
            return MongoResultMock(copy.deepcopy(self.data))
        
        filtered_data = []
        for item in self.data:
            match = True
            for key, value in filter_dict.items():
                # Handle nested keys (e.g., 'user.name')
                if '.' in key:
                    parts = key.split('.')
                    current = item
                    for part in parts[:-1]:
                        if part in current:
                            current = current[part]
                        else:
                            match = False
                            break
                    if match and (parts[-1] in current and current[parts[-1]] == value):
                        continue
                    else:
                        match = False
                        break
                # Handle non-nested keys
                elif key not in item or item[key] != value:
                    match = False
                    break
            if match:
                filtered_data.append(copy.deepcopy(item))
        
        return MongoResultMock(filtered_data)
    
    def find_one(self, filter_dict=None, *args, **kwargs):
        """Mock the find_one method"""
        results = self.find(filter_dict)
        return next(results) if results.data else None
    
    def insert_one(self, document):
        """Mock the insert_one method"""
        self.data.append(document)
        self.insert_result.inserted_id = document.get('_id', len(self.data))
        return self.insert_result
    
    def insert_many(self, documents):
        """Mock the insert_many method"""
        inserted_ids = []
        for doc in documents:
            self.data.append(doc)
            inserted_ids.append(doc.get('_id', len(self.data)))
        self.insert_result.inserted_ids = inserted_ids
        return self.insert_result
    
    def update_one(self, filter_dict, update_dict, upsert=False):
        """Mock the update_one method"""
        updated = False
        
        for i, item in enumerate(self.data):
            match = True
            for key, value in filter_dict.items():
                if key not in item or item[key] != value:
                    match = False
                    break
            
            if match:
                self._apply_update(self.data[i], update_dict)
                updated = True
                break
        
        if not updated and upsert:
            new_doc = {**filter_dict}
            self._apply_update(new_doc, update_dict, is_new=True)
            self.data.append(new_doc)
        
        self.update_result.modified_count = 1 if updated else 0
        self.update_result.upserted_id = None if updated or not upsert else len(self.data)
        self.update_result.matched_count = 1 if updated else 0
        return self.update_result
    
    def update_many(self, filter_dict, update_dict, upsert=False):
        """Mock the update_many method"""
        matched_count = 0
        modified_count = 0
        
        for i, item in enumerate(self.data):
            match = True
            if filter_dict:  # If filter_dict is not empty
                for key, value in filter_dict.items():
                    if key not in item or item[key] != value:
                        match = False
                        break
            
            if match:
                matched_count += 1
                self._apply_update(self.data[i], update_dict)
                modified_count += 1
        
        if matched_count == 0 and upsert:
            new_doc = {**filter_dict}
            self._apply_update(new_doc, update_dict, is_new=True)
            self.data.append(new_doc)
        
        self.update_result.modified_count = modified_count
        self.update_result.upserted_id = None if matched_count > 0 or not upsert else len(self.data)
        self.update_result.matched_count = matched_count
        return self.update_result
    
    def find_one_and_update(self, filter_dict, update_dict, upsert=False, return_document=False):
        """Mock the find_one_and_update method"""
        matched_item = None
        matched_index = -1
        
        for i, item in enumerate(self.data):
            match = True
            for key, value in filter_dict.items():
                if key not in item or item[key] != value:
                    match = False
                    break
            
            if match:
                matched_item = copy.deepcopy(item)
                matched_index = i
                break
        
        if matched_item is None and upsert:
            new_doc = {**filter_dict}
            self._apply_update(new_doc, update_dict, is_new=True)
            self.data.append(new_doc)
            return new_doc if return_document else None
        
        if matched_item is not None:
            self._apply_update(self.data[matched_index], update_dict)
            return self.data[matched_index] if return_document else matched_item
        
        return None
    
    def delete_one(self, filter_dict):
        """Mock the delete_one method"""
        for i, item in enumerate(self.data):
            match = True
            for key, value in filter_dict.items():
                if key not in item or item[key] != value:
                    match = False
                    break
            
            if match:
                del self.data[i]
                self.delete_result.deleted_count = 1
                return self.delete_result
        
        self.delete_result.deleted_count = 0
        return self.delete_result
    
    def delete_many(self, filter_dict):
        """Mock the delete_many method"""
        initial_count = len(self.data)
        if not filter_dict:  # Empty filter means delete all
            deleted_count = initial_count
            self.data.clear()
        else:
            new_data = []
            for item in self.data:
                match = True
                for key, value in filter_dict.items():
                    if key not in item or item[key] != value:
                        match = False
                        break
                
                if not match:
                    new_data.append(item)
            
            deleted_count = initial_count - len(new_data)
            self.data = new_data
        
        self.delete_result.deleted_count = deleted_count
        return self.delete_result
    
    def count_documents(self, filter_dict=None):
        """Mock the count_documents method"""
        if filter_dict is None:
            return len(self.data)
        
        count = 0
        for item in self.data:
            match = True
            for key, value in filter_dict.items():
                if key not in item or item[key] != value:
                    match = False
                    break
            
            if match:
                count += 1
        
        return count
    
    def create_index(self, *args, **kwargs):
        """Mock the create_index method"""
        return "mock_index"
    
    def _apply_update(self, doc, update_dict, is_new=False):
        """Apply update operations to a document"""
        for operator, fields in update_dict.items():
            if operator == '$set':
                for field, value in fields.items():
                    if '.' in field:  # Handle nested fields
                        parts = field.split('.')
                        current = doc
                        for part in parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[parts[-1]] = value
                    else:
                        doc[field] = value
            
            elif operator == '$inc':
                for field, value in fields.items():
                    if field in doc:
                        doc[field] += value
                    else:
                        doc[field] = value
            
            elif operator == '$unset':
                for field in fields:
                    if field in doc:
                        del doc[field]
            
            elif operator == '$push':
                for field, value in fields.items():
                    if field not in doc:
                        doc[field] = []
                    doc[field].append(value)
            
            elif is_new and operator.startswith('$'):
                pass  # Skip other operators for new documents
            
            elif is_new:
                # Handle direct assignments in upsert for new documents
                doc[operator] = fields

class MongoResultMock:
    """Mock for pymongo cursor results"""
    
    def __init__(self, data):
        self.data = data
        self.index = 0
    
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.index < len(self.data):
            result = self.data[self.index]
            self.index += 1
            return result
        raise StopIteration
    
    def limit(self, count):
        """Mock the limit method"""
        self.data = self.data[:count]
        return self
    
    def sort(self, sort_key, direction=1):
        """Mock the sort method"""
        if isinstance(sort_key, str):
            self.data.sort(key=lambda x: x.get(sort_key, 0), reverse=direction == -1)
        elif isinstance(sort_key, list):
            for key, direction in reversed(sort_key):
                reverse = direction == -1
                self.data.sort(key=lambda x: x.get(key, 0), reverse=reverse)
        return self
    
    def skip(self, count):
        """Mock the skip method"""
        self.data = self.data[count:]
        return self
    
    def count(self):
        """Mock the count method"""
        return len(self.data)
    
    def to_list(self, length=None):
        """Convert cursor to list"""
        if length is None:
            return self.data
        return self.data[:length]

def patch_mongo_client(collections_data=None):
    """Create a MongoClient patch with predefined collections data"""
    collections = {}
    if collections_data:
        for collection_name, data in collections_data.items():
            collections[collection_name] = MongoCollectionMock(data)
    
    return patch('pymongo.MongoClient', return_value=MongoClientMock(collections=collections))

def mock_db_instance(collections_data=None):
    """Create a mock MongoDB instance with predefined collections data"""
    collections = {}
    if collections_data:
        for collection_name, data in collections_data.items():
            collections[collection_name] = MongoCollectionMock(data)
    
    mongo_mock = MongoClientMock(collections=collections)
    return mongo_mock

if __name__ == "__main__":
    # Run the tests
    unittest.main() 