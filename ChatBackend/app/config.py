import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', '616d6f417411a6c6c54e5e561ae52a11c4caccd8f8952e50')
    
    # MongoDB settings
    MONGODB_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI') or 'mongodb://db:27017/'
    
    # News API settings
    NEWS_API_KEY = os.getenv('NEWS_API_KEY')
    NEWS_API_BASE_URL = os.getenv('NEWS_API_BASE_URL', 'https://api.vvhan.com/api/hotlist/all')
    HOTNEWS_DAILYHOT_BASE_URL = os.getenv('HOTNEWS_DAILYHOT_BASE_URL', 'https://api-hot.imsyy.top')
    HOTNEWS_IKUNPAY_BASE_URL = os.getenv('HOTNEWS_IKUNPAY_BASE_URL', 'https://api.ikunpay.com')
    
    # OpenAI settings
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    
    # OpenRouter settings
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
    OPENROUTER_BASE_URL = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    
    # LLM settings
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat-v3-0324:online")
    LLM_REQUEST_TIMEOUT = float(os.getenv('LLM_REQUEST_TIMEOUT', 90.0))
    MAX_TOKENS = int(os.getenv('MAX_TOKENS', 2048))
    
    # Application settings
    MAX_NEWS_ARTICLES = int(os.getenv('MAX_NEWS_ARTICLES', 100))
    TREND_UPDATE_INTERVAL = int(os.getenv('TREND_UPDATE_INTERVAL', 3600))  # 1 hour in seconds
    
    # Qwen API settings
    QWEN_API_KEY = os.getenv('QWEN_API_KEY', '')
    QWEN_BASE_URL = os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    QWEN_MODEL = os.getenv('QWEN_MODEL', 'qwen-plus')
    
    # News analysis settings
    NEWS_UPDATE_INTERVAL = int(os.getenv('NEWS_UPDATE_INTERVAL', 3600))  # 1 hour in seconds
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', 16))
    
    # 热门新闻分析设置
    # 选择热度排名前N的新闻进行分析，不再按每个平台分别选择N条
    TOP_HOT_NEWS_COUNT = int(os.getenv('TOP_HOT_NEWS_COUNT', 50))
    # 兼容旧代码，现已弃用，使用TOP_HOT_NEWS_COUNT替代
    MAX_NEWS_PER_PLATFORM = int(os.getenv('MAX_NEWS_PER_PLATFORM', 2))
    # 每日分析限制
    DAILY_ANALYSIS_LIMIT = int(os.getenv('DAILY_ANALYSIS_LIMIT', 20))
    
    # API采集设置
    # 从各平台API获取热搜时，每平台最多获取的条数
    API_NEWS_PER_PLATFORM = int(os.getenv('API_NEWS_PER_PLATFORM', 20))
    
    # Scheduled tasks settings
    ENABLE_SCHEDULED_TASKS = os.getenv('ENABLE_SCHEDULED_TASKS', 'True').lower() == 'true'
    
    # 智能采集设置
    SMART_COLLECTION_ENABLED = os.getenv('SMART_COLLECTION_ENABLED', 'True').lower() == 'true'
    # 数据变化检测的最大有效时间（分钟）
    MAX_DATA_AGE_MINUTES = int(os.getenv('MAX_DATA_AGE_MINUTES', 55))
    # API热力值阈值，高于此值的新闻触发即时分析
    HOT_NEWS_THRESHOLD = float(os.getenv('HOT_NEWS_THRESHOLD', 0.75))
    # 每次深度分析的最大新闻数量
    MAX_ANALYSIS_NEWS_COUNT = int(os.getenv('MAX_ANALYSIS_NEWS_COUNT', 10))
    # 深度分析的时间间隔（小时）
    DEEP_ANALYSIS_INTERVAL_HOURS = int(os.getenv('DEEP_ANALYSIS_INTERVAL_HOURS', 1))
    # 智能调度开始时间（小时:分钟），例如 "02:00"
    ANALYSIS_SCHEDULE_START = os.getenv('ANALYSIS_SCHEDULE_START', '02:00')
    
    # 平台权重配置
    # Platform weights for news popularity calculation
    PLATFORM_WEIGHTS = {
        'weibo': 1.2,
        'zhihu': 1.1,
        'toutiao': 1.0,
        'baidu': 1.3,
        'bilibili': 0.9,
        'newsqq': 1.0
    }
    DEFAULT_PLATFORM_WEIGHT = 1.0
    
    # Data files
    PROCESSED_RESULTS_FILE = os.getenv('PROCESSED_RESULTS_FILE', 'results/processed_results.json')
    TRANSFORMED_RESULTS_FILE = os.getenv('TRANSFORMED_RESULTS_FILE', 'results/transformed_results.json') 
