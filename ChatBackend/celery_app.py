# ChatBackend/celery_app.py

from celery import Celery
from celery.schedules import timedelta # 用于设置时间间隔
import os
import sys
import traceback
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)

def _ensure_python_paths():
    for path in (REPO_ROOT, CURRENT_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)


_ensure_python_paths()

# 加载环境变量文件
env_files = ['.env.local', '.env.docker', '.env.production', '.env']
for env_file in env_files:
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"Loaded environment variables from {env_file}")
        break
else:
    # 如果没有找到环境变量文件，加载默认的.env文件
    load_dotenv()
    print("Loaded environment variables from default .env file")
from dotenv import load_dotenv

# 加载环境变量文件
env_files = ['.env.local', '.env.docker', '.env.production', '.env']
for env_file in env_files:
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"Loaded environment variables from {env_file}")
        break
else:
    # 如果没有找到环境变量文件，加载默认的.env文件
    load_dotenv()
    print("Loaded environment variables from default .env file")

# 1. 定义 Redis 连接 URL
# 优先从环境变量读取，如果没有则使用默认值
# 默认值假设 Docker Compose 中的 Redis 服务名为 'redis'
redis_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
# 结果后端通常也使用 Redis，但使用不同的数据库编号（例如 1）
result_backend_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

# 2. 创建 Celery 应用实例
# 'tasks' 是 Celery 应用的名称，通常使用包含任务的模块名或项目名
celery = Celery(
    'tasks',
    broker=redis_url,         # 指定消息代理地址
    backend=result_backend_url, # 指定结果存储地址
    include=[
        'ChatBackend.app.tasks',
        'ChatBackend.app.services.chat_service',
        'ChatBackend.app.services.mindspider_bridge_service',
        'ChatBackend.app.services.mindspider_deep_sentiment_service',
        'ChatBackend.app.services.tts_service',
        'ChatBackend.app.services.video_analysis_service',
    ]  # 添加任务模块以便发现任务
)

# 3. 配置 Celery
celery.conf.update(
    task_serializer='json',         # 任务序列化方式
    accept_content=['json'],      # 可接受的内容类型
    result_serializer='json',       # 结果序列化方式
    timezone='Asia/Shanghai',       # 设置时区，建议与 Flask 应用一致
    enable_utc=True,              # 推荐使用 UTC 时间
    task_time_limit=600,          # 设置任务超时时间为10分钟 (600秒)
    task_soft_time_limit=540,     # 设置软超时时间为9分钟 (540秒)，会在硬超时前触发异常，允许任务优雅关闭
    # 可以根据需要添加其他 Celery 配置，例如任务路由、队列等
    # task_routes = {'tasks.add': 'low-priority'},
)

# 4. 处理 Flask 应用上下文的关键部分
# 确保 Celery 任务在执行时能够访问 Flask 的配置、数据库连接等
# 我们需要导入创建 Flask 应用实例的工厂函数
# !! 重要 !!: 确保这里的 'app' 模块和 'create_app' 函数
# 与你的 wsgi.py 和旧的 run.py 中使用的是同一个
try:
    from ChatBackend.app import create_app as create_flask_app
except ImportError:
    try:
        from app import create_app as create_flask_app
    except ImportError:
        print("错误：无法导入 Flask create_app。请确保 Celery 在仓库根目录和正确的 PYTHONPATH 下启动。")
        create_flask_app = None

# 定义一个继承自 celery.Task 的基类，用于自动添加 Flask 应用上下文
class ContextTask(celery.Task):
    abstract = True  # 声明为抽象基类，不会被注册为实际任务
    _flask_app = None # 缓存 Flask app 实例

    @property
    def flask_app(self):
        """惰性加载 Flask 应用实例"""
        if self._flask_app is None:
            _ensure_python_paths()
            factory = create_flask_app
            if factory is None:
                try:
                    from ChatBackend.app import create_app as factory
                except ImportError:
                    try:
                        from app import create_app as factory
                    except ImportError:
                        factory = None
            if factory:
                print("[Celery ContextTask] 正在为 Celery 任务上下文创建 Flask 应用实例...")
                try:
                    self._flask_app = factory()
                    print(f"[Celery ContextTask] Flask 应用实例已创建: {self._flask_app}")
                except Exception as e:
                    print(f"[Celery ContextTask] 创建 Flask 应用实例时出错: {e}")
                    traceback.print_exc()
                    self._flask_app = None # 标记为失败
            else:
                 print("[Celery ContextTask] 错误: Flask 应用工厂函数 'create_flask_app' 不可用。")
                 self._flask_app = None
        return self._flask_app

    def __call__(self, *args, **kwargs):
        """重写 call 方法，在任务执行前推入应用上下文"""
        app_instance = self.flask_app
        if app_instance:
            with app_instance.app_context():
                print(f"[Celery ContextTask] 正在 Flask 应用上下文中运行任务: {self.name}")
                try:
                    return super().__call__(*args, **kwargs)
                except Exception as e:
                    print(f"[Celery ContextTask] 任务 {self.name} 在应用上下文中执行时出错: {e}")
                    traceback.print_exc()
                    # 根据需要可以重新抛出异常或进行其他处理
                    raise
        else:
            print(f"[Celery ContextTask] 错误: 无法获取 Flask 应用实例来运行任务 {self.name}")
            # 抛出异常，让任务失败并可能被重试（如果配置了重试）
            raise RuntimeError(f"无法为任务 {self.name} 创建 Flask 应用上下文。")

# 将我们定义的 ContextTask 设置为所有任务的默认基类
celery.Task = ContextTask

# 5. 配置 Celery Beat 定时任务调度
# 这部分替代了原来 run.py 中的 simple_scheduler 逻辑
celery.conf.beat_schedule = {
    # 核心任务：心跳监控
    'heartbeat-every-minute': {
        'task': 'tasks.heartbeat',
        'schedule': timedelta(minutes=1),
    },
    # 核心任务：智能收集热门新闻
    'smart-collect-every-30-minutes': {
        'task': 'tasks.smart_collect',
        'schedule': timedelta(minutes=30),
    },
    # 核心任务：批量分析新闻（简化版）
    'batch-analyze-every-2-hours': {
        'task': 'tasks.batch_analyze_news',
        'schedule': timedelta(hours=2),
        'kwargs': {'limit': 10},  # 每次分析10条新闻
    },
    # 核心任务：完整流程（采集+分析）
    'full-process-every-4-hours': {
        'task': 'tasks.full_process',
        'schedule': timedelta(hours=4),
        'kwargs': {'collect_limit': 50, 'analyze_limit': 10},
    },
}

print("[Celery App] Celery 应用实例已创建并配置。")
print(f"[Celery App] Broker URL: {redis_url}")
print(f"[Celery App] Result Backend URL: {result_backend_url}")
print(f"[Celery App] 包含的任务模块: {celery.conf.include}")
