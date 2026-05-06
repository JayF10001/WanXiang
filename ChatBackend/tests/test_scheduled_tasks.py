#!/usr/bin/env python3
"""
Tests for scheduled tasks in the news application.
"""
import os
import sys
import unittest
import json
import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path so we can import the app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock flask.current_app before importing other modules
flask_current_app_mock = MagicMock()
flask_current_app_mock.config = {
    'MONGODB_URI': 'mongodb://db:27017',
    'MAX_NEWS_PER_PLATFORM': 3,
    'HOT_NEWS_THRESHOLD': 0.75,
    'MAX_DATA_AGE_MINUTES': 55,
    'NEWS_DB_NAME': 'test_news'
}
patch('flask.current_app', flask_current_app_mock).start()

# Import mock utilities
from tests.mongo_mock import patch_mongo_client, mock_db_instance
from tests.mock_data import MockData

# Import modules to test
from app.tasks import (
    heartbeat, 
    collect_news_task,
    smart_collect_news_task,
    analyze_trending_news_task,
    process_news_task
)

class TestScheduledTasks(unittest.TestCase):
    """Tests for the scheduled tasks"""
    
    def setUp(self):
        """Set up test environment"""
        self.mock_data = MockData()
        
        # Create mock data
        self.news_items = self.mock_data.generate_news_batch(10)
        self.queue_items = [self.mock_data.generate_analysis_queue_item() for _ in range(5)]
        self.transformed_news = [self.mock_data.generate_transformed_news_item() for _ in range(3)]
        
        # Mock collections data
        self.collections_data = {
            'news': self.news_items,
            'analysis_queue': self.queue_items,
            'transformed_news': self.transformed_news,
            'api_patterns': [self.mock_data.generate_pattern_doc()]
        }
        
        # Create patch for MongoDB
        self.mongo_patcher = patch_mongo_client(self.collections_data)
        self.mongo_mock = self.mongo_patcher.start()
        
        # Setup Flask app mock
        self.app_mock = MagicMock()
        self.app_mock.app_context.return_value.__enter__.return_value = None
        self.app_mock.app_context.return_value.__exit__.return_value = None
        self.app_mock.config = flask_current_app_mock.config
        
        # Mock config
        self.config_patcher = patch('config.Config')
        self.config_mock = self.config_patcher.start()
        self.config_mock.MONGODB_URI = 'mongodb://db:27017'
        self.config_mock.MAX_NEWS_PER_PLATFORM = 3
        
        # Mock API and service classes
        self.news_collection_service_patcher = patch('app.services.news_collection_service.NewsCollectionService')
        self.news_collection_service_mock = self.news_collection_service_patcher.start()
        
        self.news_service_patcher = patch('app.services.news_service.NewsService')
        self.news_service_mock = self.news_service_patcher.start()
        
        self.news_analysis_service_patcher = patch('app.services.news_analysis_service.NewsAnalysisService')
        self.news_analysis_service_mock = self.news_analysis_service_patcher.start()
        
    def tearDown(self):
        """Clean up after tests"""
        self.mongo_patcher.stop()
        self.config_patcher.stop()
        self.news_collection_service_patcher.stop()
        self.news_service_patcher.stop()
        self.news_analysis_service_patcher.stop()
    
    def test_heartbeat(self):
        """Test the heartbeat function"""
        # The heartbeat function should return True
        result = heartbeat()
        self.assertTrue(result)
    
    def test_collect_news_task(self):
        """Test the collect_news_task function"""
        # Mock the necessary methods
        self.news_collection_service_mock.collect_news.return_value = {
            'status': 'success',
            'count': 10
        }
        
        # Call the task
        result = collect_news_task()
        
        # Verify results
        self.news_collection_service_mock.collect_news.assert_called_once()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['count'], 10)
    
    def test_smart_collect_news_task(self):
        """Test the smart_collect_news_task function"""
        # Mock the necessary methods
        self.news_collection_service_mock.smart_collect_news.return_value = {
            'status': 'success',
            'count': 5
        }
        self.news_collection_service_mock.detect_high_heat_news.return_value = {
            'status': 'high_heat_detected',
            'high_heat_count': 2
        }
        
        # Call the task
        result = smart_collect_news_task()
        
        # Verify results
        self.news_collection_service_mock.smart_collect_news.assert_called_once()
        self.news_collection_service_mock.detect_high_heat_news.assert_called_once()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['high_heat_detection']['high_heat_count'], 2)
    
    def test_analyze_trending_news_task(self):
        """Test the analyze_trending_news_task function"""
        # Mock the necessary methods
        self.news_collection_service_mock.schedule_deep_analysis.return_value = {
            'status': 'success',
            'scheduled': 5
        }
        
        # Call the task
        result = analyze_trending_news_task()
        
        # Verify results
        self.news_collection_service_mock.schedule_deep_analysis.assert_called_once()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['scheduled'], 5)
    
    def test_process_news_task(self):
        """Test the process_news_task function"""
        # Mock the necessary methods
        self.news_service_mock.schedule_news_analysis.return_value = {'scheduled': 5}
        self.news_service_mock.process_analysis_queue.return_value = {'processed': 3, 'status': 'success'}
        self.news_service_mock.cleanup_old_queue_items.return_value = 2
        
        # Call the task
        result = process_news_task()
        
        # Verify results
        self.news_service_mock.schedule_news_analysis.assert_called_once()
        self.news_service_mock.process_analysis_queue.assert_called_once()
        self.news_service_mock.cleanup_old_queue_items.assert_called_once()
        self.assertEqual(result['scheduled']['scheduled'], 5)
        self.assertEqual(result['processed']['processed'], 3)
        self.assertEqual(result['cleaned'], 2)
    
    def test_collect_news_task_error(self):
        """Test error handling in collect_news_task"""
        # Mock to raise an exception
        self.news_collection_service_mock.collect_news.side_effect = Exception("API Error")
        
        # Call the task
        result = collect_news_task()
        
        # Verify error handling
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'API Error')
    
    def test_smart_collect_news_task_error(self):
        """Test error handling in smart_collect_news_task"""
        # Mock to raise an exception
        self.news_collection_service_mock.smart_collect_news.side_effect = Exception("Collection Error")
        
        # Call the task
        result = smart_collect_news_task()
        
        # Verify error handling
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Collection Error')

class TestMockData(unittest.TestCase):
    """Test cases for the MockData class"""
    
    def setUp(self):
        """Set up the test environment"""
        self.mock_data = MockData()
        
    def test_generate_news_item(self):
        """Test that news items are generated correctly"""
        item = self.mock_data.generate_news_item()
        
        # Verify that the required fields are present
        self.assertIn('title', item)
        self.assertIn('platform', item)
        self.assertIn('url', item)
        self.assertIn('heat', item)
        self.assertIn('heat_value', item)
        self.assertIn('heat_level', item)
        
        # Test with custom parameters
        custom_item = self.mock_data.generate_news_item(
            title="Custom Title",
            platform="weibo",
            heat="500万",
            heat_value=5000000
        )
        self.assertEqual(custom_item['title'], "Custom Title")
        self.assertEqual(custom_item['platform'], "weibo")
        self.assertEqual(custom_item['heat'], "500万")
        self.assertEqual(custom_item['heat_value'], 5000000)
        
    def test_generate_news_batch(self):
        """Test that news batches have the correct number of items"""
        batch = self.mock_data.generate_news_batch(5)
        
        # Verify batch size
        self.assertEqual(len(batch), 5)
        
        # Verify that all items have required fields
        for item in batch:
            self.assertIn('title', item)
            self.assertIn('platform', item)
            
        # Test with empty batch
        empty_batch = self.mock_data.generate_news_batch(0)
        self.assertEqual(len(empty_batch), 0)
            
    def test_generate_pattern_doc(self):
        """Test pattern document generation"""
        pattern = self.mock_data.generate_pattern_doc()
        
        # Verify pattern structure
        self.assertIn('pattern_hash', pattern)
        self.assertIn('timestamp', pattern)
        self.assertIn('platforms', pattern)
        
        # Test with custom parameters
        custom_pattern = self.mock_data.generate_pattern_doc(
            pattern_hash="test_hash",
            count=10
        )
        self.assertEqual(custom_pattern['pattern_hash'], "test_hash")
        self.assertEqual(custom_pattern['count'], 10)
    
    def test_generate_analysis_queue_item(self):
        """Test analysis queue item generation"""
        item = self.mock_data.generate_analysis_queue_item()
        
        # Verify required fields
        self.assertIn('_id', item)
        self.assertIn('news_id', item)
        self.assertIn('title', item)
        self.assertIn('platform', item)
        self.assertIn('status', item)
        self.assertIn('created_at', item)
        self.assertIn('last_attempt', item)
        self.assertIn('attempts', item)
        
        # Test with custom parameters
        custom_item = self.mock_data.generate_analysis_queue_item(
            status="processing",
            attempts=2
        )
        self.assertEqual(custom_item['status'], "processing")
        self.assertEqual(custom_item['attempts'], 2)
    
    def test_generate_transformed_news_item(self):
        """Test transformed news item generation"""
        item = self.mock_data.generate_transformed_news_item()
        
        # Verify required fields
        self.assertIn('_id', item)
        self.assertIn('news_id', item)
        self.assertIn('title', item)
        self.assertIn('summary', item)
        self.assertIn('sentiment', item)
        self.assertIn('category', item)
        self.assertIn('keywords', item)
        self.assertIn('topics', item)
        
        # Test with custom parameters
        custom_item = self.mock_data.generate_transformed_news_item(
            summary="Custom summary",
            sentiment="positive",
            keywords=["test", "custom"]
        )
        self.assertEqual(custom_item['summary'], "Custom summary")
        self.assertEqual(custom_item['sentiment'], "positive")
        self.assertListEqual(custom_item['keywords'], ["test", "custom"])

if __name__ == "__main__":
    unittest.main() 