"""
新闻分析服务模块

优化后的架构包含：
1. 统一的数据库架构 (4个核心集合)
2. RabbitMQ消息队列 (可选，替代数据库队列)
3. Redis缓存层 (可选，提升查询性能)
4. 统一查询接口 (减少重复查询)
5. 简化的去重逻辑 (统一在分析层处理)
"""

from .news_service import NewsService
from .news_analysis_service import NewsAnalysisService
from .news_collection_service import NewsCollectionService

# 可选导入 - RabbitMQ 服务
try:
    from .rabbitmq_service import RabbitMQService, rabbitmq_service, init_rabbitmq, cleanup_rabbitmq
    RABBITMQ_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ RabbitMQ服务不可用: {str(e)}")
    print("   如需使用RabbitMQ，请安装: pip install pika")
    RabbitMQService = None
    rabbitmq_service = None
    init_rabbitmq = None
    cleanup_rabbitmq = None
    RABBITMQ_AVAILABLE = False

# 可选导入 - Redis 缓存服务
try:
    from .redis_cache_service import RedisCacheService, redis_cache, init_redis_cache
    REDIS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Redis缓存服务不可用: {str(e)}")
    print("   如需使用Redis，请安装: pip install redis")
    RedisCacheService = None
    redis_cache = None
    init_redis_cache = None
    REDIS_AVAILABLE = False

__all__ = [
    'NewsService',
    'NewsAnalysisService', 
    'NewsCollectionService',
    'RABBITMQ_AVAILABLE',
    'REDIS_AVAILABLE'
]

# 动态添加可用的服务到 __all__
if RABBITMQ_AVAILABLE:
    __all__.extend([
        'RabbitMQService',
        'rabbitmq_service',
        'init_rabbitmq',
        'cleanup_rabbitmq'
    ])

if REDIS_AVAILABLE:
    __all__.extend([
        'RedisCacheService',
        'redis_cache',
        'init_redis_cache'
    ])

def init_optimized_services(app):
    """
    初始化所有可用的优化服务
    
    Args:
        app: Flask应用实例
        
    Returns:
        dict: 初始化结果状态
    """
    results = {
        'redis': False,
        'rabbitmq': False,
        'total_success': False,
        'available_services': [],
        'unavailable_services': []
    }
    
    try:
        # 初始化Redis缓存（如果可用）
        if REDIS_AVAILABLE and init_redis_cache:
            print("正在初始化Redis缓存服务...")
            try:
                results['redis'] = init_redis_cache(app)
                if results['redis']:
                    results['available_services'].append('Redis')
                    print("✅ Redis缓存服务初始化成功")
                else:
                    print("❌ Redis缓存服务初始化失败")
                    results['unavailable_services'].append('Redis')
            except Exception as e:
                print(f"❌ Redis缓存服务初始化失败: {str(e)}")
                results['unavailable_services'].append('Redis')
        else:
            print("⚠️ Redis缓存服务不可用，跳过初始化")
            results['unavailable_services'].append('Redis')
        
        # 初始化RabbitMQ（如果可用）
        if RABBITMQ_AVAILABLE and init_rabbitmq:
            print("正在初始化RabbitMQ消息队列...")
            try:
                results['rabbitmq'] = init_rabbitmq(app)
                if results['rabbitmq']:
                    results['available_services'].append('RabbitMQ')
                    print("✅ RabbitMQ消息队列初始化成功")
                else:
                    print("❌ RabbitMQ消息队列初始化失败")
                    results['unavailable_services'].append('RabbitMQ')
            except Exception as e:
                print(f"❌ RabbitMQ消息队列初始化失败: {str(e)}")
                results['unavailable_services'].append('RabbitMQ')
        else:
            print("⚠️ RabbitMQ消息队列不可用，跳过初始化")
            results['unavailable_services'].append('RabbitMQ')
        
        # 检查总体状态 - 至少有核心服务可用即为成功
        core_services_available = len(results['available_services']) > 0
        results['total_success'] = core_services_available
        
        if results['total_success']:
            print(f"✅ 优化服务初始化完成 - 可用: {results['available_services']}")
            if results['unavailable_services']:
                print(f"   不可用服务: {results['unavailable_services']}")
        else:
            print("⚠️ 所有优化服务都不可用，使用基础功能")
            
        return results
        
    except Exception as e:
        print(f"❌ 初始化优化服务时出错: {str(e)}")
        results['error'] = str(e)
        return results

def get_service_status():
    """
    获取所有可用服务的状态
    
    Returns:
        dict: 服务状态信息
    """
    from datetime import datetime
    
    status = {
        'timestamp': datetime.now().isoformat(),
        'services': {},
        'available': [],
        'unavailable': []
    }
    
    try:
        # Redis状态
        if REDIS_AVAILABLE and redis_cache:
            try:
                redis_info = redis_cache.get_cache_info()
                status['services']['redis'] = {
                    'available': True,
                    'connected': bool(redis_cache.redis_client),
                    'info': redis_info
                }
                status['available'].append('Redis')
            except Exception as e:
                status['services']['redis'] = {
                    'available': True,
                    'connected': False,
                    'error': str(e)
                }
                status['unavailable'].append('Redis')
        else:
            status['services']['redis'] = {
                'available': False,
                'reason': 'Redis module not installed'
            }
            status['unavailable'].append('Redis')
        
        # RabbitMQ状态
        if RABBITMQ_AVAILABLE and rabbitmq_service:
            try:
                rabbitmq_info = rabbitmq_service.get_queue_info()
                status['services']['rabbitmq'] = {
                    'available': True,
                    'connected': bool(rabbitmq_service.connection and not rabbitmq_service.connection.is_closed),
                    'queues': rabbitmq_info
                }
                status['available'].append('RabbitMQ')
            except Exception as e:
                status['services']['rabbitmq'] = {
                    'available': True,
                    'connected': False,
                    'error': str(e)
                }
                status['unavailable'].append('RabbitMQ')
        else:
            status['services']['rabbitmq'] = {
                'available': False,
                'reason': 'Pika module not installed'
            }
            status['unavailable'].append('RabbitMQ')
        
        # 核心服务状态（始终可用）
        status['services']['core'] = {
            'NewsService': True,
            'NewsAnalysisService': True,
            'NewsCollectionService': True
        }
        status['available'].extend(['NewsService', 'NewsAnalysisService', 'NewsCollectionService'])
        
    except Exception as e:
        status['error'] = str(e)
    
    return status
