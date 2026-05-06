from flask import Blueprint

# 创建父级Blueprint
api_blueprint = Blueprint('api', __name__, url_prefix='/api/v1')

# 导入并注册子级Blueprint
from .chat import chat_api
from .report import report_api
from .admin import admin_api
from .knowledge import knowledge_api
from .rag import rag_api

api_blueprint.register_blueprint(chat_api, url_prefix='/chat')
api_blueprint.register_blueprint(report_api, url_prefix='/reports')
api_blueprint.register_blueprint(admin_api, url_prefix='/admin')
api_blueprint.register_blueprint(knowledge_api)
api_blueprint.register_blueprint(rag_api)

# Blueprint注册函数
def register_blueprints(app):
    app.register_blueprint(api_blueprint) 
