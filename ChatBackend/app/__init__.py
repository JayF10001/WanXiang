from flask import Flask
from flask_login import LoginManager, current_user
from flask_cors import CORS
from .models import User
from .extensions import db
from .services.redis_cache_service import get_cache_service
import os
import datetime
import time  # Import time for sleep
from pymongo.errors import ConnectionFailure # Import specific error
import logging # Import logging


LOCAL_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5001",
    "http://127.0.0.1:5001",
]


def _get_env(name, legacy_name=None):
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if legacy_name:
        return os.environ.get(legacy_name, "").strip()
    return ""


def _get_allowed_origins():
    configured = _get_env("WANXIANG_ALLOWED_ORIGINS", "ZHIMO_ALLOWED_ORIGINS")
    if configured:
        return [item.strip() for item in configured.split(",") if item.strip()]
    return list(LOCAL_ALLOWED_ORIGINS)


def create_app():
    app = Flask(__name__)
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import Config
    app.config.from_object(Config)

    debug_enabled = _get_env("WANXIANG_BACKEND_DEBUG", "ZHIMO_BACKEND_DEBUG").lower() in {"1", "true", "yes", "on"}
    app.debug = debug_enabled
    app.config['DEBUG'] = debug_enabled
    
    # 配置日志级别
    app.logger.setLevel(logging.DEBUG)
    
    app.logger.info("Starting WanXiang backend...")
    app.logger.info(f"Debug mode: {'on' if app.debug else 'off'}")
    
    # Initialize extensions
    CORS(app, supports_credentials=True, origins=_get_allowed_origins())
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Initialize database
    db.init_app(app)
    cache_service = get_cache_service()

    app.logger.info(f"Runtime mode: {db.mode}")
    if db.is_mongo_connected:
        app.logger.info("Database status: MongoDB connected")
    elif db.is_in_memory:
        app.logger.warning("Database status: in-memory fallback")
    else:
        app.logger.warning("Database status: unavailable")

    app.logger.info(f"Cache mode: {cache_service.mode}")
    if cache_service.is_connected():
        app.logger.info(f"Redis status: connected ({cache_service.connection_label})")
    else:
        app.logger.warning("Redis status: unavailable, using in-process fallback behavior")

    @app.get("/health")
    def health():
        return {
            "success": True,
            "data": {
                "status": "ok",
                "database": {
                    "mode": db.mode,
                    "mongo_connected": db.is_mongo_connected,
                    "in_memory": db.is_in_memory,
                },
                "cache": {
                    "mode": cache_service.mode,
                    "connected": cache_service.is_connected(),
                    "connection_label": cache_service.connection_label,
                },
            },
            "message": "chatbackend is healthy",
        }

    @login_manager.user_loader
    def load_user(user_id):
        app.logger.info(f"[DEBUG] user_loader called with user_id: {user_id}") 
        try:
            user = User.get(user_id)
            app.logger.info(f"[DEBUG] user_loader: User.get result for ID {user_id}: {user}") 
            if user:
                 app.logger.info(f"[DEBUG] user_loader: Found user details - Username: {getattr(user, 'username', 'N/A')}, Email: {getattr(user, 'email', 'N/A')}")
            return user
        except Exception as e:
            app.logger.error(f"[DEBUG] user_loader: Error during User.get for ID {user_id}: {e}", exc_info=True) # Log traceback
            return None

    # Register blueprints
    from .routes import api_bp as routes_blueprint
    app.register_blueprint(routes_blueprint, url_prefix='/api')
    
    # Create MongoDB indexes with retry logic
    with app.app_context():
        if db.is_in_memory:
            app.logger.warning("Index initialization: skipped (in-memory fallback mode)")
        else:
            from .utils.db_utils import ensure_indexes
            retries = 5
            delay = 3 # seconds
            for i in range(retries):
                try:
                    app.logger.info(f"Index initialization: checking MongoDB availability ({i+1}/{retries})")
                    db.cx.admin.command('ping')
                    if ensure_indexes():
                        app.logger.info("Index initialization: MongoDB indexes ready")
                        break
                    else:
                        app.logger.warning("Index initialization: ensure_indexes returned failure, retrying...")
                except ConnectionFailure as e:
                    app.logger.warning(f"Index initialization: MongoDB unavailable on attempt {i+1}/{retries}, retrying in {delay}s")
                except Exception as e:
                    app.logger.error(f"Index initialization: unexpected error on attempt {i+1}/{retries}: {e}")

                if i < retries - 1:
                    time.sleep(delay)
                else:
                    app.logger.error("Index initialization: failed after multiple retries")

    app.logger.info("Startup summary: backend ready")
    
    return app 
