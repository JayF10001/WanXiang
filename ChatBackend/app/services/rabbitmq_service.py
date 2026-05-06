"""
RabbitMQ服务 - 替代数据库队列，提升队列处理性能

主要功能：
1. 新闻分析任务队列管理
2. 高热度新闻优先处理
3. 分布式任务调度
4. 消息持久化和确认机制
"""

import json
import pika
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import current_app
from ..extensions import db
import threading
import time


class RabbitMQService:
    """RabbitMQ队列服务"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange_name = 'news_analysis'
        self.queues = {
            'normal': 'news_analysis_normal',
            'high': 'news_analysis_high',
            'results': 'analysis_results'
        }
        
    def connect(self):
        """建立RabbitMQ连接"""
        try:
            # 从配置获取连接参数
            host = current_app.config.get('RABBITMQ_HOST', 'localhost')
            port = current_app.config.get('RABBITMQ_PORT', 5672)
            username = current_app.config.get('RABBITMQ_USERNAME', 'guest')
            password = current_app.config.get('RABBITMQ_PASSWORD', 'guest')
            
            credentials = pika.PlainCredentials(username, password)
            parameters = pika.ConnectionParameters(
                host=host,
                port=port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # 声明交换机
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='direct',
                durable=True
            )
            
            # 声明队列
            for queue_type, queue_name in self.queues.items():
                self.channel.queue_declare(
                    queue=queue_name,
                    durable=True,
                    arguments={
                        'x-message-ttl': 3600000,  # 1小时TTL
                        'x-max-length': 10000,     # 最大队列长度
                    }
                )
                
                # 绑定队列到交换机
                if queue_type != 'results':
                    self.channel.queue_bind(
                        exchange=self.exchange_name,
                        queue=queue_name,
                        routing_key=queue_type
                    )
            
            print("RabbitMQ连接建立成功")
            return True
            
        except Exception as e:
            print(f"RabbitMQ连接失败: {str(e)}")
            return False
    
    def disconnect(self):
        """关闭连接"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            print("RabbitMQ连接已关闭")
        except Exception as e:
            print(f"关闭RabbitMQ连接时出错: {str(e)}")
    
    def enqueue_analysis_task(self, news_data: Dict, priority: str = 'normal') -> bool:
        """
        将新闻分析任务加入队列
        
        Args:
            news_data: 新闻数据
            priority: 优先级 ('normal' 或 'high')
            
        Returns:
            bool: 是否成功加入队列
        """
        try:
            if not self.channel:
                if not self.connect():
                    return False
            
            # 生成任务ID
            task_id = hashlib.md5(
                f"{news_data.get('title', '')}{datetime.now().isoformat()}".encode()
            ).hexdigest()
            
            # 构建消息
            message = {
                'task_id': task_id,
                'news_data': news_data,
                'queued_at': datetime.now().isoformat(),
                'priority': priority,
                'retry_count': 0
            }
            
            # 发布消息
            routing_key = 'high' if priority == 'high' else 'normal'
            
            self.channel.basic_publish(
                exchange=self.exchange_name,
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 消息持久化
                    message_id=task_id,
                    timestamp=int(datetime.now().timestamp()),
                    priority=1 if priority == 'high' else 0
                )
            )
            
            print(f"新闻分析任务已加入队列: {news_data.get('title', '')[:30]}... (优先级: {priority})")
            return True
            
        except Exception as e:
            print(f"加入队列失败: {str(e)}")
            return False
    
    def process_analysis_queue(self, callback_func, max_workers: int = 4):
        """
        处理分析队列中的任务
        
        Args:
            callback_func: 处理任务的回调函数
            max_workers: 最大工作线程数
        """
        def worker_thread(queue_name: str, worker_id: int):
            """工作线程函数"""
            print(f"启动工作线程 {worker_id} 处理队列 {queue_name}")
            
            try:
                # 为每个工作线程创建独立连接
                worker_connection = pika.BlockingConnection(
                    self.connection.parameters
                )
                worker_channel = worker_connection.channel()
                
                # 设置QoS，每次只处理一个消息
                worker_channel.basic_qos(prefetch_count=1)
                
                def process_message(ch, method, properties, body):
                    """处理单个消息"""
                    try:
                        message = json.loads(body.decode('utf-8'))
                        task_id = message.get('task_id')
                        news_data = message.get('news_data')
                        
                        print(f"工作线程 {worker_id} 开始处理任务: {task_id}")
                        
                        # 调用回调函数处理任务
                        result = callback_func(news_data)
                        
                        if result:
                            # 处理成功，确认消息
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            
                            # 发布结果到结果队列
                            self.publish_result(task_id, result, 'success')
                            
                            print(f"任务 {task_id} 处理成功")
                        else:
                            # 处理失败，重新入队或拒绝
                            retry_count = message.get('retry_count', 0)
                            if retry_count < 3:
                                # 重试
                                message['retry_count'] = retry_count + 1
                                self.enqueue_analysis_task(
                                    news_data, 
                                    message.get('priority', 'normal')
                                )
                                ch.basic_ack(delivery_tag=method.delivery_tag)
                                print(f"任务 {task_id} 处理失败，重试第 {retry_count + 1} 次")
                            else:
                                # 超过重试次数，拒绝消息
                                ch.basic_nack(
                                    delivery_tag=method.delivery_tag, 
                                    requeue=False
                                )
                                self.publish_result(task_id, None, 'failed')
                                print(f"任务 {task_id} 处理失败，超过重试次数")
                                
                    except Exception as e:
                        print(f"处理消息时出错: {str(e)}")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                
                # 开始消费消息
                worker_channel.basic_consume(
                    queue=queue_name,
                    on_message_callback=process_message
                )
                
                print(f"工作线程 {worker_id} 开始监听队列 {queue_name}")
                worker_channel.start_consuming()
                
            except Exception as e:
                print(f"工作线程 {worker_id} 出错: {str(e)}")
            finally:
                try:
                    worker_connection.close()
                except:
                    pass
        
        # 启动工作线程
        threads = []
        
        # 高优先级队列使用一半的工作线程
        high_workers = max(1, max_workers // 2)
        normal_workers = max_workers - high_workers
        
        # 启动高优先级队列工作线程
        for i in range(high_workers):
            thread = threading.Thread(
                target=worker_thread,
                args=(self.queues['high'], f"high-{i}")
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # 启动普通优先级队列工作线程
        for i in range(normal_workers):
            thread = threading.Thread(
                target=worker_thread,
                args=(self.queues['normal'], f"normal-{i}")
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        print(f"已启动 {len(threads)} 个工作线程处理分析队列")
        return threads
    
    def publish_result(self, task_id: str, result: Any, status: str):
        """
        发布分析结果
        
        Args:
            task_id: 任务ID
            result: 分析结果
            status: 状态 ('success' 或 'failed')
        """
        try:
            message = {
                'task_id': task_id,
                'result': result,
                'status': status,
                'completed_at': datetime.now().isoformat()
            }
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queues['results'],
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            
        except Exception as e:
            print(f"发布结果失败: {str(e)}")
    
    def get_queue_info(self) -> Dict:
        """
        获取队列信息
        
        Returns:
            Dict: 队列统计信息
        """
        try:
            if not self.channel:
                if not self.connect():
                    return {}
            
            info = {}
            for queue_type, queue_name in self.queues.items():
                method = self.channel.queue_declare(
                    queue=queue_name, 
                    passive=True
                )
                info[queue_type] = {
                    'name': queue_name,
                    'message_count': method.method.message_count,
                    'consumer_count': method.method.consumer_count
                }
            
            return info
            
        except Exception as e:
            print(f"获取队列信息失败: {str(e)}")
            return {}
    
    def clear_queue(self, queue_type: str = 'all') -> bool:
        """
        清空队列
        
        Args:
            queue_type: 队列类型 ('normal', 'high', 'results', 'all')
            
        Returns:
            bool: 是否成功
        """
        try:
            if not self.channel:
                if not self.connect():
                    return False
            
            if queue_type == 'all':
                for queue_name in self.queues.values():
                    self.channel.queue_purge(queue=queue_name)
                print("已清空所有队列")
            else:
                queue_name = self.queues.get(queue_type)
                if queue_name:
                    self.channel.queue_purge(queue=queue_name)
                    print(f"已清空队列: {queue_name}")
                else:
                    print(f"未找到队列类型: {queue_type}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"清空队列失败: {str(e)}")
            return False


# 全局RabbitMQ服务实例
rabbitmq_service = RabbitMQService()


def init_rabbitmq(app):
    """初始化RabbitMQ服务"""
    with app.app_context():
        try:
            if rabbitmq_service.connect():
                print("RabbitMQ服务初始化成功")
                return True
            else:
                print("RabbitMQ服务初始化失败")
                return False
        except Exception as e:
            print(f"初始化RabbitMQ时出错: {str(e)}")
            return False


def cleanup_rabbitmq():
    """清理RabbitMQ资源"""
    rabbitmq_service.disconnect()
