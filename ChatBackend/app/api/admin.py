from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from ..extensions import db
from app.models import News, User, Chat
import logging
from datetime import datetime
import json
from bson import ObjectId
from bson.errors import InvalidId
import re
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

admin_api = Blueprint('admin_api', __name__)
logger = logging.getLogger(__name__)

# 动态获取数据库集合
def get_available_collections():
    """动态获取数据库中的所有集合"""
    try:
        # 获取数据库中的所有集合名称
        if isinstance(db.db, dict):
            # 内存模式
            collection_names = list(db.db.keys())
        else:
            # MongoDB模式
            collection_names = db.db.list_collection_names()
        
        # 过滤掉系统集合
        filtered_collections = [name for name in collection_names 
                              if not name.startswith('system.') and name != 'fs.files' and name != 'fs.chunks']
        
        return filtered_collections
    except Exception as e:
        logger.error(f"获取集合列表失败: {e}")
        return []

def infer_field_type(value):
    """推断字段类型"""
    if value is None:
        return 'string'  # 默认类型
    elif isinstance(value, ObjectId):
        return 'ObjectId'
    elif isinstance(value, bool):
        return 'boolean'
    elif isinstance(value, int):
        return 'integer'
    elif isinstance(value, float):
        return 'float'
    elif isinstance(value, datetime):
        return 'datetime'
    elif isinstance(value, list):
        return 'array'
    elif isinstance(value, dict):
        return 'object'
    else:
        return 'string'

def infer_input_type(field_name, field_type, value=None):
    """推断表单输入类型"""
    field_name_lower = field_name.lower()
    
    # 根据字段名推断
    if 'email' in field_name_lower:
        return 'email'
    elif 'password' in field_name_lower:
        return 'password'
    elif 'url' in field_name_lower or 'link' in field_name_lower:
        return 'url'
    elif 'content' in field_name_lower or 'description' in field_name_lower or 'text' in field_name_lower:
        return 'textarea'
    elif 'created_at' in field_name_lower or 'updated_at' in field_name_lower or 'published_at' in field_name_lower:
        return 'datetime'
    elif 'keywords' in field_name_lower or 'tags' in field_name_lower:
        return 'tags'
    
    # 根据字段类型推断
    if field_type == 'boolean':
        return 'boolean'
    elif field_type in ['integer', 'float']:
        return 'number'
    elif field_type == 'datetime':
        return 'datetime'
    elif field_type == 'array':
        return 'json'
    elif field_type == 'object':
        return 'json'
    else:
        return 'text'

def analyze_collection_schema(collection_name):
    """分析集合的字段结构"""
    try:
        # 处理内存模式和MongoDB模式
        if isinstance(db.db, dict):
            # 内存模式
            if collection_name not in db.db:
                return {
                    '_id': {
                        'type': 'ObjectId',
                        'editable': False,
                        'primary_key': True,
                        'required': True,
                        'input_type': 'text'
                    }
                }
            
            collection_data = db.db[collection_name]
            sample_docs = list(collection_data.values())[:10]
        else:
            # MongoDB模式
            collection = getattr(db, collection_name)
            sample_docs = list(collection.find().limit(10))
        
        if not sample_docs:
            # 如果没有数据，返回基本的_id字段
            return {
                '_id': {
                    'type': 'ObjectId',
                    'editable': False,
                    'primary_key': True,
                    'required': True,
                    'input_type': 'text'
                }
            }
        
        # 分析所有字段
        all_fields = set()
        field_types = {}
        field_samples = {}
        
        for doc in sample_docs:
            for field_name, value in doc.items():
                all_fields.add(field_name)
                field_type = infer_field_type(value)
                
                # 记录字段类型（取最常见的类型）
                if field_name not in field_types:
                    field_types[field_name] = {}
                if field_type not in field_types[field_name]:
                    field_types[field_name][field_type] = 0
                field_types[field_name][field_type] += 1
                
                # 保存样本值
                if field_name not in field_samples:
                    field_samples[field_name] = value
        
        # 构建字段定义
        fields = {}
        for field_name in all_fields:
            # 获取最常见的类型
            most_common_type = max(field_types[field_name].items(), key=lambda x: x[1])[0]
            sample_value = field_samples[field_name]
            
            fields[field_name] = {
                'type': most_common_type,
                'editable': field_name != '_id',
                'primary_key': field_name == '_id',
                'required': field_name == '_id',  # 只有_id是必需的
                'input_type': infer_input_type(field_name, most_common_type, sample_value)
            }
        
        return fields
        
    except Exception as e:
        logger.error(f"分析集合 {collection_name} 结构失败: {e}")
        return {
            '_id': {
                'type': 'ObjectId',
                'editable': False,
                'primary_key': True,
                'required': True,
                'input_type': 'text'
            }
        }

def serialize_document(doc, fields):
    """序列化MongoDB文档"""
    if not doc:
        return None
    
    result = {}
    for field_name, field_info in fields.items():
        value = doc.get(field_name)
        
        if value is None:
            result[field_name] = None
        elif isinstance(value, ObjectId):
            result[field_name] = str(value)
        elif isinstance(value, datetime):
            result[field_name] = value.isoformat()
        elif isinstance(value, list):
            result[field_name] = value
        else:
            result[field_name] = value
    
    return result

def parse_value(value, field_type):
    """根据字段类型解析值"""
    if value is None or value == '':
        return None
    
    try:
        if field_type == 'ObjectId':
            return ObjectId(value)
        elif field_type == 'datetime':
            if isinstance(value, str):
                # 尝试解析ISO格式的日期时间
                try:
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except:
                    return datetime.now()
            return value
        elif field_type == 'float':
            return float(value)
        elif field_type == 'int':
            return int(value)
        elif field_type == 'array':
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except:
                    return value.split(',') if value else []
            return value if isinstance(value, list) else [value]
        else:
            return value
    except Exception as e:
        logger.warning(f"解析值失败: {value}, 类型: {field_type}, 错误: {e}")
        return value

def build_search_query(search_term, fields):
    """构建搜索查询"""
    if not search_term:
        return {}
    
    # 获取可搜索的文本字段
    text_fields = [name for name, info in fields.items() 
                   if info['type'] in ['string'] and name != '_id']
    
    if not text_fields:
        return {}
    
    # 构建正则表达式搜索
    search_conditions = []
    for field in text_fields:
        search_conditions.append({
            field: {'$regex': search_term, '$options': 'i'}
        })
    
    return {'$or': search_conditions} if search_conditions else {}

def build_sort_query(sort_field, sort_order):
    """构建排序查询"""
    if not sort_field:
        return [('_id', DESCENDING)]  # 默认按ID倒序
    
    direction = DESCENDING if sort_order == 'desc' else ASCENDING
    return [(sort_field, direction)]

@admin_api.route('/collections', methods=['GET'])
@login_required
def get_collections_list():
    """获取可用的集合列表"""
    try:
        collections = []
        collection_names = get_available_collections()
        
        for collection_name in collection_names:
            try:
                # 获取集合统计信息
                collection = getattr(db, collection_name)
                count = collection.count_documents({})
                
                # 分析集合结构
                fields = analyze_collection_schema(collection_name)
                
                # 转换字段格式为前端期望的格式
                columns = []
                for field_name, field_info in fields.items():
                    columns.append({
                        'key': field_name,
                        'title': field_name.replace('_', ' ').title(),
                        'dataIndex': field_name,
                        'type': field_info['type'],
                        'nullable': not field_info.get('required', False),
                        'primary_key': field_info.get('primary_key', False),
                        'autoincrement': False,
                        'input_type': field_info.get('input_type', 'text'),
                        'default': field_info.get('default')
                    })
                
                collections.append({
                    'name': collection_name,
                    'title': collection_name.replace('_', ' ').title(),
                    'collection_name': collection_name,
                    'columns': columns,
                    'total_columns': len(columns)
                })
            except Exception as e:
                logger.warning(f"获取集合 {collection_name} 信息失败: {e}")
                # 如果分析失败，至少返回基本信息
                collections.append({
                    'name': collection_name,
                    'title': collection_name.replace('_', ' ').title(),
                    'collection_name': collection_name,
                    'columns': [{
                        'key': '_id',
                        'title': 'Id',
                        'dataIndex': '_id',
                        'type': 'ObjectId',
                        'nullable': False,
                        'primary_key': True,
                        'autoincrement': False,
                        'input_type': 'text',
                        'default': None
                    }],
                    'total_columns': 1
                })
        
        return jsonify({
            'success': True,
            'data': collections
        })
    except Exception as e:
        logger.error(f"获取集合列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/schema', methods=['GET'])
@login_required
def get_collection_schema(collection_name):
    """获取指定集合的结构信息"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        # 分析集合结构
        fields = analyze_collection_schema(collection_name)
        
        # 转换字段格式为前端期望的格式
        columns = []
        for field_name, field_info in fields.items():
            columns.append({
                'key': field_name,
                'title': field_name.replace('_', ' ').title(),
                'dataIndex': field_name,
                'type': field_info['type'],
                'nullable': not field_info.get('required', False),
                'primary_key': field_info.get('primary_key', False),
                'autoincrement': False,  # MongoDB doesn't have autoincrement
                'input_type': field_info.get('input_type', 'text'),
                'default': field_info.get('default')
            })
        
        return jsonify({
            'success': True,
            'data': {
                'table_name': collection_name,
                'columns': columns
            }
        })
    except Exception as e:
        logger.error(f"获取集合结构失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/data', methods=['GET'])
@login_required
def get_collection_data(collection_name):
    """获取集合数据"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        collection = getattr(db, collection_name)
        fields = analyze_collection_schema(collection_name)
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 20, type=int)
        search = request.args.get('search', '')
        sort_field = request.args.get('sortField', None)
        sort_order = request.args.get('sortOrder', 'desc')
        
        # 构建查询条件
        query = build_search_query(search, fields)
        
        # 构建排序条件
        sort_conditions = build_sort_query(sort_field, sort_order)
        
        # 获取总数
        total = collection.count_documents(query)
        
        # 分页查询
        skip = (page - 1) * page_size
        cursor = collection.find(query).sort(sort_conditions).skip(skip).limit(page_size)
        
        # 序列化数据
        documents = []
        for doc in cursor:
            serialized = serialize_document(doc, fields)
            if serialized:
                documents.append(serialized)
        
        return jsonify({
            'success': True,
            'data': documents,
            'pagination': {
                'current': page,
                'pageSize': page_size,
                'total': total,
                'totalPages': (total + page_size - 1) // page_size
            }
        })
    except Exception as e:
        logger.error(f"获取集合数据失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/data', methods=['POST'])
@login_required
def create_document(collection_name):
    """创建新文档"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        collection = getattr(db, collection_name)
        fields = analyze_collection_schema(collection_name)
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少数据'}), 400
        
        # 构建文档数据
        document = {}
        for field_name, field_info in fields.items():
            if field_name == '_id':
                continue  # MongoDB会自动生成_id
            
            if field_name in data:
                value = parse_value(data[field_name], field_info['type'])
                if value is not None:
                    document[field_name] = value
            elif field_info.get('required', False):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field_name}'}), 400
        
        # 添加创建时间（如果字段存在）
        if 'created_at' in fields:
            document['created_at'] = datetime.utcnow()
        
        # 插入文档
        result = collection.insert_one(document)
        
        # 获取插入的文档
        inserted_doc = collection.find_one({'_id': result.inserted_id})
        serialized_doc = serialize_document(inserted_doc, fields)
        
        return jsonify({
            'success': True,
            'data': serialized_doc,
            'message': '文档创建成功'
        })
    except PyMongoError as e:
        logger.error(f"创建文档失败: {e}")
        return jsonify({'success': False, 'error': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"创建文档失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/data/<document_id>', methods=['PUT'])
@login_required
def update_document(collection_name, document_id):
    """更新文档"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        collection = getattr(db, collection_name)
        fields = analyze_collection_schema(collection_name)
        
        # 验证文档ID
        try:
            obj_id = ObjectId(document_id)
        except InvalidId:
            return jsonify({'success': False, 'error': '无效的文档ID'}), 400
        
        # 检查文档是否存在
        existing_doc = collection.find_one({'_id': obj_id})
        if not existing_doc:
            return jsonify({'success': False, 'error': '文档不存在'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少数据'}), 400
        
        # 构建更新数据
        update_data = {}
        for field_name, field_info in fields.items():
            if field_name == '_id' or not field_info.get('editable', True):
                continue  # 跳过不可编辑的字段
            
            if field_name in data:
                value = parse_value(data[field_name], field_info['type'])
                if value is not None:
                    update_data[field_name] = value
        
        if not update_data:
            return jsonify({'success': False, 'error': '没有可更新的数据'}), 400
        
        # 更新文档
        result = collection.update_one(
            {'_id': obj_id},
            {'$set': update_data}
        )
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'error': '文档更新失败'}), 500
        
        # 获取更新后的文档
        updated_doc = collection.find_one({'_id': obj_id})
        serialized_doc = serialize_document(updated_doc, fields)
        
        return jsonify({
            'success': True,
            'data': serialized_doc,
            'message': '文档更新成功'
        })
    except PyMongoError as e:
        logger.error(f"更新文档失败: {e}")
        return jsonify({'success': False, 'error': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"更新文档失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/data/<document_id>', methods=['DELETE'])
@login_required
def delete_document(collection_name, document_id):
    """删除文档"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        collection = getattr(db, collection_name)
        
        # 验证文档ID
        try:
            obj_id = ObjectId(document_id)
        except InvalidId:
            return jsonify({'success': False, 'error': '无效的文档ID'}), 400
        
        # 检查文档是否存在
        existing_doc = collection.find_one({'_id': obj_id})
        if not existing_doc:
            return jsonify({'success': False, 'error': '文档不存在'}), 404
        
        # 删除文档
        result = collection.delete_one({'_id': obj_id})
        
        if result.deleted_count == 0:
            return jsonify({'success': False, 'error': '文档删除失败'}), 500
        
        return jsonify({
            'success': True,
            'message': '文档删除成功'
        })
    except PyMongoError as e:
        logger.error(f"删除文档失败: {e}")
        return jsonify({'success': False, 'error': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/data/batch', methods=['DELETE'])
@login_required
def batch_delete_documents(collection_name):
    """批量删除文档"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        collection = getattr(db, collection_name)
        
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'success': False, 'error': '缺少要删除的文档ID'}), 400
        
        ids = data['ids']
        if not isinstance(ids, list) or not ids:
            return jsonify({'success': False, 'error': '无效的ID列表'}), 400
        
        # 转换为ObjectId
        object_ids = []
        for id_str in ids:
            try:
                object_ids.append(ObjectId(id_str))
            except InvalidId:
                return jsonify({'success': False, 'error': f'无效的文档ID: {id_str}'}), 400
        
        # 批量删除
        result = collection.delete_many({'_id': {'$in': object_ids}})
        
        return jsonify({
            'success': True,
            'message': f'成功删除 {result.deleted_count} 个文档'
        })
    except PyMongoError as e:
        logger.error(f"批量删除文档失败: {e}")
        return jsonify({'success': False, 'error': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"批量删除文档失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/export', methods=['GET'])
@login_required
def export_collection_data(collection_name):
    """导出集合数据"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
            
        collection = getattr(db, collection_name)
        fields = analyze_collection_schema(collection_name)
        
        # 获取所有文档
        cursor = collection.find({})
        documents = []
        for doc in cursor:
            serialized = serialize_document(doc, fields)
            if serialized:
                documents.append(serialized)
        
        # 准备导出数据，同时支持新旧格式
        field_names = list(fields.keys())
        
        return jsonify({
            'success': True,
            'data': {
                'collection_name': collection_name,
                # 新格式 - 前端期望的格式
                'columns': field_names,
                'rows': documents,
                # 旧格式 - 保持向后兼容
                'fields': field_names,
                'documents': documents,
                'total': len(documents)
            }
        })
    except Exception as e:
        logger.error(f"导出集合数据失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>/import', methods=['POST'])
@login_required
def import_collection_data(collection_name):
    """导入数据到集合（支持JSON和CSV格式）"""
    try:
        logger.info(f"开始导入数据到集合: {collection_name}")
        logger.info(f"请求文件: {list(request.files.keys())}")
        logger.info(f"请求表单数据: {dict(request.form)}")
        
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            logger.error(f"集合不存在: {collection_name}, 可用集合: {available_collections}")
            return jsonify({'success': False, 'error': '集合不存在'}), 404
        
        # 检查是否有上传的文件
        if 'file' not in request.files:
            logger.error(f"未找到上传文件，请求文件键: {list(request.files.keys())}")
            return jsonify({'success': False, 'error': '未找到上传文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400
        
        # 检查文件类型
        filename = file.filename.lower()
        if not (filename.endswith('.json') or filename.endswith('.csv')):
            return jsonify({'success': False, 'error': '仅支持JSON和CSV格式文件'}), 400
        
        # 读取文件内容
        file_content = file.read().decode('utf-8')
        
        # 获取集合结构信息
        fields = analyze_collection_schema(collection_name)
        field_names = set(fields.keys())
        
        # 解析文件数据
        import_data = []
        
        if filename.endswith('.json'):
            # 解析JSON文件
            try:
                json_data = json.loads(file_content)
                
                # 支持两种JSON格式：数组或单个对象
                if isinstance(json_data, list):
                    import_data = json_data
                elif isinstance(json_data, dict):
                    import_data = [json_data]
                else:
                    return jsonify({'success': False, 'error': 'JSON文件格式错误，应为对象或对象数组'}), 400
                    
            except json.JSONDecodeError as e:
                # 如果标准JSON解析失败，尝试JSONL格式（每行一个JSON对象）
                logger.info(f"标准JSON解析失败，尝试JSONL格式: {e}")
                try:
                    import_data = []
                    for line_num, line in enumerate(file_content.strip().split('\n'), 1):
                        line = line.strip()
                        if line:  # 跳过空行
                            try:
                                obj = json.loads(line)
                                import_data.append(obj)
                            except json.JSONDecodeError as line_error:
                                logger.error(f"JSONL第{line_num}行解析失败: {line_error}")
                                return jsonify({'success': False, 'error': f'JSONL第{line_num}行解析失败: {str(line_error)}'}), 400
                    
                    if not import_data:
                        return jsonify({'success': False, 'error': 'JSON文件为空或格式不正确'}), 400
                        
                    logger.info(f"成功解析JSONL格式文件，共{len(import_data)}条记录")
                except Exception as jsonl_error:
                    logger.error(f"JSON和JSONL解析都失败: 原始错误={e}, JSONL错误={jsonl_error}")
                    return jsonify({'success': False, 'error': f'JSON文件解析失败: {str(e)}'}), 400
        
        elif filename.endswith('.csv'):
            # 解析CSV文件
            try:
                import csv
                from io import StringIO
                
                csv_reader = csv.DictReader(StringIO(file_content))
                import_data = list(csv_reader)
                
                if not import_data:
                    return jsonify({'success': False, 'error': 'CSV文件为空或格式错误'}), 400
                    
            except Exception as e:
                return jsonify({'success': False, 'error': f'CSV文件解析失败: {str(e)}'}), 400
        
        if not import_data:
            return jsonify({'success': False, 'error': '文件中没有有效数据'}), 400
        
        # 验证列名
        sample_record = import_data[0]
        import_columns = set(sample_record.keys())
        
        # 检查必需的列是否存在
        missing_columns = []
        extra_columns = []
        
        # 找出缺失的必需列（非自增主键，_id字段除外，因为它会自动生成）
        for field_name, field_info in fields.items():
            if field_info.get('required', False) and not field_info.get('autoincrement', False) and field_name != '_id':
                if field_name not in import_columns:
                    missing_columns.append(field_name)
        
        # 找出多余的列
        for col in import_columns:
            if col not in field_names:
                extra_columns.append(col)
        
        # 构建验证结果
        validation_info = {
            'total_records': len(import_data),
            'missing_columns': missing_columns,
            'extra_columns': extra_columns,
            'valid_columns': list(import_columns & field_names)
        }
        
        # 如果有严重错误，返回验证信息
        if missing_columns:
            return jsonify({
                'success': False, 
                'error': f'缺少必需的列: {", ".join(missing_columns)}',
                'validation': validation_info
            }), 400
        
        # 数据类型转换和验证
        processed_data = []
        errors = []
        
        for i, record in enumerate(import_data):
            try:
                processed_record = {}
                
                for field_name, field_info in fields.items():
                    if field_name in record:
                        value = record[field_name]
                        
                        # 跳过空值（除非是必需字段）
                        if value == '' or value is None:
                            if field_info.get('required', False) and not field_info.get('autoincrement', False):
                                errors.append(f'第{i+1}行: {field_name} 不能为空')
                                continue
                            else:
                                processed_record[field_name] = None
                                continue
                        
                        # 根据字段类型转换数据
                        try:
                            if field_info['type'] == 'int':
                                processed_record[field_name] = int(value)
                            elif field_info['type'] == 'float':
                                processed_record[field_name] = float(value)
                            elif field_info['type'] == 'bool':
                                if isinstance(value, str):
                                    processed_record[field_name] = value.lower() in ('true', '1', 'yes', 'on')
                                else:
                                    processed_record[field_name] = bool(value)
                            elif field_info['type'] == 'datetime':
                                from datetime import datetime
                                if isinstance(value, str):
                                    # 尝试多种日期格式
                                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d']:
                                        try:
                                            processed_record[field_name] = datetime.strptime(value, fmt)
                                            break
                                        except ValueError:
                                            continue
                                    else:
                                        # 如果所有格式都失败，尝试ISO格式
                                        processed_record[field_name] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                else:
                                    processed_record[field_name] = value
                            elif field_info['type'] in ['array', 'object']:
                                if isinstance(value, str):
                                    try:
                                        processed_record[field_name] = json.loads(value)
                                    except json.JSONDecodeError:
                                        processed_record[field_name] = value
                                else:
                                    processed_record[field_name] = value
                            else:
                                processed_record[field_name] = str(value)
                                
                        except (ValueError, TypeError) as e:
                            errors.append(f'第{i+1}行: {field_name} 数据类型转换失败 - {str(e)}')
                            continue
                
                # 为自增字段生成ID
                if '_id' not in processed_record:
                    processed_record['_id'] = ObjectId()
                
                processed_data.append(processed_record)
                
            except Exception as e:
                errors.append(f'第{i+1}行: 处理失败 - {str(e)}')
        
        # 如果有太多错误，返回错误信息
        if len(errors) > len(import_data) * 0.5:  # 如果超过50%的记录有错误
            return jsonify({
                'success': False,
                'error': '数据错误过多，请检查文件格式',
                'validation': validation_info,
                'errors': errors[:10]  # 只返回前10个错误
            }), 400
        
        # 执行批量插入
        collection = getattr(db, collection_name)
        inserted_count = 0
        
        if isinstance(db.db, dict):
            # 内存模式
            if collection_name not in db.db:
                db.db[collection_name] = {}
            
            for record in processed_data:
                doc_id = str(record['_id'])
                db.db[collection_name][doc_id] = record
                inserted_count += 1
        else:
            # MongoDB模式
            if processed_data:
                result = collection.insert_many(processed_data)
                inserted_count = len(result.inserted_ids)
        
        # 返回导入结果
        result_info = {
            'success': True,
            'message': f'成功导入 {inserted_count} 条记录',
            'data': {
                'inserted_count': inserted_count,
                'total_records': len(import_data),
                'error_count': len(errors),
                'validation': validation_info
            }
        }
        
        if errors:
            result_info['warnings'] = errors[:5]  # 返回前5个警告
        
        return jsonify(result_info)
        
    except Exception as e:
        logger.error(f"导入集合 {collection_name} 数据失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/stats', methods=['GET'])
@login_required
def get_admin_stats():
    """获取管理统计信息"""
    try:
        stats = {}
        collection_names = get_available_collections()
        
        for collection_name in collection_names:
            try:
                collection = getattr(db, collection_name)
                count = collection.count_documents({})
                stats[collection_name] = {
                    'total': count,
                    'title': collection_name.replace('_', ' ').title()
                }
            except Exception as e:
                logger.warning(f"获取集合 {collection_name} 统计信息失败: {e}")
                stats[collection_name] = {
                    'total': 0,
                    'title': collection_name.replace('_', ' ').title()
                }
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_api.route('/collections/<collection_name>', methods=['DELETE'])
@login_required
def delete_collection(collection_name):
    """删除整个集合"""
    try:
        available_collections = get_available_collections()
        if collection_name not in available_collections:
            return jsonify({'success': False, 'error': '集合不存在'}), 404
        
        # 安全检查：防止删除重要的系统集合
        protected_collections = ['users']  # 保护用户集合
        if collection_name in protected_collections:
            return jsonify({
                'success': False, 
                'error': f'集合 "{collection_name}" 是受保护的系统集合，不能删除'
            }), 403
        
        collection = getattr(db, collection_name)
        
        # 获取删除前的文档数量
        doc_count = collection.count_documents({})
        
        if isinstance(db.db, dict):
            # 内存模式：直接删除字典中的集合
            if collection_name in db.db:
                del db.db[collection_name]
                logger.info(f"内存模式：成功删除集合 {collection_name}，包含 {doc_count} 个文档")
            else:
                return jsonify({'success': False, 'error': '集合不存在'}), 404
        else:
            # MongoDB模式：删除集合
            collection.drop()
            logger.info(f"MongoDB模式：成功删除集合 {collection_name}，包含 {doc_count} 个文档")
        
        return jsonify({
            'success': True,
            'message': f'成功删除集合 "{collection_name}"，共删除 {doc_count} 个文档'
        })
        
    except Exception as e:
        logger.error(f"删除集合 {collection_name} 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 兼容性路由 - 保持与原API的兼容性
@admin_api.route('/tables', methods=['GET'])
@login_required
def get_available_tables():
    """获取可用的表列表（兼容性接口）"""
    return get_collections_list()

@admin_api.route('/tables/<table_name>/schema', methods=['GET'])
@login_required
def get_table_schema(table_name):
    """获取指定表的结构信息（兼容性接口）"""
    return get_collection_schema(table_name)

@admin_api.route('/tables/<table_name>/data', methods=['GET'])
@login_required
def get_table_data(table_name):
    """获取表数据（兼容性接口）"""
    return get_collection_data(table_name)

@admin_api.route('/tables/<table_name>/data', methods=['POST'])
@login_required
def create_record(table_name):
    """创建新记录（兼容性接口）"""
    return create_document(table_name)

@admin_api.route('/tables/<table_name>/data/<record_id>', methods=['PUT'])
@login_required
def update_record(table_name, record_id):
    """更新记录（兼容性接口）"""
    return update_document(table_name, record_id)

@admin_api.route('/tables/<table_name>/data/<record_id>', methods=['DELETE'])
@login_required
def delete_record(table_name, record_id):
    """删除记录（兼容性接口）"""
    return delete_document(table_name, record_id)

@admin_api.route('/tables/<table_name>/data/batch', methods=['DELETE'])
@login_required
def batch_delete_records(table_name):
    """批量删除记录（兼容性接口）"""
    return batch_delete_documents(table_name)

@admin_api.route('/tables/<table_name>/export', methods=['GET'])
@login_required
def export_table_data(table_name):
    """导出表数据（兼容性接口）"""
    return export_collection_data(table_name)

@admin_api.route('/tables/<table_name>', methods=['DELETE'])
@login_required
def delete_table(table_name):
    """删除表（兼容性接口）"""
    return delete_collection(table_name)

@admin_api.route('/tables/<table_name>/import', methods=['POST'])
@login_required
def import_table_data(table_name):
    """导入表数据（兼容性接口）"""
    return import_collection_data(table_name)
