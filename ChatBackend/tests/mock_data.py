#!/usr/bin/env python3
"""
Mock data generator for testing.
"""
import datetime
import json
import os
import random
import unittest
import uuid
from bson import ObjectId

class TestMockData(unittest.TestCase):
    """Test the mock data generator functionality"""
    
    def test_generate_news_item(self):
        """Test that news items are generated with required fields"""
        item = MockData.generate_news_item()
        self.assertIsNotNone(item.get('title'))
        self.assertIsNotNone(item.get('url'))
        self.assertIsNotNone(item.get('source'))
        self.assertIsNotNone(item.get('heat'))
        
    def test_generate_news_batch(self):
        """Test that news batches have the correct number of items"""
        batch = MockData.generate_news_batch(5)
        self.assertEqual(len(batch), 5)
        
    def test_generate_pattern_doc(self):
        """Test pattern document generation"""
        pattern = MockData.generate_pattern_doc()
        self.assertEqual(pattern['type'], 'hourly_pattern')
        self.assertIsInstance(pattern['common_minute'], int)

class MockData:
    """Generate mock data for testing"""
    
    def __init__(self):
        """Initialize the mock data generator"""
        self.platforms = ['weibo', 'toutiao', 'zhihu', 'baidu', 'douyin']
        self.categories = ['politics', 'entertainment', 'technology', 'sports', 'business']
        self.heat_levels = ['爆', '热', '高', '中', '低']
        self.languages = ['zh', 'en']
        self.titles = [
            "China announces new economic policy",
            "Latest smartphone release breaks sales records",
            "Major sports event outcomes surprise fans",
            "Entertainment industry faces new challenges",
            "Technology breakthrough promises cleaner energy",
            "Global markets react to economic indicators",
            "Healthcare innovations gain attention",
            "Environmental concerns drive policy changes",
            "Education system undergoes significant reforms",
            "Cultural event attracts international audience"
        ]
        
    def generate_news_item(self, **kwargs):
        """Generate a single news item"""
        item = {
            '_id': str(uuid.uuid4()),
            'title': kwargs.get('title', random.choice(self.titles)),
            'platform': kwargs.get('platform', random.choice(self.platforms)),
            'url': kwargs.get('url', f"https://example.com/news/{uuid.uuid4()}"),
            'heat': kwargs.get('heat', f"{random.randint(1, 1000)}万"),
            'heat_value': kwargs.get('heat_value', random.randint(10000, 10000000)),
            'heat_level': kwargs.get('heat_level', random.choice(self.heat_levels)),
            'category': kwargs.get('category', random.choice(self.categories)),
            'collected_at': kwargs.get('collected_at', datetime.datetime.now()),
            'language': kwargs.get('language', random.choice(self.languages)),
            'sources': kwargs.get('sources', []),
            'normalized_score': kwargs.get('normalized_score', random.random()),
        }
        
        # Generate sources if not provided
        if not item['sources']:
            source_count = random.randint(1, 3)
            for _ in range(source_count):
                platform = random.choice(self.platforms)
                item['sources'].append({
                    'platform': platform,
                    'url': f"https://{platform}.com/news/{uuid.uuid4()}",
                    'heat': f"{random.randint(1, 500)}万",
                    'heat_value': random.randint(10000, 5000000)
                })
                
        return item
    
    def generate_news_batch(self, count=10):
        """Generate a batch of news items"""
        return [self.generate_news_item() for _ in range(count)]
    
    def generate_analysis_queue_item(self, **kwargs):
        """Generate an analysis queue item"""
        news_item = self.generate_news_item(**kwargs)
        
        return {
            '_id': str(uuid.uuid4()),
            'news_id': kwargs.get('news_id', news_item['_id']),
            'title': news_item['title'],
            'platform': news_item['platform'],
            'url': news_item['url'],
            'status': kwargs.get('status', random.choice(['pending', 'processing', 'completed', 'error'])),
            'created_at': kwargs.get('created_at', datetime.datetime.now()),
            'last_attempt': kwargs.get('last_attempt', datetime.datetime.now()),
            'attempts': kwargs.get('attempts', random.randint(0, 3)),
            'error': kwargs.get('error', None)
        }
    
    def generate_transformed_news_item(self, **kwargs):
        """Generate a transformed news item"""
        news_item = self.generate_news_item(**kwargs)
        
        return {
            '_id': str(uuid.uuid4()),
            'news_id': kwargs.get('news_id', news_item['_id']),
            'title': news_item['title'],
            'summary': kwargs.get('summary', "This is a mock summary of the news article."),
            'sentiment': kwargs.get('sentiment', random.choice(['positive', 'negative', 'neutral'])),
            'category': news_item['category'],
            'keywords': kwargs.get('keywords', ["keyword1", "keyword2", "keyword3"]),
            'topics': kwargs.get('topics', ["topic1", "topic2"]),
            'platforms': kwargs.get('platforms', [news_item['platform']]),
            'heat_level': news_item['heat_level'],
            'normalized_score': news_item['normalized_score'],
            'urls': kwargs.get('urls', [news_item['url']]),
            'created_at': kwargs.get('created_at', datetime.datetime.now()),
            'analysis_version': kwargs.get('analysis_version', "1.0")
        }
    
    def generate_pattern_doc(self, **kwargs):
        """Generate an API pattern document"""
        return {
            '_id': str(uuid.uuid4()),
            'pattern_hash': kwargs.get('pattern_hash', str(uuid.uuid4())),
            'timestamp': kwargs.get('timestamp', datetime.datetime.now()),
            'count': kwargs.get('count', random.randint(5, 20)),
            'platforms': kwargs.get('platforms', self.platforms),
            'news_ids': kwargs.get('news_ids', [str(uuid.uuid4()) for _ in range(5)])
        }
    
    def generate_response_file(self, filename, item_count=20):
        """Generate a mock response file"""
        news_items = self.generate_news_batch(item_count)
        response_data = {
            'data': {
                'list': news_items
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, default=str, ensure_ascii=False)
            
        return filename

if __name__ == "__main__":
    # Generate sample mock data and save to files
    mock_data = MockData()
    for collection_name, data in mock_data.__dict__.items():
        if callable(data):
            MockData.save_mock_data_to_file(data, f"mock_{collection_name}.json")
            print(f"Generated mock data for {collection_name} with {len(data)} items")
    
    # Run the tests
    unittest.main() 