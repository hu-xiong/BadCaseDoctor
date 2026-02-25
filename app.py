from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import pymysql
from dotenv import load_dotenv
import random
import string
from config import Config
from werkzeug.utils import secure_filename
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError
import mimetypes
from sqlalchemy import text, inspect
from PIL import Image
import io
import time
from collections import defaultdict
import redis
import base64
from urllib.parse import unquote
import subprocess
import threading
import time
import signal
import os

from routers.chat import chat_bp
from routers.agent import agent_bp
from routers.payment import payment_bp

# 导入 Prometheus
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# Flask应用配置
app.config['SECRET_KEY'] = 'hxReligi12.-badcase-doctor-secret-key-2025'  # 添加SECRET_KEY配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///badcase_doctor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# 数据库连接池配置 - 解决MySQL连接断开问题
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 15,  # 增加连接池大小
    'pool_timeout': 30,  # 增加超时时间
    'pool_recycle': 3600,  # 1小时后回收连接
    'max_overflow': 30,  # 增加最大溢出连接数
    'pool_pre_ping': True,  # 连接前ping一下，确保连接有效
    'echo': False,  # 关闭SQL日志，提高性能
}

# 添加CORS支持
CORS(app, supports_credentials=True, origins=['http://localhost:3000', 'http://localhost:5173', 'http://localhost:8080', 'http://127.0.0.1:3000', 'http://127.0.0.1:5173', 'http://127.0.0.1:8080'])

# 全局 OPTIONS 处理器 - 处理 CORS 预检请求
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """处理所有 OPTIONS 请求（CORS 预检）"""
    response = app.make_response(('', 204))
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response

# 邮件配置 - 使用环境变量
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.163.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 465))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'false').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
app.register_blueprint(chat_bp)
app.register_blueprint(agent_bp)
app.register_blueprint(payment_bp)

# MinIO配置
MINIO_CONFIG = {
    'endpoint': 'http://117.72.33.38:9901',
    'access_key': 'admin',
    'secret_key': 'hxReligi12.',
    'bucket_name': 'apaas-root',  # 使用rootQABucketName
    'saas_file_path': 'saas_qa_file/',
    'max_file_size': 524288000,  # 500MB
    'max_sum_file_size': 524288000  # 500MB
}

# Redis配置
REDIS_CONFIG = {
    'host': '117.72.33.38',
    'port': 26378,
    'password': 'Religi12,.',
    'db': 0,
    'decode_responses': False  # 不自动解码，因为我们要存储二进制数据
}

# 允许上传的文件类型
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 全局MinIO客户端实例，避免重复创建
_minio_client = None
_bucket_checked = False

# 全局Redis客户端实例
_redis_client = None

# 防盗刷：访问频率限制
_avatar_access_log = defaultdict(list)  # 记录每个用户的访问时间
MAX_AVATAR_REQUESTS_PER_MINUTE = 60  # 每分钟最多60次头像请求
_avatar_access_cleanup_time = time.time()  # 上次清理时间

# 初始化MinIO客户端
def get_minio_client():
    global _minio_client
    if _minio_client is None:
        _minio_client = boto3.client(
            's3',
            endpoint_url=MINIO_CONFIG['endpoint'],
            aws_access_key_id=MINIO_CONFIG['access_key'],
            aws_secret_access_key=MINIO_CONFIG['secret_key'],
            region_name='us-east-1',  # MinIO默认区域
            config=boto3.session.Config(
                connect_timeout=10,  # 连接超时10秒
                read_timeout=30,     # 读取超时30秒
                retries={'max_attempts': 3}  # 最大重试3次
            )
        )
    return _minio_client

# 初始化Redis客户端
def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            print(f"正在连接Redis: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
            _redis_client = redis.Redis(
                host=REDIS_CONFIG['host'],
                port=REDIS_CONFIG['port'],
                password=REDIS_CONFIG['password'],
                db=REDIS_CONFIG['db'],
                decode_responses=REDIS_CONFIG['decode_responses'],
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试连接
            _redis_client.ping()
            print("✅ Redis连接成功")
        except Exception as e:
            print(f"❌ Redis连接失败: {e}")
            _redis_client = None
    return _redis_client

# 全局进程管理
active_processes = {}

# ==================== Prometheus 指标端点 ====================

@app.route('/metrics', methods=['GET'])
def metrics():
    """
    暴露 Prometheus 指标端点
    使用 curl http://localhost:5000/metrics 查看
    """
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

# ==================== 终端接口 ====================
@app.route('/api/terminal/exec', methods=['POST'])
@login_required
def terminal_exec():
    try:
        data = request.get_json(force=True) or {}
        cmd = data.get('command', '').strip()
        cwd = data.get('cwd') or os.getcwd()
        timeout = int(data.get('timeout', 30))
        session_id = data.get('session_id', 'default')

        if not cmd:
            return jsonify({ 'success': False, 'error': '命令不能为空' }), 400

        # 安全防护（黑名单示例，可按需扩展）
        forbidden = ['rm -rf /', 'shutdown', 'reboot', 'sudo rm -rf']
        for f in forbidden:
            if f in cmd:
                return jsonify({ 'success': False, 'error': '危险命令已被阻止' }), 400

        # 使用 subprocess 执行命令，更简单可靠
        try:
            # 执行命令
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
            
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = "命令执行超时"
            exit_code = -1
        except Exception as e:
            stdout = ""
            stderr = f"执行错误: {str(e)}"
            exit_code = -1
        
        # subprocess 不会包含命令回显，直接清理首尾空白
        if stdout:
            stdout = stdout.strip()
        if stderr:
            stderr = stderr.strip()

        return jsonify({
            'success': True,
            'code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
            'cwd': cwd
        })
        
    except Exception as e:
        return jsonify({ 'success': False, 'error': str(e) }), 500

# 终止终端会话
@app.route('/api/terminal/kill', methods=['POST'])
@login_required
def terminal_kill():
    try:
        data = request.get_json(force=True) or {}
        session_id = data.get('session_id', 'default')
        
        if session_id in active_processes:
            process_info = active_processes[session_id]
            process = process_info['process']
            
            if process.isalive():
                process.terminate()
                time.sleep(0.5)
                if process.isalive():
                    process.kill()
            
            del active_processes[session_id]
            
        return jsonify({ 'success': True, 'message': '会话已终止' })
        
    except Exception as e:
        return jsonify({ 'success': False, 'error': str(e) }), 500

# 获取终端会话状态
@app.route('/api/terminal/status', methods=['GET'])
@login_required
def terminal_status():
    try:
        session_id = request.args.get('session_id', 'default')
        
        if session_id in active_processes:
            process_info = active_processes[session_id]
            process = process_info['process']
            
            return jsonify({
                'success': True,
                'alive': process.isalive(),
                'cwd': process_info['cwd'],
                'created_at': process_info['created_at']
            })
        else:
            return jsonify({
                'success': True,
                'alive': False,
                'cwd': os.getcwd(),
                'created_at': None
            })
            
    except Exception as e:
        return jsonify({ 'success': False, 'error': str(e) }), 500

# 检查并创建存储桶
def ensure_bucket_exists():
    global _bucket_checked
    if _bucket_checked:
        return True
        
    try:
        client = get_minio_client()
        
        # 检查存储桶是否存在
        try:
            client.head_bucket(Bucket=MINIO_CONFIG['bucket_name'])
            print(f"存储桶 {MINIO_CONFIG['bucket_name']} 已存在")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # 存储桶不存在，创建它
                print(f"存储桶 {MINIO_CONFIG['bucket_name']} 不存在，正在创建...")
                client.create_bucket(Bucket=MINIO_CONFIG['bucket_name'])
                print(f"存储桶 {MINIO_CONFIG['bucket_name']} 创建成功")
            else:
                print(f"检查存储桶时出错: {e}")
                return False
        
        _bucket_checked = True
        return True
    except Exception as e:
        print(f"MinIO连接失败: {e}")
        return False

# 判断文件类型
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 检查头像访问频率
def check_avatar_access_rate(user_id):
    """检查用户头像访问频率，防止盗刷"""
    global _avatar_access_log, _avatar_access_cleanup_time
    
    current_time = time.time()
    
    # 每小时清理一次过期的访问记录，防止内存泄漏
    if current_time - _avatar_access_cleanup_time > 3600:  # 1小时
        _avatar_access_cleanup_time = current_time
        # 清理所有超过1小时的记录
        for uid in list(_avatar_access_log.keys()):
            _avatar_access_log[uid] = [t for t in _avatar_access_log[uid] if current_time - t < 3600]
            # 如果用户没有访问记录，删除该用户
            if not _avatar_access_log[uid]:
                del _avatar_access_log[uid]
    
    user_log = _avatar_access_log[user_id]
    
    # 清理超过1分钟的记录
    user_log = [t for t in user_log if current_time - t < 60]
    _avatar_access_log[user_id] = user_log
    
    # 检查是否超过限制
    if len(user_log) >= MAX_AVATAR_REQUESTS_PER_MINUTE:
        return False
    
    # 添加当前访问记录
    user_log.append(current_time)
    _avatar_access_log[user_id] = user_log
    
    return True

# 压缩图片文件
def compress_image(file, max_size=(800, 800), quality=85):
    """压缩图片文件，减少文件大小"""
    try:
        # 打开图片
        image = Image.open(file)
        
        # 转换为RGB模式（如果是RGBA，去除透明通道）
        if image.mode in ('RGBA', 'LA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 调整图片大小
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 保存到内存中
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return output
    except Exception as e:
        print(f"图片压缩失败: {e}")
        # 如果压缩失败，返回原文件
        file.seek(0)
        return file

# 上传文件到MinIO
def upload_file_to_minio(file, folder_path=''):
    try:
        # 确保存储桶存在
        if not ensure_bucket_exists():
            return {
                'success': False,
                'error': 'MinIO存储桶不可用'
            }
        
        client = get_minio_client()
        
        # 生成安全的文件名，包含项目ID用于权限控制
        # 处理压缩后的文件对象（BytesIO）和原始文件对象
        if hasattr(file, 'filename'):
            # 原始文件对象
            original_filename = secure_filename(file.filename)
            file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        else:
            # 压缩后的文件对象，使用默认文件名
            original_filename = "compressed_image"
            file_extension = 'jpg'  # 压缩后统一为JPEG格式
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 如果是头像上传，添加项目ID到文件名中
        if folder_path == 'avatar':
            # 从请求中获取项目ID（如果有的话）
            project_id = request.args.get('project_id', 'unknown')
            if file_extension:
                safe_filename = f"project_{project_id}_{timestamp}_{original_filename}.{file_extension}"
            else:
                safe_filename = f"project_{project_id}_{timestamp}_{original_filename}.jpg"
        else:
            if file_extension:
                safe_filename = f"{timestamp}_{original_filename}.{file_extension}"
            else:
                safe_filename = f"{timestamp}_{original_filename}.jpg"
        
        # 构建完整的文件路径
        file_path = f"{MINIO_CONFIG['saas_file_path']}{folder_path}/{safe_filename}" if folder_path else f"{MINIO_CONFIG['saas_file_path']}{safe_filename}"
        
        # 获取文件的MIME类型
        if hasattr(file, 'filename'):
            content_type = mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
        else:
            # 压缩后的文件统一为JPEG格式
            content_type = 'image/jpeg'
        
        # 对于头像文件，添加压缩和优化
        extra_args = {'ContentType': content_type}
        if folder_path == 'avatar' and content_type.startswith('image/'):
            # 头像文件优化：添加缓存控制
            extra_args.update({
                'CacheControl': 'public, max-age=31536000',  # 1年缓存
                'Metadata': {
                    'optimized': 'true',
                    'upload-time': timestamp
                }
            })
        
        # 上传文件到MinIO
        client.upload_fileobj(
            file,
            MINIO_CONFIG['bucket_name'],
            file_path,
            ExtraArgs=extra_args
        )
        
        # 返回文件的访问URL - 使用MinIO的直接访问URL
        # 不使用预签名URL，避免重启后URL过期的问题
        file_url = f"{MINIO_CONFIG['endpoint']}/{MINIO_CONFIG['bucket_name']}/{file_path}"
        
        # 添加调试信息
        print(f"文件上传成功:")
        print(f"  - 文件名: {safe_filename}")
        print(f"  - 文件路径: {file_path}")
        print(f"  - 访问URL: {file_url}")
        
        return {
            'success': True,
            'url': file_url,
            'filename': safe_filename,
            'path': file_path
        }
        
    except ClientError as e:
        print(f"MinIO上传错误: {e}")
        return {
            'success': False,
            'error': f"文件上传失败: {str(e)}"
        }
    except Exception as e:
        print(f"文件上传异常: {e}")
        return {
            'success': False,
            'error': f"文件上传异常: {str(e)}"
        }

# 从MinIO删除文件
def delete_file_from_minio(file_path):
    try:
        client = get_minio_client()
        client.delete_object(
            Bucket=MINIO_CONFIG['bucket_name'],
            Key=file_path
        )
        return True
    except Exception as e:
        print(f"删除文件失败: {e}")
        return False

def get_image_from_cache(cache_key):
    """从Redis缓存获取图片数据"""
    try:
        redis_client = get_redis_client()
        if redis_client is None:
            print("❌ Redis客户端未初始化")
            return None
        
        print(f"🔍 尝试从Redis缓存获取: {cache_key}")
        cached_data = redis_client.get(cache_key)
        if cached_data:
            print(f"✅ 从Redis缓存获取图片成功: {cache_key}, 大小: {len(cached_data)} 字节")
            return cached_data
        else:
            print(f"❌ Redis缓存中未找到: {cache_key}")
        return None
    except Exception as e:
        print(f"❌ 从Redis缓存获取图片失败: {e}")
        return None

def set_image_to_cache(cache_key, image_data, expire_time=600):
    """将图片数据存储到Redis缓存，默认10分钟过期"""
    try:
        redis_client = get_redis_client()
        if redis_client is None:
            print("❌ Redis客户端未初始化，无法缓存")
            return False
        
        print(f"💾 正在缓存图片到Redis: {cache_key}, 大小: {len(image_data)} 字节, 过期时间: {expire_time}秒")
        redis_client.setex(cache_key, expire_time, image_data)
        print(f"✅ 图片已成功缓存到Redis: {cache_key}")
        return True
    except Exception as e:
        print(f"❌ 缓存图片到Redis失败: {e}")
        return False

def get_image_cache_key(filename):
    """生成图片缓存键"""
    return f"avatar:{filename}"

db = SQLAlchemy(app)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 自定义未授权处理器，让API路由返回JSON错误
@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/'):
        return jsonify({'error': '未登录'}), 401
    return redirect(url_for('login'))

# 自定义过滤器
@app.template_filter('nl2br')
def nl2br_filter(text):
    if text:
        # 先清理已有的HTML标签，然后重新添加换行符
        import re
        # 移除已有的<br>标签
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        # 移除其他HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 将换行符转换为<br>标签
        return text.replace('\n', '<br>')
    return text

# 将函数添加到模板全局上下文
@app.context_processor
def inject_functions():
    return {
        'has_project_permission': has_project_permission
    }

# 数据模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='collaborator')  # admin, collaborator
    is_verified = db.Column(db.Boolean, default=False)  # 邮箱验证状态
    verification_code = db.Column(db.String(10))  # 邮箱验证码
    verification_expires = db.Column(db.DateTime)  # 验证码过期时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserCredits(db.Model):
    """用户额度表"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    credits = db.Column(db.Integer, default=0)  # 剩余使用次数
    total_purchased = db.Column(db.Integer, default=0)  # 累计购买次数
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaymentHistory(db.Model):
    """支付历史记录"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_id = db.Column(db.String(50), nullable=False)  # basic/standard/professional/enterprise
    credits = db.Column(db.Integer, nullable=False)  # 购买的额度
    amount = db.Column(db.Integer, nullable=False)  # 支付金额(美分)
    stripe_session_id = db.Column(db.String(200))  # Stripe 会话ID
    status = db.Column(db.String(20), default='pending')  # pending/completed/failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    avatar = db.Column(db.String(500))  # 项目头像URL
    owner = db.Column(db.String(100))  # 负责人名称
    intro = db.Column(db.Text)  # 项目介绍语
    status = db.Column(db.String(20), default='published')  # published, unpublished
    login_configs = db.Column(db.Text)  # 网站登录配置 JSON: [{"url": "...", "username": "...", "password": "..."}]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ProjectPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, collaborator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    project = db.relationship('Project', backref='permissions')
    user = db.relationship('User', backref='project_permissions')

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    project = db.relationship('Project', backref='teams')
    creator = db.relationship('User', backref='created_teams')

class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member')  # leader, member
    permissions = db.Column(db.Text)  # 权限JSON字符串
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    team = db.relationship('Team', backref='members')
    user = db.relationship('User', backref='team_memberships')

class BadCase(db.Model):
    __tablename__ = 'bad_case'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))  # 关联计划
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200))  # BadCase标题
    case_category = db.Column(db.String(100), nullable=False)  # 问题分类
    base_problem = db.Column(db.Text, nullable=False)  # 具体问题
    reproduction_steps = db.Column(db.Text)  # 复现步骤
    badcase_result = db.Column(db.Text, nullable=False)  # badcase问题结果
    correct_answer = db.Column(db.Text, nullable=False)  # 应该得到的正确答案
    correct_answer_final = db.Column(db.Text)  # 最终正确答案
    problem_reason = db.Column(db.Text)  # 问题原因
    needs_processing = db.Column(db.Boolean, default=True)  # 是否需要处理
    solution = db.Column(db.Text)  # 解决方式
    is_verified = db.Column(db.Boolean, default=False)  # 是否验证
    priority = db.Column(db.String(10), default='p3')  # p1, p2, p3
    status = db.Column(db.String(20), default='new')  # new, pending, resolved, hold, reopen, close
    assignee = db.Column(db.String(100))  # 负责人
    plan = db.Column(db.String(100))  # 所属计划（保留字段，用于向后兼容）
    document_type = db.Column(db.String(100))  # 文档类型
    attachments = db.Column(db.Text)  # 附件信息，JSON格式存储
    assigned_users = db.Column(db.Text)  # 指派的人员，JSON格式存储
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    project = db.relationship('Project', backref='badcases')
    plan_relation = db.relationship('Plan', backref='badcases')
    creator = db.relationship('User', backref='created_badcases')

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    badcase_id = db.Column(db.Integer, db.ForeignKey('bad_case.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)  # 富文本内容
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Plan(db.Model):
    __tablename__ = 'plan'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # 计划名称
    description = db.Column(db.Text)  # 计划描述
    plan_type = db.Column(db.String(20), nullable=False)  # 'badcase' 或 'bug'
    status = db.Column(db.String(20), default='active')  # active, archived, completed
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    is_pinned = db.Column(db.Boolean, default=False)  # 是否置顶
    start_date = db.Column(db.Date)  # 开始日期
    end_date = db.Column(db.Date)  # 结束日期
    progress = db.Column(db.Float, default=0.0)  # 进度百分比 0-100
    parent_id = db.Column(db.Integer, db.ForeignKey('plan.id'))  # 父计划ID，支持递归
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 负责人
    cycle = db.Column(db.String(20))  # 计划周期：one_week, two_weeks, one_month, custom
    plan_count = db.Column(db.Integer, default=1)  # 计划个数
    scope_notification = db.Column(db.Boolean, default=False)  # 范围变更通知
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    parent = db.relationship('Plan', remote_side=[id], backref='children')
    project = db.relationship('Project', backref='plans')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_plans')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_plans')

class Bug(db.Model):
    __tablename__ = 'bug'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # Bug标题
    description = db.Column(db.Text)  # Bug描述，改为可选
    steps_to_reproduce = db.Column(db.Text)  # 复现步骤
    expected_result = db.Column(db.Text)  # 期望结果
    actual_result = db.Column(db.Text)  # 实际结果
    severity = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    priority = db.Column(db.String(10), default='p3')  # p1, p2, p3
    status = db.Column(db.String(20), default='new')  # new, assigned, in_progress, resolved, closed, reopened
    bug_type = db.Column(db.String(50))  # 功能缺陷, 性能问题, 界面问题, 兼容性问题, 安全问题, 其他
    environment = db.Column(db.String(100))  # 测试环境
    browser = db.Column(db.String(50))  # 浏览器
    os = db.Column(db.String(50))  # 操作系统
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 负责人
    attachments = db.Column(db.Text)  # 附件信息，JSON格式存储
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    plan = db.relationship('Plan', backref='bugs')
    project = db.relationship('Project', backref='bugs')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_bugs')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_bugs')

class TestCase(db.Model):
    __tablename__ = 'test_case'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # 用例标题
    status = db.Column(db.String(20), default='draft')  # draft(草稿), review(规绩), active(生效), archived(归档)
    case_type = db.Column(db.String(50))  # 用例类型：功能测试/接口测试/性能测试/安全测试
    priority = db.Column(db.String(10), default='P3')  # P0/P1/P2/P3
    test_type = db.Column(db.String(50))  # 测试类型：手动/自动/探索
    
    # 基本信息
    preconditions = db.Column(db.Text)  # 前置条件
    steps = db.Column(db.JSON)  # 用例步骤，JSON格式: [{"step": "步骤描述", "expected": "预期结果"}]
    remark = db.Column(db.Text)  # 备注
    
    # 产品需求
    requirement_id = db.Column(db.Integer)  # 关联需求ID
    
    # 工作项
    related_defects = db.Column(db.JSON)  # 关联缺陷，JSON格式: [bug_id1, bug_id2]
    
    # 缺陷（执行信息）
    last_executed = db.Column(db.DateTime)  # 最后执行时间
    executed_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # 执行人
    execution_result = db.Column(db.String(20))  # 执行结果：pass/fail/blocked/skip
    
    # 执行（测试集）
    baseline = db.Column(db.String(100))  # 基线管理
    
    # 工时
    estimated_time = db.Column(db.Float)  # 预估工时（小时）
    actual_time = db.Column(db.Float)  # 实际工时（小时）
    remaining_time = db.Column(db.Float)  # 剩余工时（小时）
    
    # 关联信息
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))  # 所属计划
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 维护人
    
    # 版本信息
    version = db.Column(db.String(20), default='v1')  # 版本号
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    plan = db.relationship('Plan', backref='testcases')
    project = db.relationship('Project', backref='testcases')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_testcases')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_testcases')
    executor = db.relationship('User', foreign_keys=[executed_by], backref='executed_testcases')

class ChatSession(db.Model):
    __tablename__ = 'chat_session'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    memory_enabled = db.Column(db.Boolean, default=True)
    memory_data = db.Column(db.Text)  # JSON格式存储
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    project = db.relationship('Project', backref='chat_sessions')
    user = db.relationship('User', backref='chat_sessions')

class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_user = db.Column(db.Boolean, default=True)
    content = db.Column(db.Text)
    understanding = db.Column(db.Text)
    steps = db.Column(db.Text)  # JSON格式存储
    execution_results = db.Column(db.Text)  # JSON格式存储executionResults
    agent_result = db.Column(db.Text)  # JSON格式存储agentResult
    evidences = db.Column(db.Text)  # JSON格式存储evidences
    navigation = db.Column(db.Text)  # JSON格式存储navigation（点击跳转Bug）
    final_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    session = db.relationship('ChatSession', backref='messages')
    user = db.relationship('User', backref='chat_messages')

class BugComment(db.Model):
    __tablename__ = 'bug_comment'
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey('bug.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)  # 富文本内容
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关系
    bug = db.relationship('Bug', backref='comments')
    user = db.relationship('User', backref='bug_comments')

class PromptTemplate(db.Model):
    __tablename__ = 'prompt_template'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# 邮件发送函数
def send_email(to, subject, body):
    try:
        msg = Message(subject, recipients=[to], body=body)
        mail.send(msg)
        print(f"邮件发送成功: {to}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        print(f"邮件配置: MAIL_SERVER={app.config.get('MAIL_SERVER')}, MAIL_USERNAME={app.config.get('MAIL_USERNAME')}")
        return False

# 生成验证码
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

# 检查用户是否有项目权限
def has_project_permission(user_id, project_id, required_role='collaborator'):
    # 首先检查项目是否存在
    project = Project.query.get(project_id)
    if not project:
        return False
    
    # 如果用户是项目创建者，直接允许访问
    if project.user_id == user_id:
        return True
    
    # 检查权限记录
    permission = ProjectPermission.query.filter_by(
        user_id=user_id, 
        project_id=project_id
    ).first()
    
    if not permission:
        return False
    
    if required_role == 'admin':
        return permission.role == 'admin'
    else:
        return permission.role in ['admin', 'collaborator']

# 路由
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        name = request.form['name']
        verification_code = request.form['verification_code']
        
        # 检查邮箱是否已注册
        if User.query.filter_by(email=email).first():
            flash('邮箱已被注册')
            return redirect(url_for('register'))
        
        # 验证验证码
        user = User.query.filter_by(email=email, verification_code=verification_code).first()
        if not user or user.verification_expires < datetime.utcnow():
            flash('验证码无效或已过期')
            return redirect(url_for('register'))
        
        # 更新用户信息
        user.password_hash = generate_password_hash(password)
        user.name = name
        user.is_verified = True
        user.verification_code = None
        user.verification_expires = None
        db.session.commit()
        
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/send_verification_code', methods=['POST'])
def send_verification_code():
    email = request.form['email']
    
    # 检查邮箱是否已注册
    if User.query.filter_by(email=email).first():
        return jsonify({'error': '邮箱已被注册'})
    
    # 生成验证码
    code = generate_verification_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    # 创建或更新用户记录
    user = User.query.filter_by(email=email).first()
    if not user:
        # 创建临时用户，使用临时密码和名称
        temp_password = generate_password_hash('temp_password_' + code)
        user = User(
            email=email, 
            password_hash=temp_password,
            name='待完善',  # 临时名称，注册时会更新
            verification_code=code, 
            verification_expires=expires
        )
        db.session.add(user)
    else:
        user.verification_code = code
        user.verification_expires = expires
    
    db.session.commit()
    
    # 发送邮件
    subject = 'BadCase Doctor 注册验证码'
    body = f'您的验证码是: {code}，有效期10分钟。'
    
    if send_email(email, subject, body):
        return jsonify({'success': True})
    else:
        return jsonify({'error': '邮件发送失败'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_verified:
                flash('请先验证邮箱')
                return redirect(url_for('login'))
            
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('邮箱或密码错误')
    
    return render_template('login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('邮箱不存在')
            return redirect(url_for('forgot_password'))
        
        # 生成验证码
        code = generate_verification_code()
        expires = datetime.utcnow() + timedelta(minutes=10)
        
        user.verification_code = code
        user.verification_expires = expires
        db.session.commit()
        
        # 发送邮件
        subject = 'BadCase Doctor 密码重置验证码'
        body = f'您的验证码是: {code}，有效期10分钟。'
        
        if send_email(email, subject, body):
            flash('验证码已发送到您的邮箱')
        else:
            flash('邮件发送失败')
        
        return redirect(url_for('reset_password'))
    
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        verification_code = request.form['verification_code']
        new_password = request.form['new_password']
        
        user = User.query.filter_by(email=email, verification_code=verification_code).first()
        if not user or user.verification_expires < datetime.utcnow():
            flash('验证码无效或已过期')
            return redirect(url_for('reset_password'))
        
        # 检查新密码是否与旧密码相同
        if check_password_hash(user.password_hash, new_password):
            flash('新密码不能与旧密码相同')
            return redirect(url_for('reset_password'))
        
        # 更新密码
        user.password_hash = generate_password_hash(new_password)
        user.verification_code = None
        user.verification_expires = None
        db.session.commit()
        
        flash('密码重置成功，请登录')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # 获取用户有权限的项目
    permissions = ProjectPermission.query.filter_by(user_id=current_user.id).all()
    project_ids = [p.project_id for p in permissions]
    projects = Project.query.filter(Project.id.in_(project_ids)).all()
    # 构造可序列化的projects_json
    projects_json = []
    for p in projects:
        projects_json.append({
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'created_at': p.created_at.strftime('%Y-%m-%d'),
            'badcases': [{'id': b.id} for b in p.badcases]
        })
    return render_template('dashboard.html', projects=projects, projects_json=projects_json)

@app.route('/project/new', methods=['GET', 'POST'])
@login_required
def new_project():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        
        project = Project(name=name, description=description, user_id=current_user.id)
        db.session.add(project)
        db.session.commit()
        
        # 创建者自动成为项目管理员
        permission = ProjectPermission(
            project_id=project.id,
            user_id=current_user.id,
            role='admin'
        )
        db.session.add(permission)
        db.session.commit()
        
        flash('项目创建成功')
        return redirect(url_for('dashboard'))
    
    return render_template('new_project.html')

@app.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    
    # 检查权限
    if not has_project_permission(current_user.id, project_id):
        flash('无权访问此项目')
        return redirect(url_for('dashboard'))
    
    badcases = BadCase.query.filter_by(project_id=project_id).all()
    permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
    
    return render_template('project_detail.html', project=project, badcases=badcases, permissions=permissions)

@app.route('/project/<int:project_id>/manage')
@login_required
def project_manage(project_id):
    project = Project.query.get_or_404(project_id)
    
    # 检查管理员权限
    if not has_project_permission(current_user.id, project_id, 'admin'):
        flash('需要管理员权限')
        return redirect(url_for('project_detail', project_id=project_id))
    
    permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
    all_users = User.query.all()
    
    return render_template('project_manage.html', project=project, permissions=permissions, all_users=all_users)

@app.route('/project/<int:project_id>/invite', methods=['POST'])
@login_required
def invite_user(project_id):
    project = Project.query.get_or_404(project_id)
    
    # 检查管理员权限
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'error': '需要管理员权限'}), 403
    
    email = request.form['email']
    role = request.form['role']
    
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    # 检查是否已经有权限
    existing_permission = ProjectPermission.query.filter_by(
        project_id=project_id, user_id=user.id
    ).first()
    
    if existing_permission:
        return jsonify({'error': '用户已有项目权限'}), 400
    
    permission = ProjectPermission(
        project_id=project_id,
        user_id=user.id,
        role=role
    )
    db.session.add(permission)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/project/<int:project_id>/remove_user/<int:user_id>', methods=['POST'])
@login_required
def remove_user(project_id, user_id):
    project = Project.query.get_or_404(project_id)
    
    # 检查管理员权限
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'error': '需要管理员权限'}), 403
    
    permission = ProjectPermission.query.filter_by(
        project_id=project_id, user_id=user_id
    ).first()
    
    if permission:
        db.session.delete(permission)
        db.session.commit()
    
    return jsonify({'success': True})

@app.route('/badcase/new/<int:project_id>', methods=['GET', 'POST'])
@login_required
def new_badcase(project_id):
    project = Project.query.get_or_404(project_id)
    
    # 检查权限
    if not has_project_permission(current_user.id, project_id):
        flash('无权访问此项目')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        badcase = BadCase(
            project_id=project_id,
            creator_id=current_user.id,
            case_category=request.form['case_category'],
            base_problem=request.form['base_problem'],
            badcase_result=request.form['badcase_result'],
            correct_answer=request.form['correct_answer'],
            problem_reason=request.form['problem_reason'],
            needs_processing=request.form.get('needs_processing') == 'on',
            priority=request.form['priority']
        )
        db.session.add(badcase)
        db.session.commit()
        
        flash('BadCase创建成功')
        return redirect(url_for('project_detail', project_id=project_id))
    
    return render_template('new_badcase.html', project=project)

@app.route('/badcase/<int:badcase_id>')
@login_required
def badcase_detail(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    project = Project.query.get(badcase.project_id)
    
    # 检查权限
    if not has_project_permission(current_user.id, badcase.project_id):
        flash('无权访问此BadCase')
        return redirect(url_for('dashboard'))
    
    # 获取项目成员
    project_members = []
    permissions = ProjectPermission.query.filter_by(project_id=badcase.project_id).all()
    for permission in permissions:
        user = User.query.get(permission.user_id)
        if user:
            project_members.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': permission.role
            })
    
    comments = Comment.query.filter_by(badcase_id=badcase_id).order_by(Comment.created_at.desc()).all()
    
    return render_template('badcase_detail.html', badcase=badcase, project=project, comments=comments, project_members=project_members)

@app.route('/badcase/<int:badcase_id>/update_status', methods=['POST'])
@login_required
def update_badcase_status(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    # 检查权限
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'error': '无权操作'}), 403
    
    new_status = request.form['status']
    assigned_users = request.form.get('assigned_users', '')

    # 支持多指派人员，前端传递为逗号分隔或JSON字符串
    import json
    try:
        # 优先尝试解析为JSON数组
        assigned_list = json.loads(assigned_users) if assigned_users else []
        if not isinstance(assigned_list, list):
            raise ValueError
    except Exception:
        # 如果不是JSON，尝试逗号分隔
        assigned_list = [int(uid) for uid in assigned_users.split(',') if uid.strip().isdigit()]
    badcase.assigned_users = json.dumps(assigned_list)

    # 状态流转校验（支持所有需求状态）
    valid_status = ['new', 'pending', 'resolved', 'hold', 'reopen', 'close', 'not_badcase']
    if new_status not in valid_status:
        return jsonify({'error': '无效的状态'}), 400
    badcase.status = new_status
    db.session.commit()
    
    return jsonify({'success': True, 'status': new_status, 'assigned_users': assigned_list})

@app.route('/badcase/<int:badcase_id>/comment', methods=['POST'])
@login_required
def add_comment(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    # 检查权限
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'error': '无权操作'}), 403
    
    content = request.form['content']
    
    comment = Comment(
        badcase_id=badcase_id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/badcase/<int:badcase_id>/close', methods=['POST'])
@login_required
def close_badcase(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    # 检查权限
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'error': '无权操作'}), 403
    
    # 检查是否有评论
    comments = Comment.query.filter_by(badcase_id=badcase_id).all()
    if not comments:
        return jsonify({'error': '关闭BadCase必须有一条评论'}), 400
    
    badcase.status = 'close'
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/import/excel', methods=['GET', 'POST'])
@login_required
def import_excel():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('没有选择文件')
            return redirect(request.url)
        
        file = request.files['file']
        project_id = request.form['project_id']
        
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            flash('无权访问此项目')
            return redirect(url_for('dashboard'))
        
        if file.filename == '':
            flash('没有选择文件')
            return redirect(request.url)
        
        if file and file.filename.endswith('.xlsx'):
            try:
                df = pd.read_excel(file)
                project = Project.query.get(project_id)
                
                for _, row in df.iterrows():
                    badcase = BadCase(
                        project_id=project_id,
                        creator_id=current_user.id,
                        case_category=row.get('case_category', ''),
                        base_problem=row.get('base_problem', ''),
                        badcase_result=row.get('badcase_result', ''),
                        correct_answer=row.get('correct_answer', ''),
                        problem_reason=row.get('problem_reason', ''),
                        needs_processing=row.get('needs_processing', True),
                        priority=row.get('priority', 'p3')
                    )
                    db.session.add(badcase)
                
                db.session.commit()
                flash('Excel导入成功')
                return redirect(url_for('project_detail', project_id=project_id))
                
            except Exception as e:
                flash(f'导入失败: {str(e)}')
        
    # 获取用户有权限的项目
    if current_user.role == 'admin':
        projects = Project.query.all()
    else:
        permissions = ProjectPermission.query.filter_by(user_id=current_user.id).all()
        project_ids = [p.project_id for p in permissions]
        projects = Project.query.filter(Project.id.in_(project_ids)).all()
    
    return render_template('import_excel.html', projects=projects)

@app.route('/import/database', methods=['GET', 'POST'])
@login_required
def import_database():
    if request.method == 'POST':
        host = request.form['host']
        port = request.form['port']
        database = request.form['database']
        username = request.form['username']
        password = request.form['password']
        table_name = request.form['table_name']
        project_id = request.form['project_id']
        
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            flash('无权访问此项目')
            return redirect(url_for('dashboard'))
        
        try:
            connection = pymysql.connect(
                host=host,
                port=int(port),
                user=username,
                password=password,
                database=database
            )
            
            query = f"SELECT * FROM {table_name}"
            df = pd.read_sql(query, connection)
            connection.close()
            
            for _, row in df.iterrows():
                badcase = BadCase(
                    project_id=project_id,
                    creator_id=current_user.id,
                    case_category=row.get('case_category', ''),
                    base_problem=row.get('base_problem', ''),
                    badcase_result=row.get('badcase_result', ''),
                    correct_answer=row.get('correct_answer', ''),
                    problem_reason=row.get('problem_reason', ''),
                    needs_processing=row.get('needs_processing', True),
                    priority=row.get('priority', 'p3')
                )
                db.session.add(badcase)
            
            db.session.commit()
            flash('数据库导入成功')
            return redirect(url_for('project_detail', project_id=project_id))
            
        except Exception as e:
            flash(f'数据库连接失败: {str(e)}')
    
    # 获取用户有权限的项目
    if current_user.role == 'admin':
        projects = Project.query.all()
    else:
        permissions = ProjectPermission.query.filter_by(user_id=current_user.id).all()
        project_ids = [p.project_id for p in permissions]
        projects = Project.query.filter(Project.id.in_(project_ids)).all()
    
    return render_template('import_database.html', projects=projects)

#@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    message = data.get('message', '')
    context = data.get('context', [])
    tools = data.get('tools', [])

    # 这里预留大模型和工具调度逻辑，当前返回模拟数据
    # 后续可集成Qwen3-Code模型和MCP工具
    reply = f"[模拟回复] 收到：{message}"
    tool_calls = [
        {"tool": "search_doc", "result": "[模拟] 文档召回内容"},
        {"tool": "get_prompt", "result": "[模拟] 提示词内容"}
    ] if tools else []
    flow_info = {"step": "tool_dispatch", "desc": "已调用相关工具"} if tools else {"step": "reply", "desc": "直接回复"}
    docs = ["[模拟] 相关文档1", "[模拟] 相关文档2"] if tools else []

    return jsonify({
        "reply": reply,
        "tool_calls": tool_calls,
        "flow_info": flow_info,
        "docs": docs
    })

# ==================== Browser-use Agent API ==================== #

@app.route('/api/agent/browser-use/test', methods=['POST'])
@login_required
def api_browser_use_test():
    """测试用例自动执行"""
    try:
        from agents import BrowserUseAgent
        from llm.factory import get_llm
        
        data = request.get_json()
        test_case = data.get('test_case', {})
        
        agent = BrowserUseAgent()
        llm = get_llm("qwen")
        
        result = agent.handle(
            userId=str(current_user.id),
            action="test_execution",
            llm=llm,
            test_case=test_case
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"测试执行失败: {e}")
        return jsonify({"error": f"测试执行失败: {str(e)}"}), 500

@app.route('/api/agent/browser-use/badcase', methods=['POST'])
@login_required
def api_browser_use_badcase():
    """BadCase 复现定位"""
    try:
        from agents import BrowserUseAgent
        from llm.factory import get_llm
        
        data = request.get_json()
        badcase = data.get('badcase', {})
        
        agent = BrowserUseAgent()
        llm = get_llm("qwen")
        
        result = agent.handle(
            userId=str(current_user.id),
            action="badcase_reproduction",
            llm=llm,
            badcase=badcase
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"BadCase 复现失败: {e}")
        return jsonify({"error": f"BadCase 复现失败: {str(e)}"}), 500

@app.route('/api/agent/browser-use/conversation', methods=['POST'])
@login_required
def api_browser_use_conversation():
    """对话准确率测试"""
    try:
        from agents import BrowserUseAgent
        from llm.factory import get_llm
        
        data = request.get_json()
        conversation_test = data.get('conversation_test', {})
        
        agent = BrowserUseAgent()
        llm = get_llm("qwen")
        
        result = agent.handle(
            userId=str(current_user.id),
            action="conversation_test",
            llm=llm,
            conversation_test=conversation_test
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"对话测试失败: {e}")
        return jsonify({"error": f"对话测试失败: {str(e)}"}), 500

# ==================== Bug 管理 Agent API ==================== #
# 注意：这是基于 Redis 的 Bug 管理 Agent，用于对话式操作
# 不同于下方基于数据库的 Bug CRUD API

@app.route('/api/agent/bugs/list', methods=['POST'])
@login_required
def api_agent_list_bugs():
    """查询 Bug 列表（Agent）"""
    try:
        from agents import BugManagementAgent
        
        data = request.get_json()
        project_id = data.get('project_id')
        status = data.get('status')
        priority = data.get('priority')
        assignee = data.get('assignee')
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="list",
            project_id=project_id,
            status=status,
            priority=priority,
            assignee=assignee
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"查询 Bug 列表失败: {e}")
        return jsonify({"error": f"查询 Bug 列表失败: {str(e)}"}), 500

@app.route('/api/agent/bugs/create', methods=['POST'])
@login_required
def api_agent_create_bug():
    """创建新 Bug（Agent）"""
    try:
        from agents import BugManagementAgent
        
        data = request.get_json()
        project_id = data.get('project_id')
        title = data.get('title')
        description = data.get('description', '')
        priority = data.get('priority', 'medium')
        assignee = data.get('assignee')
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="create",
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            assignee=assignee
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"创建 Bug 失败: {e}")
        return jsonify({"error": f"创建 Bug 失败: {str(e)}"}), 500

@app.route('/api/agent/bugs/update', methods=['POST'])
@login_required
def api_agent_update_bug():
    """更新 Bug 信息（Agent）"""
    try:
        from agents import BugManagementAgent
        
        data = request.get_json()
        bug_id = data.get('bug_id')
        updates = data.get('updates', {})
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="update",
            bug_id=bug_id,
            updates=updates
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"更新 Bug 失败: {e}")
        return jsonify({"error": f"更新 Bug 失败: {str(e)}"}), 500

@app.route('/api/agent/bugs/delete', methods=['POST'])
@login_required
def api_agent_delete_bug():
    """删除 Bug（Agent）"""
    try:
        from agents import BugManagementAgent
        
        data = request.get_json()
        bug_id = data.get('bug_id')
        project_id = data.get('project_id')
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="delete",
            bug_id=bug_id,
            project_id=project_id
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"删除 Bug 失败: {e}")
        return jsonify({"error": f"删除 Bug 失败: {str(e)}"}), 500

@app.route('/api/agent/bugs/assign', methods=['POST'])
@login_required
def api_agent_assign_bug():
    """分配 Bug（Agent）"""
    try:
        from agents import BugManagementAgent
        
        data = request.get_json()
        bug_id = data.get('bug_id')
        assignee = data.get('assignee')
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="assign",
            bug_id=bug_id,
            assignee=assignee
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"分配 Bug 失败: {e}")
        return jsonify({"error": f"分配 Bug 失败: {str(e)}"}), 500

@app.route('/api/agent/bugs/change-status', methods=['POST'])
@login_required
def api_agent_change_bug_status():
    """修改 Bug 状态（Agent）- 使用 ModifyTool"""
    import asyncio
    from agents.tools.modify_tool import ModifyTool
    
    try:
        data = request.get_json()
        bug_id = data.get('bug_id')
        status = data.get('status')
        project_id = data.get('project_id')
        
        if not bug_id or not status:
            return jsonify({"error": "Bug ID 和状态不能为空"}), 400
        
        # 使用 ModifyTool 修改状态
        modify_tool = ModifyTool(db.session)
        
        async def run_modify():
            result = await modify_tool.execute(
                target='bug',
                target_id=bug_id,
                modifications={'status': status},
                project_id=project_id,
                confirm=True  # 直接确认修改
            )
            return result
        
        result = asyncio.run(run_modify())
        
        if result.get('success'):
            return jsonify({
                "code": 200,
                "message": f"Bug 状态已更新为: {status}",
                "data": result.get('after')
            })
        else:
            return jsonify({
                "code": 500,
                "error": result.get('error', '修改失败')
            }), 500
            
    except Exception as e:
        print(f"修改 Bug 状态失败: {e}")
        return jsonify({"error": f"修改 Bug 状态失败: {str(e)}"}), 500

@app.route('/api/agent/bugs/search', methods=['POST'])
@login_required
def api_agent_search_bugs():
    """搜索 Bug（Agent）"""
    try:
        from agents import BugManagementAgent
        
        data = request.get_json()
        project_id = data.get('project_id')
        keyword = data.get('keyword')
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="search",
            project_id=project_id,
            keyword=keyword
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"搜索 Bug 失败: {e}")
        return jsonify({"error": f"搜索 Bug 失败: {str(e)}"}), 500

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    if file and allowed_file(file.filename):
        # 检查文件大小
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置到文件开头
        
        if file_size > MINIO_CONFIG['max_file_size']:
            return jsonify({'error': f'文件大小超过限制 ({MINIO_CONFIG["max_file_size"] // 1024 // 1024}MB)'}), 400
        
        # 上传到MinIO
        result = upload_file_to_minio(file)
        
        if result['success']:
            return jsonify({
                'success': True,
                'url': result['url'],
                'filename': result['filename'],
                'path': result['path']
            })
        else:
            return jsonify({'error': result['error']}), 500
    else:
        return jsonify({'error': '文件类型不被允许'}), 400

# 项目头像上传
@app.route('/api/upload/avatar', methods=['POST'])
@login_required
def api_upload_avatar():
    print("=== 开始头像上传 ===")
    
    if 'file' not in request.files:
        print("错误: 未选择文件")
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        print("错误: 文件名为空")
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    print(f"接收到的文件: {file.filename}, 大小: {file.content_length if hasattr(file, 'content_length') else '未知'}")
    
    # 只允许图片文件
    allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
    if not (file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_image_extensions):
        print(f"错误: 不支持的文件类型 {file.filename}")
        return jsonify({'success': False, 'error': '只支持图片文件'}), 400
    
    # 检查文件大小 - 头像文件限制为5MB
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    print(f"文件大小: {file_size} 字节")
    
    # 头像文件大小限制为1MB
    max_avatar_size = 1 * 1024 * 1024  # 1MB
    if file_size > max_avatar_size:
        print(f"错误: 头像文件大小超过限制")
        return jsonify({'success': False, 'error': f'头像文件大小不能超过1MB，当前大小: {file_size // 1024 // 1024}MB'}), 400
    
    # 压缩头像图片
    print("开始压缩头像图片...")
    compressed_file = compress_image(file, max_size=(800, 800), quality=85)
    original_size = file_size
    compressed_file.seek(0, 2)
    compressed_size = compressed_file.tell()
    compressed_file.seek(0)
    
    print(f"图片压缩完成: {original_size} -> {compressed_size} 字节 (压缩率: {((original_size - compressed_size) / original_size * 100):.1f}%)")
    
    # 上传到MinIO的avatar文件夹
    print("开始上传到MinIO...")
    start_time = datetime.now()
    result = upload_file_to_minio(compressed_file, 'avatar')
    end_time = datetime.now()
    upload_duration = (end_time - start_time).total_seconds()
    
    print(f"上传耗时: {upload_duration:.2f}秒")
    print(f"上传结果: {result}")
    
    if result['success']:
        print(f"头像上传成功，URL: {result['url']}")
        return jsonify({
            'success': True,
            'url': result['url'],
            'filename': result['filename'],
            'path': result['path'],
            'upload_time': upload_duration
        })
    else:
        print(f"头像上传失败: {result['error']}")
        return jsonify({'success': False, 'error': result['error']}), 500

# 获取头像URL的API端点（带防盗刷）
@app.route('/api/avatar/<path:file_path>', methods=['GET'])
@login_required  # 需要登录才能获取头像URL
def api_get_avatar(file_path):
    """动态获取头像URL，支持预签名URL，带防盗刷功能"""
    try:
        # 检查访问频率限制
        if not check_avatar_access_rate(current_user.id):
            print(f"用户 {current_user.id} 头像访问频率过高，疑似盗刷")
            return jsonify({
                'success': False,
                'error': '访问频率过高，请稍后再试'
            }), 429  # Too Many Requests
        
        # 检查用户权限 - 只有项目成员才能访问项目头像
        import urllib.parse
        decoded_path = urllib.parse.unquote(file_path)
        
        # 从文件名中提取项目ID进行权限检查
        filename_parts = decoded_path.split('_')
        if len(filename_parts) >= 3 and filename_parts[0] == 'project':
            try:
                project_id = int(filename_parts[1])
                # 检查用户是否有权限访问该项目
                if not has_project_permission(current_user.id, project_id):
                    print(f"用户 {current_user.id} 尝试访问无权限的项目 {project_id} 的头像")
                    return jsonify({
                        'success': False,
                        'error': '无权限访问该头像'
                    }), 403
            except (ValueError, IndexError):
                # 如果无法解析项目ID，记录警告但允许访问
                print(f"警告: 无法从文件名 {decoded_path} 解析项目ID")
        else:
            # 如果文件名格式不符合预期，记录警告
            print(f"警告: 头像文件名格式异常: {decoded_path}")
        
        # 构建完整的MinIO路径
        full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{decoded_path}"
        
        # 检查文件是否存在
        client = get_minio_client()
        try:
            client.head_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return jsonify({
                    'success': False,
                    'error': '头像文件不存在'
                }), 404
            else:
                raise e
        
        # 生成新的预签名URL，设置较长的有效期以支持浏览器缓存
        presigned_url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': MINIO_CONFIG['bucket_name'], 'Key': full_path},
            ExpiresIn=86400  # 24小时有效期，支持浏览器缓存
        )
        
        # 记录访问日志
        print(f"用户 {current_user.id} ({current_user.email}) 访问头像: {decoded_path}")
        
        return jsonify({
            'success': True,
            'url': presigned_url
        })
        
    except Exception as e:
        print(f"获取头像URL失败: {e}")
        return jsonify({
            'success': False,
            'error': f'获取头像URL失败: {str(e)}'
        }), 500

# 获取头像图片数据的API端点（带Redis缓存）
@app.route('/api/avatar/image/<path:file_path>', methods=['GET'])
@login_required  # 需要登录才能获取头像
def api_get_avatar_image(file_path):
    """获取头像图片数据，支持Redis缓存，10分钟有效期"""
    try:
        # 速率限制检查
        if not check_avatar_access_rate(current_user.id):
            return jsonify({'error': '访问过于频繁，请稍后再试'}), 429
        
        # URL解码文件名
        decoded_path = unquote(file_path)
        print(f"用户 {current_user.id} ({current_user.email}) 请求头像图片: {decoded_path}")
        
        # 生成缓存键
        cache_key = get_image_cache_key(decoded_path)
        
        # 尝试从Redis缓存获取图片数据
        cached_image_data = get_image_from_cache(cache_key)
        if cached_image_data:
            print(f"从Redis缓存返回头像: {decoded_path}")
            response = app.response_class(
                cached_image_data,
                status=200,
                mimetype='image/jpeg'  # Default MIME type
            )
            response.headers['Cache-Control'] = 'public, max-age=600'  # Browser cache 10 minutes
            return response
        
        # Cache miss, fetch from MinIO
        print(f"从MinIO获取头像: {decoded_path}")
        full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{decoded_path}"
        
        client = get_minio_client()
        response = client.get_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
        image_data = response.read()
        response.close()
        
        # Cache image data to Redis, 10 minutes expiry
        set_image_to_cache(cache_key, image_data, 600)
        
        # Determine MIME type and return response
        mime_type = 'image/jpeg'  # Default
        if decoded_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif decoded_path.lower().endswith('.gif'):
            mime_type = 'image/gif'
        elif decoded_path.lower().endswith('.webp'):
            mime_type = 'image/webp'
        
        response = app.response_class(
            image_data,
            status=200,
            mimetype=mime_type
        )
        response.headers['Cache-Control'] = 'public, max-age=600'  # Browser cache 10 minutes
        response.headers['Content-Type'] = mime_type
        
        print(f"用户 {current_user.id} ({current_user.email}) 访问头像图片: {decoded_path}")
        
        return response
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"头像文件不存在: {decoded_path}")
            return jsonify({'error': '头像文件不存在'}), 404
        else:
            print(f"获取头像失败: {e}")
            return jsonify({'error': '获取头像失败'}), 500
    except Exception as e:
        print(f"获取头像时发生错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/api/avatar/base64/<path:file_path>', methods=['GET'])
def api_get_avatar_base64(file_path):
    """获取头像图片的base64数据，支持Redis缓存，10分钟有效期"""
    try:
        # 移除速率限制检查，允许匿名访问
        
        # URL解码文件名
        decoded_path = unquote(file_path)
        
        # 生成缓存键
        cache_key = get_image_cache_key(decoded_path)
        
        # 尝试从Redis缓存获取图片数据
        redis_client = get_redis_client()
        cached_image_data = get_image_from_cache(cache_key)
        if cached_image_data:
            # 转换为base64
            base64_data = base64.b64encode(cached_image_data).decode('utf-8')
            
            # 确定MIME类型
            mime_type = 'image/jpeg'  # Default
            if decoded_path.lower().endswith('.png'):
                mime_type = 'image/png'
            elif decoded_path.lower().endswith('.gif'):
                mime_type = 'image/gif'
            elif decoded_path.lower().endswith('.webp'):
                mime_type = 'image/webp'
            
            return jsonify({
                'data': f'data:{mime_type};base64,{base64_data}',
                'cached': True
            })
        
        # Cache miss, fetch from MinIO
        full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{decoded_path}"
        
        client = get_minio_client()
        response = client.get_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
        
        # 检查响应类型并获取正确的文件对象
        if isinstance(response, dict):
            if 'Body' in response:
                file_obj = response['Body']
            else:
                raise Exception(f"MinIO响应缺少Body字段")
        elif hasattr(response, 'read'):
            file_obj = response
        else:
            raise Exception(f"MinIO响应类型不支持: {type(response)}")
        
        image_data = file_obj.read()
        file_obj.close()
        
        # Cache image data to Redis, 10 minutes expiry
        set_image_to_cache(cache_key, image_data, 600)
        
        # 转换为base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # 确定MIME类型
        mime_type = 'image/jpeg'  # Default
        if decoded_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif decoded_path.lower().endswith('.gif'):
            mime_type = 'image/gif'
        elif decoded_path.lower().endswith('.webp'):
            mime_type = 'image/webp'
        
        return jsonify({
            'data': f'data:{mime_type};base64,{base64_data}',
            'cached': False
        })
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({'error': '头像文件不存在'}), 404
        else:
            print(f"MinIO错误: {e}")
            return jsonify({'error': '获取头像失败'}), 500
    except Exception as e:
        print(f"获取头像时发生未知错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

# 测试MinIO连接
@app.route('/api/test/minio', methods=['GET'])
@login_required
def api_test_minio():
    try:
        client = get_minio_client()
        
        # 测试列出存储桶中的对象
        response = client.list_objects_v2(
            Bucket=MINIO_CONFIG['bucket_name'],
            MaxKeys=5
        )
        
        objects = []
        if 'Contents' in response:
            for obj in response['Contents']:
                objects.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat()
                })
        
        return jsonify({
            'success': True,
            'bucket': MINIO_CONFIG['bucket_name'],
            'endpoint': MINIO_CONFIG['endpoint'],
            'objects': objects,
            'message': 'MinIO连接正常'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'MinIO连接失败: {str(e)}'
        }), 500

# 获取项目成员及角色
@app.route('/api/project/<int:project_id>/members', methods=['GET'])
@login_required
def api_project_members(project_id):
    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问'}), 403
    permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
    members = []
    for p in permissions:
        user = User.query.get(p.user_id)
        if user:
            members.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': p.role
            })
    return jsonify({'success': True, 'data': members})

# 邀请成员
@app.route('/api/project/<int:project_id>/invite', methods=['POST'])
@login_required
def api_invite_user(project_id):
    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    data = request.get_json()
    email = data.get('email')
    role = data.get('role', 'collaborator')
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    existing_permission = ProjectPermission.query.filter_by(project_id=project_id, user_id=user.id).first()
    if existing_permission:
        return jsonify({'success': False, 'error': '用户已有项目权限'}), 400
    permission = ProjectPermission(project_id=project_id, user_id=user.id, role=role)
    db.session.add(permission)
    db.session.commit()
    return jsonify({'success': True})

# 移除成员
@app.route('/api/project/<int:project_id>/remove_user', methods=['POST'])
@login_required
def api_remove_user(project_id):
    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    data = request.get_json()
    user_id = data.get('user_id')
    permission = ProjectPermission.query.filter_by(project_id=project_id, user_id=user_id).first()
    if permission:
        db.session.delete(permission)
        db.session.commit()
    return jsonify({'success': True})

# 修改成员角色
@app.route('/api/project/<int:project_id>/change_role', methods=['POST'])
@login_required
def api_change_role(project_id):
    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    data = request.get_json()
    user_id = data.get('user_id')
    new_role = data.get('role')
    permission = ProjectPermission.query.filter_by(project_id=project_id, user_id=user_id).first()
    if not permission:
        return jsonify({'success': False, 'error': '用户无项目权限'}), 404
    permission.role = new_role
    db.session.commit()
    return jsonify({'success': True})

# 获取所有可邀请用户（不在该项目的已注册用户）
@app.route('/api/users', methods=['GET'])
@login_required
def api_all_users():
    project_id = request.args.get('project_id', type=int)
    users = User.query.filter(User.is_verified==True).all()
    if project_id:
        permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
        member_ids = {p.user_id for p in permissions}
        users = [u for u in users if u.id not in member_ids]
    user_list = [{'id': u.id, 'name': u.name, 'email': u.email} for u in users]
    return jsonify({'success': True, 'data': user_list})

@app.route('/api/import/excel', methods=['POST'])
@login_required
def api_import_excel():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    file = request.files['file']
    project_id = request.form.get('project_id')
    if not project_id:
        return jsonify({'success': False, 'error': '缺少project_id'}), 400
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403
    if file.filename == '' or not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'error': '文件格式错误'}), 400
    try:
        df = pd.read_excel(file)
        success_count = 0
        fail_count = 0
        fail_rows = []
        for idx, row in df.iterrows():
            try:
                badcase = BadCase(
                    project_id=project_id,
                    creator_id=current_user.id,
                    case_category=row.get('case_category', ''),
                    base_problem=row.get('base_problem', ''),
                    badcase_result=row.get('badcase_result', ''),
                    correct_answer=row.get('correct_answer', ''),
                    problem_reason=row.get('problem_reason', ''),
                    needs_processing=row.get('needs_processing', True),
                    priority=row.get('priority', 'p3')
                )
                db.session.add(badcase)
                success_count += 1
            except Exception as e:
                fail_count += 1
                fail_rows.append({'row': idx+2, 'error': str(e)})
        db.session.commit()
        return jsonify({'success': True, 'imported': success_count, 'failed': fail_count, 'fail_rows': fail_rows})
    except Exception as e:
        return jsonify({'success': False, 'error': f'导入失败: {str(e)}'}), 500

@app.route('/api/import/database', methods=['POST'])
@login_required
def api_import_database():
    data = request.json if request.is_json else request.form
    host = data.get('host')
    port = data.get('port')
    database_name = data.get('database')
    username = data.get('username')
    password = data.get('password')
    table_name = data.get('table_name')
    project_id = data.get('project_id')
    if not all([host, port, database_name, username, password, table_name, project_id]):
        return jsonify({'success': False, 'error': '参数不完整'}), 400
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403
    try:
        connection = pymysql.connect(
            host=host,
            port=int(port),
            user=username,
            password=password,
            database=database_name
        )
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, connection)
        connection.close()
        success_count = 0
        fail_count = 0
        fail_rows = []
        for idx, row in df.iterrows():
            try:
                badcase = BadCase(
                    project_id=project_id,
                    creator_id=current_user.id,
                    case_category=row.get('case_category', ''),
                    base_problem=row.get('base_problem', ''),
                    badcase_result=row.get('badcase_result', ''),
                    correct_answer=row.get('correct_answer', ''),
                    problem_reason=row.get('problem_reason', ''),
                    needs_processing=row.get('needs_processing', True),
                    priority=row.get('priority', 'p3')
                )
                db.session.add(badcase)
                success_count += 1
            except Exception as e:
                fail_count += 1
                fail_rows.append({'row': idx+2, 'error': str(e)})
        db.session.commit()
        return jsonify({'success': True, 'imported': success_count, 'failed': fail_count, 'fail_rows': fail_rows})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据库导入失败: {str(e)}'}), 500

# API端点 - 用户认证
@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        start_time = time.time()
        print(f"\n[LOGIN] === 开始处理登录请求 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        print(f"[LOGIN] 收到请求: email={email}")
        
        if not email or not password:
            print("[LOGIN] 错误: 邮箱或密码为空")
            return jsonify({'success': False, 'error': '邮箱和密码不能为空'}), 400
        
        print("[LOGIN] 正在查询数据库...")
        db_start = time.time()
        user = User.query.filter_by(email=email).first()
        print(f"[LOGIN] 数据库查询耗时: {time.time() - db_start:.4f}s")
        
        if user:
            print("[LOGIN] 用户存在，正在校验密码...")
            pwd_start = time.time()
            is_valid = check_password_hash(user.password_hash, password)
            print(f"[LOGIN] 密码校验耗时: {time.time() - pwd_start:.4f}s")
            
            if is_valid:
                print(f"[LOGIN] 校验成功，正在执行 login_user(id={user.id})...")
                login_user(user)
                
                print(f"[LOGIN] === 登录处理成功，总耗时: {time.time() - start_time:.4f}s ===\n")
                return jsonify({
                    'success': True, 
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'name': user.name,
                        'role': user.role
                    }
                })
            else:
                print("[LOGIN] 错误: 密码校验失败")
        else:
            print(f"[LOGIN] 错误: 未找到该用户 ({email})")
            
        print(f"[LOGIN] === 登录处理结束 (401)，总耗时: {time.time() - start_time:.4f}s ===\n")
        return jsonify({'success': False, 'error': '邮箱或密码错误'}), 401
    except Exception as e:
        print(f"[LOGIN] !!! 发生异常: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': '服务器内部错误'}), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    verification_code = data.get('verification_code')
    
    if not all([email, password, name, verification_code]):
        return jsonify({'success': False, 'error': '所有字段都是必填的'}), 400
    
    # 检查邮箱是否已存在
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.is_verified:
        return jsonify({'success': False, 'error': '邮箱已被注册'}), 400
    
    # 验证验证码
    user = User.query.filter_by(email=email, verification_code=verification_code).first()
    if not user or user.verification_expires < datetime.utcnow():
        return jsonify({'success': False, 'error': '验证码无效或已过期'}), 400
    
    # 更新用户信息
    user.password_hash = generate_password_hash(password)
    user.name = name
    user.is_verified = True
    user.verification_code = None
    user.verification_expires = None
    
    db.session.commit()
    login_user(user)
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'role': user.role
        }
    })

@app.route('/api/user', methods=['GET'])
@login_required
def api_get_user():
    return jsonify({
        'success': True,
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'role': current_user.role
        }
    })

@app.route('/api/send_verification_code', methods=['POST'])
def api_send_verification_code():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'error': '邮箱不能为空'}), 400
    
    # 生成验证码
    verification_code = generate_verification_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    # 检查用户是否已存在
    user = User.query.filter_by(email=email).first()
    if user:
        # 更新现有用户的验证码
        user.verification_code = verification_code
        user.verification_expires = expires
    else:
        # 创建新用户
        user = User(
            email=email,
            verification_code=verification_code,
            verification_expires=expires
        )
        db.session.add(user)
    
    db.session.commit()
    
    # 发送邮件
    try:
        send_email(
            to=email,
            subject='BadCase Doctor - 邮箱验证码',
            body=f'您的验证码是: {verification_code}，有效期10分钟。'
        )
        return jsonify({'success': True, 'message': '验证码已发送'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'发送邮件失败: {str(e)}'}), 500

# API端点 - 项目管理
@app.route('/api/projects', methods=['GET'])
@login_required
def api_get_projects():
    try:
        # 使用更简单的查询方式，避免复杂的UNION操作
        # 首先获取用户创建的项目，限制返回字段
        owned_projects = db.session.query(
            Project.id,
            Project.name,
            Project.description,
            Project.avatar,
            Project.owner,
            Project.status,
            Project.created_at
        ).filter(Project.user_id == current_user.id).limit(100).all()  # 限制数量避免过多数据
        
        # 获取用户参与的项目（通过权限表），限制数量
        permission_projects = db.session.query(
            Project.id,
            Project.name,
            Project.description,
            Project.avatar,
            Project.owner,
            Project.status,
            Project.created_at,
            ProjectPermission.role
        ).join(
            ProjectPermission, Project.id == ProjectPermission.project_id
        ).filter(
            ProjectPermission.user_id == current_user.id,
            Project.user_id != current_user.id  # 排除用户自己创建的项目
        ).limit(100).all()  # 限制数量避免过多数据
        
        # 合并项目列表
        user_projects = []
        
        # 添加用户创建的项目
        for project in owned_projects:
            user_projects.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'status': project.status,
                'created_at': project.created_at.isoformat(),
                'role': 'admin'
            })
        
        # 添加用户参与的项目
        for project in permission_projects:
            user_projects.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'status': project.status,
                'created_at': project.created_at.isoformat(),
                'role': project.role
            })
        
        # 处理项目头像URL
        for project in user_projects:
            if project['avatar']:
                # 检查是否是预签名URL且可能已过期
                if 'AWSAccessKeyId' in project['avatar'] and 'Expires=' in project['avatar']:
                    try:
                        # 从URL中提取文件名
                        import urllib.parse
                        from urllib.parse import urlparse, parse_qs
                        
                        parsed_url = urlparse(project['avatar'])
                        path_parts = parsed_url.path.split('/')
                        filename = path_parts[-1] if path_parts else ''
                        
                        if filename:
                            # 生成新的预签名URL
                            full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{filename}"
                            client = get_minio_client()
                            
                            # 检查文件是否存在
                            try:
                                client.head_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
                                # 生成新的预签名URL
                                new_presigned_url = client.generate_presigned_url(
                                    'get_object',
                                    Params={'Bucket': MINIO_CONFIG['bucket_name'], 'Key': full_path},
                                    ExpiresIn=86400  # 24小时有效期，支持浏览器缓存
                                )
                                project['avatar'] = new_presigned_url
                            except ClientError as e:
                                if e.response['Error']['Code'] == '404':
                                    project['avatar'] = None
                    except Exception as e:
                        print(f"处理项目 {project['id']} 头像URL时出错: {e}")
                else:
                    # 如果不是预签名URL，检查是否是MinIO的普通URL，需要转换为预签名URL
                    if project['avatar'].startswith('http://117.72.33.38:9901/') and 'AWSAccessKeyId' not in project['avatar']:
                        try:
                            # 从URL中提取文件名
                            import urllib.parse
                            from urllib.parse import urlparse
                            
                            parsed_url = urlparse(project['avatar'])
                            path_parts = parsed_url.path.split('/')
                            filename = path_parts[-1] if path_parts else ''
                            
                            if filename:
                                # 生成预签名URL
                                full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{filename}"
                                client = get_minio_client()
                                
                                # 检查文件是否存在
                                try:
                                    client.head_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
                                    # 生成新的预签名URL
                                    new_presigned_url = client.generate_presigned_url(
                                        'get_object',
                                        Params={'Bucket': MINIO_CONFIG['bucket_name'], 'Key': full_path},
                                        ExpiresIn=86400  # 24小时有效期，支持浏览器缓存
                                    )
                                    project['avatar'] = new_presigned_url
                                except ClientError as e:
                                    if e.response['Error']['Code'] == '404':
                                        project['avatar'] = None
                        except Exception as e:
                            print(f"处理项目 {project['id']} 普通URL时出错: {e}")
        
        # 按创建时间排序
        user_projects.sort(key=lambda x: x['created_at'], reverse=True)
        
        return jsonify({'success': True, 'projects': user_projects})
        
    except Exception as e:
        print(f"获取项目列表时发生错误: {str(e)}")
        return jsonify({'success': False, 'error': '获取项目列表失败'}), 500

@app.route('/api/projects', methods=['POST'])
@login_required
def api_create_project():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
            
        name = data.get('name')
        description = data.get('description', '')
        avatar = data.get('avatar', '')
        owner = data.get('owner', '')
        intro = data.get('intro', '')
        
        if not name:
            return jsonify({'success': False, 'error': '项目名称不能为空'}), 400
        
        project = Project(
            name=name,
            description=description,
            avatar=avatar,
            owner=owner,
            intro=intro,
            user_id=current_user.id
        )
        
        db.session.add(project)
        db.session.commit()
        print(f"项目保存成功，ID: {project.id}")
        
        # 为项目创建者添加管理员权限
        permission = ProjectPermission(
            project_id=project.id,
            user_id=current_user.id,
            role='admin'
        )
        db.session.add(permission)
        db.session.commit()
        print(f"已为用户 {current_user.id} 添加项目 {project.id} 的管理员权限")
        
        result = {
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'intro': project.intro,
                'status': project.status,
                'created_at': project.created_at.isoformat()
            }
        }
        print(f"返回结果: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"创建项目时发生异常: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
def api_get_project_detail(project_id):
    print(f"=== 获取项目详情 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    
    try:
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权访问项目 {project_id}")
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 只获取项目基本信息，不包含BadCase列表
        project = Project.query.get_or_404(project_id)
        print(f"项目信息获取成功: {project.name}")
        
        # 获取BadCase统计信息（快速统计）
        badcase_stats = db.session.query(
            db.func.count(BadCase.id).label('total'),
            db.func.sum(db.case((BadCase.status == 'pending', 1), else_=0)).label('pending'),
            db.func.sum(db.case((BadCase.status == 'resolved', 1), else_=0)).label('resolved'),
            db.func.sum(db.case((BadCase.status == 'close', 1), else_=0)).label('close')
        ).filter_by(project_id=project_id).first()
        
        print(f"BadCase统计完成: 总计={badcase_stats.total}, 待处理={badcase_stats.pending}, 已解决={badcase_stats.resolved}, 已关闭={badcase_stats.close}")
        
        return jsonify({
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'intro': project.intro,
                'status': project.status,
                'login_configs': json.loads(project.login_configs) if project.login_configs else [],
                'created_at': project.created_at.isoformat(),
                'badcase_stats': {
                    'total': badcase_stats.total or 0,
                    'pending': badcase_stats.pending or 0,
                    'resolved': badcase_stats.resolved or 0,
                    'close': badcase_stats.close or 0
                }
            }
        })
    except Exception as e:
        print(f"获取项目详情失败: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取项目信息失败'}), 500

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
def api_update_project(project_id):
    print(f"=== 开始更新项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 检查权限
        print("检查项目权限...")
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权修改项目 {project_id}")
            return jsonify({'success': False, 'error': '无权修改此项目'}), 403
        print("权限检查通过")
        
        # 获取项目
        print(f"获取项目信息...")
        project = Project.query.get_or_404(project_id)
        print(f"项目信息: ID={project.id}, 名称={project.name}, 创建者={project.user_id}")
        
        # 获取请求数据
        print("解析请求数据...")
        data = request.get_json()
        print(f"请求数据: {data}")
        
        if not data:
            print("请求数据为空")
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        # 记录更新前的项目信息
        print("更新前的项目信息:")
        print(f"  - 名称: {project.name}")
        print(f"  - 描述: {project.description}")
        print(f"  - 头像: {project.avatar}")
        print(f"  - 负责人: {project.owner}")
        print(f"  - 介绍: {project.intro}")
        print(f"  - 状态: {project.status}")
        print(f"  - 登录配置: {project.login_configs}")
        
        # 更新项目信息
        print("开始更新项目字段...")
        if 'name' in data:
            old_name = project.name
            project.name = data['name']
            print(f"  更新名称: {old_name} -> {project.name}")
        if 'description' in data:
            old_desc = project.description
            project.description = data['description']
            print(f"  更新描述: {old_desc} -> {project.description}")
        if 'avatar' in data:
            old_avatar = project.avatar
            # 检查是否是base64数据，如果是则跳过（避免数据过大）
            if data['avatar'] and data['avatar'].startswith('data:'):
                print(f"  跳过base64头像数据，保持原有头像: {old_avatar}")
            else:
                project.avatar = data['avatar']
                print(f"  更新头像: {old_avatar} -> {project.avatar}")
        if 'owner' in data:
            old_owner = project.owner
            project.owner = data['owner']
            print(f"  更新负责人: {old_owner} -> {project.owner}")
        if 'intro' in data:
            old_intro = project.intro
            project.intro = data['intro']
            print(f"  更新介绍: {old_intro} -> {project.intro}")
        if 'login_configs' in data:
            old_login_configs = project.login_configs
            # login_configs 是列表，需要序列化为 JSON 字符串
            if isinstance(data['login_configs'], list):
                project.login_configs = json.dumps(data['login_configs'], ensure_ascii=False)
            else:
                project.login_configs = data['login_configs']
            print(f"  更新登录配置: {old_login_configs} -> {project.login_configs}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        # 返回更新后的项目信息
        response_data = {
            'success': True,
            'message': '项目更新成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'intro': project.intro,
                'status': project.status,
                'login_configs': json.loads(project.login_configs) if project.login_configs else []
            }
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 更新完成 ===")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"更新项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/projects/<int:project_id>/publish', methods=['POST'])
@login_required
def api_publish_project(project_id):
    print(f"=== 开始发布项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 检查权限
        print("检查项目权限...")
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权发布项目 {project_id}")
            return jsonify({'success': False, 'error': '无权发布此项目'}), 403
        print("权限检查通过")
        
        # 获取项目
        print(f"获取项目信息...")
        project = Project.query.get_or_404(project_id)
        print(f"项目信息: ID={project.id}, 名称={project.name}, 当前状态={project.status}")
        
        # 更新状态
        old_status = project.status
        project.status = 'published'
        print(f"更新项目状态: {old_status} -> {project.status}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        response_data = {
            'success': True,
            'message': '项目发布成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'status': project.status
            }
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 发布完成 ===")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"发布项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/projects/<int:project_id>/badcases', methods=['GET'])
@login_required
def api_get_project_badcases(project_id):
    """获取项目的BadCase列表（分页）"""
    print(f"=== 获取项目BadCase列表 {project_id} ===")
    
    try:
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取计划ID参数
        plan_id = request.args.get('plan_id', type=int)
        
        # 获取状态类型和内容类型参数
        status_type = request.args.get('status_type')
        content_type = request.args.get('content_type')
        
        # 构建查询条件
        query = BadCase.query.filter_by(project_id=project_id)
        
        # 处理status_type和content_type参数
        if status_type == 'unplanned':
            # 未计划的BadCase：没有关联计划的BadCase
            query = query.filter(BadCase.plan_id.is_(None))
            print(f"过滤未计划的BadCase (status_type=unplanned)")
        elif plan_id is not None:
            # 如果指定了计划ID，添加计划过滤条件
            if plan_id == 0:  # plan_id=0 表示未计划的BadCase
                query = query.filter(BadCase.plan_id.is_(None))
                print(f"过滤未计划的BadCase (plan_id=0)")
            else:
                query = query.filter_by(plan_id=plan_id)
                print(f"过滤计划ID为 {plan_id} 的BadCase")
        else:
            print("不进行计划过滤，显示所有BadCase")
        
        # 分页查询BadCase
        pagination = query.order_by(BadCase.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        badcases = []
        for bc in pagination.items:
            # 处理负责人字段，将用户ID转换为用户名
            assignee_display = '未指派'
            if bc.assignee:
                try:
                    # 如果assignee是逗号分隔的用户ID字符串
                    if ',' in str(bc.assignee):
                        user_ids = [int(uid.strip()) for uid in str(bc.assignee).split(',') if uid.strip()]
                        if user_ids:
                            users = User.query.filter(User.id.in_(user_ids)).all()
                            if len(users) == 1:
                                assignee_display = users[0].name
                            else:
                                assignee_display = f"{users[0].name}..." if users else '未指派'
                    else:
                        # 单个用户ID
                        user_id = int(bc.assignee)
                        user = User.query.get(user_id)
                        if user:
                            assignee_display = user.name
                except (ValueError, AttributeError):
                    # 如果转换失败，直接使用原值
                    assignee_display = str(bc.assignee) if bc.assignee else '未指派'
            
            badcases.append({
                'id': bc.id,
                'title': bc.title,
                'case_category': bc.case_category,
                'base_problem': bc.base_problem[:100] + '...' if len(bc.base_problem) > 100 else bc.base_problem,
                'priority': bc.priority,
                'status': bc.status,
                'assignee': assignee_display,
                'plan_id': bc.plan_id,  # 添加计划ID字段
                'created_at': bc.created_at.isoformat()
            })
        
        print(f"BadCase列表获取成功: 第{page}页，共{per_page}条，总计{pagination.total}条")
        
        return jsonify({
            'success': True,
            'badcases': badcases,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
    except Exception as e:
        print(f"获取项目BadCase列表失败: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取BadCase列表失败'}), 500

@app.route('/api/projects/<int:project_id>/revoke', methods=['POST'])
@login_required
def api_revoke_project(project_id):
    print(f"=== 开始撤销发布项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 检查权限
        print("检查项目权限...")
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权撤销发布项目 {project_id}")
            return jsonify({'success': False, 'error': '无权撤销发布此项目'}), 403
        print("权限检查通过")
        
        # 获取项目
        print(f"获取项目信息...")
        project = Project.query.get_or_404(project_id)
        print(f"项目信息: ID={project.id}, 名称={project.name}, 当前状态={project.status}")
        
        # 更新状态
        old_status = project.status
        project.status = 'unpublished'
        print(f"更新项目状态: {old_status} -> {project.status}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        response_data = {
            'success': True,
            'message': '项目撤销发布成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'status': project.status
            }
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 撤销发布完成 ===")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"撤销发布项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

# API端点 - BadCase管理
@app.route('/api/badcases', methods=['POST'])
@login_required
def api_create_badcase():
    print("=== 创建BadCase ===")
    print(f"当前用户ID: {current_user.id}")
    
    try:
        data = request.get_json()
        print(f"请求数据: {data}")
        
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        project_id = data.get('project_id')
        title = data.get('title')
        case_category = data.get('case_category')
        base_problem = data.get('base_problem')
        badcase_result = data.get('badcase_result')
        correct_answer = data.get('correct_answer')
        
        # 检查必要字段
        missing_fields = []
        if not project_id:
            missing_fields.append('project_id')
        if not title:
            missing_fields.append('title')
        if not case_category:
            missing_fields.append('case_category')
        if not base_problem:
            missing_fields.append('base_problem')
        if not badcase_result:
            missing_fields.append('badcase_result')
        if not correct_answer:
            missing_fields.append('correct_answer')
            
        if missing_fields:
            return jsonify({
                'success': False, 
                'error': f'缺少必要字段: {", ".join(missing_fields)}'
            }), 400
        
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权在此项目中创建BadCase'}), 403
        
        # 处理附件数据
        import json
        attachments_json = json.dumps(data.get('attachments', [])) if data.get('attachments') else None
        
        badcase = BadCase(
            project_id=project_id,
            creator_id=current_user.id,
            title=title,
            case_category=case_category,
            base_problem=base_problem,
            reproduction_steps=data.get('reproduction_steps', ''),
            badcase_result=badcase_result,
            correct_answer=correct_answer,
            correct_answer_final=data.get('correct_answer_final', ''),
            problem_reason=data.get('problem_reason', ''),
            solution=data.get('solution', ''),
            priority=data.get('priority', 'p3'),
            status=data.get('status', 'new'),
            assignee=data.get('assignee', ''),
            plan=data.get('plan', ''),
            document_type=data.get('document_type', '其他文档'),
            attachments=attachments_json,
            assigned_users=data.get('assigned_users', '')
        )
        
        db.session.add(badcase)
        db.session.commit()
        
        print(f"BadCase创建成功，ID: {badcase.id}")
        
        return jsonify({
            'success': True,
            'badcase': {
                'id': badcase.id,
                'title': badcase.title,
                'project_id': badcase.project_id,
                'creator_id': badcase.creator_id,
                'case_category': badcase.case_category,
                'base_problem': badcase.base_problem,
                'badcase_result': badcase.badcase_result,
                'correct_answer': badcase.correct_answer,
                'correct_answer_final': badcase.correct_answer_final,
                'priority': badcase.priority,
                'status': badcase.status,
                'assignee': badcase.assignee,
                'plan': badcase.plan,
                'created_at': badcase.created_at.isoformat()
            }
        })
        
    except Exception as e:
        import traceback
        print(f"创建BadCase失败: {e}")
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'创建BadCase失败: {str(e)}'}), 500

@app.route('/api/badcases/<int:badcase_id>', methods=['GET'])
@login_required
def api_get_badcase_detail(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权访问此BadCase'}), 403
    
    comments = Comment.query.filter_by(badcase_id=badcase_id).order_by(Comment.created_at.desc()).all()
    
    # 解析附件数据
    import json
    attachments = []
    if badcase.attachments:
        try:
            attachments = json.loads(badcase.attachments)
        except:
            attachments = []
    
    return jsonify({
        'success': True,
        'badcase': {
            'id': badcase.id,
            'project_id': badcase.project_id,  # 添加项目ID字段
            'title': badcase.title,
            'case_category': badcase.case_category,
            'base_problem': badcase.base_problem,
            'reproduction_steps': badcase.reproduction_steps,
            'badcase_result': badcase.badcase_result,
            'correct_answer': badcase.correct_answer,
            'correct_answer_final': badcase.correct_answer_final,
            'problem_reason': badcase.problem_reason,
            'solution': badcase.solution,
            'priority': badcase.priority,
            'status': badcase.status,
            'assignee': badcase.assignee,
            'plan': badcase.plan,
            'document_type': badcase.document_type,
            'attachments': attachments,
            'assigned_users': badcase.assigned_users,
            'created_at': badcase.created_at.isoformat(),
            'updated_at': badcase.updated_at.isoformat(),
            'comments': [{
                'id': comment.id,
                'content': comment.content,
                'user_name': comment.user.name,
                'created_at': comment.created_at.isoformat()
            } for comment in comments]
        }
    })

@app.route('/api/badcases/<int:badcase_id>/status', methods=['POST'])
@login_required
def api_update_badcase_status(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
    
    data = request.get_json()
    status = data.get('status')
    assigned_users = data.get('assigned_users')
    
    if status:
        badcase.status = status
    if assigned_users is not None:
        badcase.assigned_users = assigned_users
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/badcases/<int:badcase_id>/comment', methods=['POST'])
@login_required
def api_add_badcase_comment(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
    
    data = request.get_json()
    content = data.get('content')
    
    if not content:
        return jsonify({'success': False, 'error': '评论内容不能为空'}), 400
    
    comment = Comment(
        badcase_id=badcase_id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'comment': {
            'id': comment.id,
            'content': comment.content,
            'user_name': current_user.name,
            'created_at': comment.created_at.isoformat()
        }
    })

@app.route('/api/badcases/<int:badcase_id>', methods=['PUT'])
@login_required
def api_update_badcase(badcase_id):
    """更新BadCase信息"""
    print(f"=== 更新BadCase {badcase_id} ===")
    
    try:
        badcase = BadCase.query.get_or_404(badcase_id)
        
        if not has_project_permission(current_user.id, badcase.project_id):
            return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        print(f"更新数据: {data}")
        
        # 更新BadCase字段
        if 'title' in data:
            badcase.title = data['title']
        if 'case_category' in data:
            badcase.case_category = data['case_category']
        if 'base_problem' in data:
            badcase.base_problem = data['base_problem']
        if 'badcase_result' in data:
            badcase.badcase_result = data['badcase_result']
        if 'correct_answer' in data:
            badcase.correct_answer = data['correct_answer']
        if 'correct_answer_final' in data:
            badcase.correct_answer_final = data['correct_answer_final']
        if 'reproduction_steps' in data:
            badcase.reproduction_steps = data['reproduction_steps']
        if 'problem_reason' in data:
            badcase.problem_reason = data['problem_reason']
        if 'solution' in data:
            badcase.solution = data['solution']
        if 'priority' in data:
            badcase.priority = data['priority']
        if 'status' in data:
            badcase.status = data['status']
        if 'assignee' in data:
            badcase.assignee = data['assignee']
        if 'plan' in data:
            badcase.plan = data['plan']
        if 'document_type' in data:
            badcase.document_type = data['document_type']
        if 'attachments' in data:
            import json
            badcase.attachments = json.dumps(data['attachments']) if data['attachments'] else None
        if 'assigned_users' in data:
            badcase.assigned_users = data['assigned_users']
        
        db.session.commit()
        print("BadCase更新成功")
        
        return jsonify({'success': True, 'message': 'BadCase更新成功'})
        
    except Exception as e:
        print(f"更新BadCase失败: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': '更新BadCase失败'}), 500

@app.route('/api/badcases/<int:badcase_id>/close', methods=['POST'])
@login_required
def api_close_badcase(badcase_id):
    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
    
    badcase.status = 'close'
    db.session.commit()
    
    return jsonify({'success': True})



# CORS已在上面配置，这里不需要重复配置

def sync_database_schema():
    """同步数据库表结构，确保与代码中的模型完全一致"""
    try:
        print("开始同步数据库表结构...")
        
        # 获取数据库检查器
        inspector = inspect(db.engine)
        
        # 定义表结构映射
        table_definitions = {
            'user': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'email VARCHAR(120) UNIQUE NOT NULL',
                    'password_hash VARCHAR(200) NOT NULL',
                    'name VARCHAR(100) NOT NULL',
                    'role VARCHAR(20) DEFAULT "collaborator"',
                    'is_verified BOOLEAN DEFAULT FALSE',
                    'verification_code VARCHAR(10)',
                    'verification_expires DATETIME',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP'
                ]
            },
            'project': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(100) NOT NULL',
                    'description TEXT',
                    'avatar VARCHAR(500)',
                    'owner VARCHAR(100)',
                    'intro TEXT',
                    'status VARCHAR(20) DEFAULT "published"',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'user_id INT NOT NULL',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'project_permission': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'project_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'role VARCHAR(20) NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'bad_case': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'project_id INT NOT NULL',
                    'plan_id INT',
                    'creator_id INT NOT NULL',
                    'title VARCHAR(200)',
                    'case_category VARCHAR(100) NOT NULL',
                    'base_problem TEXT NOT NULL',
                    'reproduction_steps TEXT',
                    'badcase_result TEXT NOT NULL',
                    'correct_answer TEXT NOT NULL',
                    'correct_answer_final TEXT',
                    'problem_reason TEXT',
                    'needs_processing BOOLEAN DEFAULT TRUE',
                    'solution TEXT',
                    'is_verified BOOLEAN DEFAULT FALSE',
                    'priority VARCHAR(10) DEFAULT "p3"',
                    'status VARCHAR(20) DEFAULT "new"',
                    'assignee VARCHAR(100)',
                    'plan VARCHAR(100)',
                    'document_type VARCHAR(100)',
                    'attachments TEXT',
                    'assigned_users TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (plan_id) REFERENCES plan(id)',
                    'FOREIGN KEY (creator_id) REFERENCES user(id)'
                ]
            },
            'comment': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'badcase_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (badcase_id) REFERENCES bad_case(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'prompt_template': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(100) NOT NULL',
                    'content TEXT NOT NULL',
                    'project_id INT NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (project_id) REFERENCES project(id)'
                ]
            },
            'team': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(100) NOT NULL',
                    'description TEXT',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (creator_id) REFERENCES user(id)'
                ]
            },
            'team_member': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'team_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'role VARCHAR(20) DEFAULT "member"',
                    'permissions TEXT',
                    'joined_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (team_id) REFERENCES team(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'plan': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'name VARCHAR(200) NOT NULL',
                    'description TEXT',
                    'plan_type VARCHAR(20) NOT NULL',
                    'status VARCHAR(20) DEFAULT "active"',
                    'priority VARCHAR(10) DEFAULT "medium"',
                    'is_pinned BOOLEAN DEFAULT FALSE',
                    'start_date DATE',
                    'end_date DATE',
                    'progress FLOAT DEFAULT 0.0',
                    'parent_id INT',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'assignee_id INT',
                    'cycle VARCHAR(20)',
                    'plan_count INT DEFAULT 1',
                    'scope_notification BOOLEAN DEFAULT FALSE',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (parent_id) REFERENCES plan(id)',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (creator_id) REFERENCES user(id)',
                    'FOREIGN KEY (assignee_id) REFERENCES user(id)'
                ]
            },
            'bug': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'title VARCHAR(200) NOT NULL',
                    'description TEXT NOT NULL',
                    'steps_to_reproduce TEXT',
                    'expected_result TEXT',
                    'actual_result TEXT',
                    'severity VARCHAR(20) DEFAULT "medium"',
                    'priority VARCHAR(10) DEFAULT "p3"',
                    'status VARCHAR(20) DEFAULT "new"',
                    'bug_type VARCHAR(50)',
                    'environment VARCHAR(100)',
                    'browser VARCHAR(50)',
                    'os VARCHAR(50)',
                    'plan_id INT NOT NULL',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'assignee_id INT',
                    'attachments TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (plan_id) REFERENCES plan(id)',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (creator_id) REFERENCES user(id)',
                    'FOREIGN KEY (assignee_id) REFERENCES user(id)'
                ]
            },
            'bug_comment': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'bug_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (bug_id) REFERENCES bug(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'chat_session': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'title VARCHAR(200) NOT NULL',
                    'project_id INT NOT NULL',
                    'user_id INT NOT NULL',
                    'is_active BOOLEAN DEFAULT 1',
                    'memory_enabled BOOLEAN DEFAULT 1',
                    'memory_data TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'chat_message': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'session_id INT NOT NULL',
                    'user_id INT',
                    'is_user BOOLEAN DEFAULT 1',
                    'content TEXT NOT NULL',
                    'understanding TEXT',
                    'steps TEXT',
                    'execution_results TEXT',
                    'agent_result TEXT',
                    'evidences TEXT',
                    'final_response TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (session_id) REFERENCES chat_session(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            }
        }
        
        # 检查并创建/更新每个表
        for table_name, definition in table_definitions.items():
            # 检查表是否存在
            table_exists = inspector.has_table(table_name)
            
            if not table_exists:
                # 创建新表
                create_sql = f"CREATE TABLE {table_name} (\n    " + ",\n    ".join(definition['columns']) + "\n)"
                db.session.execute(text(create_sql))
                print(f"已创建表: {table_name}")
            else:
                # 检查现有表的列
                existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
                required_columns = []
                
                # 解析需要的列
                for col_def in definition['columns']:
                    if 'FOREIGN KEY' not in col_def and 'PRIMARY KEY' not in col_def:
                        col_name = col_def.split()[0]
                        if col_name not in existing_columns:
                            required_columns.append(col_def)
                
                # 添加缺失的列
                for col_def in required_columns:
                    col_name = col_def.split()[0]
                    if col_name not in existing_columns:
                        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_def}"
                        db.session.execute(text(alter_sql))
                        print(f"已添加列 {table_name}.{col_name}")
        
        db.session.commit()
        print("数据库表结构同步完成")
        
        # 创建性能优化索引
        create_performance_indexes()
        
        # 创建测试用户（如果不存在）
        test_user = User.query.filter_by(email='test@example.com').first()
        if not test_user:
            test_user = User(
                email='test@example.com',
                password_hash=generate_password_hash('123456'),
                name='测试用户',
                is_verified=True
            )
            db.session.add(test_user)
            print("已创建测试用户: test@example.com / 123456")
        
        # 创建指定用户账号（如果不存在）
        specified_user = User.query.filter_by(email='2629258027@qq.com').first()
        if not specified_user:
            specified_user = User(
                email='2629258027@qq.com',
                password_hash=generate_password_hash('123456'),
                name='hx',
                is_verified=True
            )
            db.session.add(specified_user)
            print("已创建指定用户: 2629258027@qq.com / 123456")
        else:
            # 如果用户已存在，更新密码为123456
            specified_user.password_hash = generate_password_hash('123456')
            print("已更新用户密码: 2629258027@qq.com / 123456")
        
        db.session.commit()
        
        return True
        
    except Exception as e:
        print(f"数据库同步过程中出现错误: {e}")
        db.session.rollback()
        return False

def create_performance_indexes():
    """创建性能优化索引"""
    try:
        print("开始创建性能优化索引...")
        
        # 定义需要创建的索引（MySQL不支持IF NOT EXISTS，使用try-catch处理）
        indexes = [
            # 用户表索引
            ("idx_user_email", "CREATE INDEX idx_user_email ON user(email)"),
            ("idx_user_created_at", "CREATE INDEX idx_user_created_at ON user(created_at)"),
            
            # 项目表索引
            ("idx_project_user_id", "CREATE INDEX idx_project_user_id ON project(user_id)"),
            ("idx_project_status", "CREATE INDEX idx_project_status ON project(status)"),
            ("idx_project_created_at", "CREATE INDEX idx_project_created_at ON project(created_at)"),
            ("idx_project_name", "CREATE INDEX idx_project_name ON project(name)"),
            
            # 项目权限表索引
            ("idx_permission_user_id", "CREATE INDEX idx_permission_user_id ON project_permission(user_id)"),
            ("idx_permission_project_id", "CREATE INDEX idx_permission_project_id ON project_permission(project_id)"),
            ("unique_user_project", "CREATE UNIQUE INDEX unique_user_project ON project_permission(user_id, project_id)"),
            
            # BadCase表索引
            ("idx_badcase_project_id", "CREATE INDEX idx_badcase_project_id ON bad_case(project_id)"),
            ("idx_badcase_creator_id", "CREATE INDEX idx_badcase_creator_id ON bad_case(creator_id)"),
            ("idx_badcase_status", "CREATE INDEX idx_badcase_status ON bad_case(status)"),
            ("idx_badcase_priority", "CREATE INDEX idx_badcase_priority ON bad_case(priority)"),
            ("idx_badcase_created_at", "CREATE INDEX idx_badcase_created_at ON bad_case(created_at)"),
            # 复合索引 - 优化项目BadCase查询
            ("idx_badcase_project_status", "CREATE INDEX idx_badcase_project_status ON bad_case(project_id, status)"),
            ("idx_badcase_project_created", "CREATE INDEX idx_badcase_project_created ON bad_case(project_id, created_at)"),
            
            # 评论表索引
            ("idx_comment_badcase_id", "CREATE INDEX idx_comment_badcase_id ON comment(badcase_id)"),
            ("idx_comment_user_id", "CREATE INDEX idx_comment_user_id ON comment(user_id)"),
            ("idx_comment_created_at", "CREATE INDEX idx_comment_created_at ON comment(created_at)"),
            
            # 提示模板表索引
            ("idx_template_project_id", "CREATE INDEX idx_template_project_id ON prompt_template(project_id)"),
            ("idx_template_name", "CREATE INDEX idx_template_name ON prompt_template(name)"),
            
            # 计划表索引
            ("idx_plan_project_id", "CREATE INDEX idx_plan_project_id ON plan(project_id)"),
            ("idx_plan_parent_id", "CREATE INDEX idx_plan_parent_id ON plan(parent_id)"),
            ("idx_plan_type", "CREATE INDEX idx_plan_type ON plan(plan_type)"),
            ("idx_plan_status", "CREATE INDEX idx_plan_status ON plan(status)"),
            ("idx_plan_creator_id", "CREATE INDEX idx_plan_creator_id ON plan(creator_id)"),
            ("idx_plan_assignee_id", "CREATE INDEX idx_plan_assignee_id ON plan(assignee_id)"),
            
            # Bug表索引
            ("idx_bug_project_id", "CREATE INDEX idx_bug_project_id ON bug(project_id)"),
            ("idx_bug_plan_id", "CREATE INDEX idx_bug_plan_id ON bug(plan_id)"),
            ("idx_bug_creator_id", "CREATE INDEX idx_bug_creator_id ON bug(creator_id)"),
            ("idx_bug_assignee_id", "CREATE INDEX idx_bug_assignee_id ON bug(assignee_id)"),
            ("idx_bug_status", "CREATE INDEX idx_bug_status ON bug(status)"),
            ("idx_bug_priority", "CREATE INDEX idx_bug_priority ON bug(priority)"),
            ("idx_bug_severity", "CREATE INDEX idx_bug_severity ON bug(severity)"),
            
            # Bug评论表索引
            ("idx_bug_comment_bug_id", "CREATE INDEX idx_bug_comment_bug_id ON bug_comment(bug_id)"),
            ("idx_bug_comment_user_id", "CREATE INDEX idx_bug_comment_user_id ON bug_comment(user_id)"),
            
            # BadCase表新增索引
            ("idx_badcase_plan_id", "CREATE INDEX idx_badcase_plan_id ON bad_case(plan_id)")
        ]
        
        # 执行索引创建
        for index_name, index_sql in indexes:
            try:
                db.session.execute(text(index_sql))
                print(f"已创建索引: {index_name}")
            except Exception as e:
                # 如果索引已存在，忽略错误
                if "Duplicate key name" not in str(e) and "already exists" not in str(e):
                    print(f"创建索引失败 {index_name}: {e}")
                else:
                    print(f"索引 {index_name} 已存在，跳过")
        
        db.session.commit()
        print("性能优化索引创建完成")
        
    except Exception as e:
        print(f"创建索引时发生错误: {e}")
        db.session.rollback()

# 计划相关API接口
@app.route('/api/plans', methods=['POST'])
@login_required
def api_create_plan():
    """创建计划"""
    try:
        print("=== 创建计划API被调用 ===")
        data = request.get_json()
        print(f"接收到的数据: {data}")
        print(f"当前用户ID: {current_user.id}")
            
        # 验证必填字段
        required_fields = ['name', 'cycle', 'start_date', 'end_date', 'project_id']
        for field in required_fields:
            if not data.get(field):
                print(f"缺少必填字段: {field}")
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
            
        # 验证计划周期
        valid_cycles = ['one_week', 'two_weeks', 'one_month', 'custom']
        if data.get('cycle') and data['cycle'] not in valid_cycles:
            return jsonify({'success': False, 'error': '无效的计划周期'}), 400
            
        # 检查项目权限
        print(f"检查项目权限: 用户ID={current_user.id}, 项目 ID={data['project_id']}")
        if not has_project_permission(current_user.id, data['project_id']):
            print("权限检查失败")
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        print("权限检查通过")
            
        # 检查父计划是否存在
        if data.get('parent_id'):
            parent_plan = Plan.query.get(data['parent_id'])
            if not parent_plan:
                return jsonify({'success': False, 'error': '父计划不存在'}), 404
            
        # 验证日期格式
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else None
        except ValueError:
            return jsonify({'success': False, 'error': '日期格式错误，请使用 YYYY-MM-DD 格式'}), 400
            
        # 创建计划
        plan = Plan(
            name=data['name'],
            description=data.get('description', ''),
            plan_type=data.get('plan_type', 'badcase'),  # 默认为badcase类型
            status=data.get('status', 'active'),
            priority=data.get('priority', 'medium'),
            start_date=start_date,
            end_date=end_date,
            cycle=data.get('cycle'),
            plan_count=data.get('count', 1),
            scope_notification=data.get('scope_notification', False),
            parent_id=data.get('parent_id'),
            project_id=data['project_id'],
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id')
        )
            
        db.session.add(plan)
        db.session.commit()
            
        return jsonify({
            'success': True,
            'message': '计划创建成功',
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'description': plan.description,
                'plan_type': plan.plan_type,
                'status': plan.status,
                'priority': plan.priority,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'cycle': plan.cycle,
                'plan_count': plan.plan_count,
                'scope_notification': plan.scope_notification,
                'parent_id': plan.parent_id,
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            }
        })
            
    except Exception as e:
        db.session.rollback()
        print(f"创建计划失败: {e}")
        return jsonify({'success': False, 'error': '创建计划失败'}), 500

@app.route('/api/plans/<int:plan_id>', methods=['GET'])
@login_required
def api_get_plan_detail(plan_id):
    """获取计划详情"""
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 获取子计划
        children = []
        for child in plan.children:
            children.append({
                'id': child.id,
                'name': child.name,
                'plan_type': child.plan_type,
                'status': child.status,
                'progress': child.progress,
                'created_at': child.created_at.isoformat()
            })
        
        # 获取BadCase或Bug列表
        items = []
        if plan.plan_type == 'badcase':
            for badcase in plan.badcases:
                items.append({
                    'id': badcase.id,
                    'title': badcase.title,
                    'case_category': badcase.case_category,
                    'status': badcase.status,
                    'priority': badcase.priority,
                    'assignee': badcase.assignee,
                    'created_at': badcase.created_at.isoformat(),
                    'type': 'badcase'
                })
        else:  # bug类型
            for bug in plan.bugs:
                items.append({
                    'id': bug.id,
                    'title': bug.title,
                    'bug_type': bug.bug_type,
                    'status': bug.status,
                    'priority': bug.priority,
                    'severity': bug.severity,
                    'assignee_id': bug.assignee_id,
                    'created_at': bug.created_at.isoformat(),
                    'type': 'bug'
                })
        
        return jsonify({
            'success': True,
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'description': plan.description,
                'plan_type': plan.plan_type,
                'status': plan.status,
                'priority': plan.priority,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'parent_id': plan.parent_id,
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat(),
                'children': children,
                'items': items
            }
        })
        
    except Exception as e:
        print(f"获取计划详情失败: {e}")
        return jsonify({'success': False, 'error': '获取计划详情失败'}), 500

@app.route('/api/plans/<int:plan_id>', methods=['PUT'])
@login_required
def api_update_plan(plan_id):
    """更新计划"""
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        data = request.get_json()
        
        # 更新字段
        if 'name' in data:
            plan.name = data['name']
        if 'description' in data:
            plan.description = data['description']
        if 'status' in data:
            plan.status = data['status']
        if 'priority' in data:
            plan.priority = data['priority']
        if 'start_date' in data:
            plan.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data['start_date'] else None
        if 'end_date' in data:
            plan.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data['end_date'] else None
        if 'progress' in data:
            plan.progress = data['progress']
        if 'assignee_id' in data:
            plan.assignee_id = data['assignee_id']
        
        plan.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '计划更新成功',
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'description': plan.description,
                'plan_type': plan.plan_type,
                'status': plan.status,
                'priority': plan.priority,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'parent_id': plan.parent_id,
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"更新计划失败: {e}")
        return jsonify({'success': False, 'error': '更新计划失败'}), 500

@app.route('/api/plans/<int:plan_id>', methods=['DELETE'])
@login_required
def api_delete_plan(plan_id):
    """删除计划"""
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 检查是否有子计划
        if plan.children:
            return jsonify({'success': False, 'error': '无法删除包含子计划的计划'}), 400
        
        # 检查是否有关联的BadCase或Bug
        if plan.plan_type == 'badcase' and plan.badcases:
            return jsonify({'success': False, 'error': '无法删除包含BadCase的计划'}), 400
        elif plan.plan_type == 'bug' and plan.bugs:
            return jsonify({'success': False, 'error': '无法删除包含Bug的计划'}), 400
        
        db.session.delete(plan)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '计划删除成功'})
        
    except Exception as e:
        db.session.rollback()
        print(f"删除计划失败: {e}")
        return jsonify({'success': False, 'error': '删除计划失败'}), 500

@app.route('/api/plans/<int:plan_id>/pin', methods=['POST'])
@login_required
def api_pin_plan(plan_id):
    """置顶/取消置顶计划"""
    try:
        print(f"=== 置顶计划API被调用 ===")
        print(f"计划ID: {plan_id}")
        print(f"当前用户ID: {current_user.id}")
        
        # 获取计划
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有权限'}), 403
        
        # 切换置顶状态
        plan.is_pinned = not plan.is_pinned
        db.session.commit()
        
        action = "置顶" if plan.is_pinned else "取消置顶"
        print(f"计划 {plan.name} {action}成功")
        
        return jsonify({
            'success': True,
            'message': f'计划{action}成功',
            'is_pinned': plan.is_pinned
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"置顶计划失败: {e}")
        return jsonify({'success': False, 'error': '置顶计划失败'}), 500

@app.route('/api/projects/<int:project_id>/plans', methods=['GET'])
@login_required
def api_get_project_plans(project_id):
    """获取项目的计划树"""
    try:
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 获取顶级计划（没有父计划的计划），按置顶状态和创建时间排序
        root_plans = Plan.query.filter_by(project_id=project_id, parent_id=None).order_by(
            Plan.is_pinned.desc(),  # 置顶的在前
            Plan.created_at.desc()  # 然后按创建时间倒序
        ).all()
        print(f"=== 获取项目 {project_id} 的计划 ===")
        print(f"找到 {len(root_plans)} 个顶级计划")
        for plan in root_plans:
            print(f"计划: {plan.name} (ID: {plan.id}, 状态: {plan.status}, 置顶: {plan.is_pinned}, 创建时间: {plan.created_at})")
        
        def build_plan_tree(plan):
            """递归构建计划树"""
            children = []
            for child in plan.children:
                children.append(build_plan_tree(child))
            
            plan_data = {
                'id': plan.id,
                'name': plan.name,
                'description': plan.description,
                'plan_type': plan.plan_type,
                'status': plan.status,
                'priority': plan.priority,
                'is_pinned': plan.is_pinned,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat(),
                'children': children,
                'badcase_count': BadCase.query.filter_by(plan_id=plan.id).count() if plan.plan_type == 'badcase' else 0,
                'bug_count': Bug.query.filter_by(plan_id=plan.id).count() if plan.plan_type == 'bug' else 0
            }
            print(f"[DEBUG] Plan data: ID={plan.id}, name={plan.name}, plan_type={plan.plan_type}")
            return plan_data
        
        plans_tree = []
        for plan in root_plans:
            plans_tree.append(build_plan_tree(plan))
        
        return jsonify({
            'success': True,
            'plans': plans_tree
        })
        
    except Exception as e:
        import traceback
        print(f"获取项目计划失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'获取项目计划失败: {str(e)}'}), 500

    # 团队管理API接口
@app.route('/api/teams', methods=['POST'])
@login_required
def api_create_team():
    """创建团队"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['name', 'project_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, data['project_id']):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 创建团队
        team = Team(
            name=data['name'],
            description=data.get('description', ''),
            project_id=data['project_id'],
            creator_id=current_user.id
        )
        
        db.session.add(team)
        db.session.commit()
        
        # 创建者自动成为团队成员
        team_member = TeamMember(
            team_id=team.id,
            user_id=current_user.id,
            role='leader'
        )
        db.session.add(team_member)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'team': {
                'id': team.id,
                'name': team.name,
                'description': team.description,
                'project_id': team.project_id,
                'creator_id': team.creator_id,
                'created_at': team.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"创建团队失败: {e}")
        return jsonify({'success': False, 'error': '创建团队失败'}), 500

@app.route('/api/teams/<int:team_id>/members', methods=['POST'])
@login_required
def api_add_team_member(team_id):
    """添加团队成员"""
    try:
        import json
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('user_id'):
            return jsonify({'success': False, 'error': '缺少用户ID'}), 400
        
        # 检查团队是否存在
        team = Team.query.get(team_id)
        if not team:
            return jsonify({'success': False, 'error': '团队不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, team.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 检查用户是否已经是团队成员
        existing_member = TeamMember.query.filter_by(
            team_id=team_id, 
            user_id=data['user_id']
        ).first()
        
        if existing_member:
            return jsonify({'success': False, 'error': '用户已经是团队成员'}), 400
        
        # 添加团队成员
        team_member = TeamMember(
            team_id=team_id,
            user_id=data['user_id'],
            role=data.get('role', 'member'),
            permissions=json.dumps(data.get('permissions', ['view_project']))
        )
        
        db.session.add(team_member)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'member': {
                'id': team_member.id,
                'team_id': team_member.id,
                'user_id': team_member.user_id,
                'role': team_member.role,
                'permissions': json.loads(team_member.permissions) if team_member.permissions else ['view_project'],
                'joined_at': team_member.joined_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"添加团队成员失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'添加团队成员失败: {str(e)}'}), 500

@app.route('/api/projects/<int:project_id>/teams', methods=['GET'])
@login_required
def api_get_project_teams(project_id):
    """获取项目的团队列表"""
    try:
        import json
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 获取项目下的所有团队
        teams = Team.query.filter_by(project_id=project_id).all()
        
        teams_data = []
        for team in teams:
            # 获取团队成员
            members = TeamMember.query.filter_by(team_id=team.id).all()
            members_data = []
            
            for member in members:
                user = User.query.get(member.user_id)
                if user:
                    members_data.append({
                        'id': member.id,
                        'user_id': member.user_id,
                        'user_name': user.name,
                        'user_email': user.email,
                        'role': member.role,
                        'permissions': json.loads(member.permissions) if member.permissions else ['view_project'],
                        'joined_at': member.joined_at.isoformat()
                    })
            
            teams_data.append({
                'id': team.id,
                'name': team.name,
                'description': team.description,
                'project_id': team.project_id,
                'creator_id': team.creator_id,
                'created_at': team.created_at.isoformat(),
                'members': members_data
            })
        
        return jsonify({
            'success': True,
            'teams': teams_data
        })
        
    except Exception as e:
        print(f"获取项目团队失败: {e}")
        return jsonify({'success': False, 'error': '获取项目团队失败'}), 500

@app.route('/api/projects/<int:project_id>/members', methods=['GET'])
@login_required
def api_get_project_members(project_id):
    """获取项目的所有成员（包括直接权限和团队成员）"""
    try:
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 获取直接项目权限的用户
        direct_permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
        direct_members = []
        
        for perm in direct_permissions:
            user = User.query.get(perm.user_id)
            if user:
                direct_members.append({
                    'id': user.id,
                    'name': user.name,
                    'email': user.email,
                    'role': perm.role,
                    'source': 'direct_permission'
                })
        
        # 获取团队成员
        teams = Team.query.filter_by(project_id=project_id).all()
        team_members = []
        
        for team in teams:
            members = TeamMember.query.filter_by(team_id=team.id).all()
            for member in members:
                user = User.query.get(member.user_id)
                if user:
                    # 检查是否已经在直接成员列表中
                    if not any(dm['id'] == user.id for dm in direct_members):
                        team_members.append({
                            'id': user.id,
                            'name': user.name,
                            'email': user.email,
                            'role': member.role,
                            'source': f'team_{team.name}'
                        })
        
        # 合并所有成员
        all_members = direct_members + team_members
        
        return jsonify({
            'success': True,
            'members': all_members
        })
        
    except Exception as e:
        print(f"获取项目成员失败: {e}")
        return jsonify({'success': False, 'error': '获取项目成员失败'}), 500

@app.route('/api/users/available', methods=['GET'])
@login_required
def api_get_available_users():
    """获取所有可用的注册用户（用于添加团队成员）"""
    try:
        # 获取所有已注册的用户
        users = User.query.filter_by(is_verified=True).all()
        
        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role if hasattr(user, 'role') else None
            })
        
        return jsonify({
            'success': True,
            'users': users_data
        })
        
    except Exception as e:
        print(f"获取可用用户失败: {e}")
        return jsonify({'success': False, 'error': '获取可用用户失败'}), 500

@app.route('/api/projects/<int:project_id>/add_user', methods=['POST'])
@login_required
def api_add_project_user(project_id):
    """添加用户到项目（需要管理员权限）"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('user_id') or not data.get('role'):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id, 'admin'):
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        
        # 检查用户是否存在
        user = User.query.get(data['user_id'])
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        
        # 检查是否已经有权限
        existing_permission = ProjectPermission.query.filter_by(
            project_id=project_id, 
            user_id=data['user_id']
        ).first()
        
        if existing_permission:
            return jsonify({'success': False, 'error': '用户已有项目权限'}), 400
        
        # 添加权限
        permission = ProjectPermission(
            project_id=project_id,
            user_id=data['user_id'],
            role=data['role']
        )
        
        db.session.add(permission)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'permission': {
                'id': permission.id,
                'project_id': permission.project_id,
                'user_id': permission.user_id,
                'role': permission.role,
                'created_at': permission.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"添加项目用户失败: {e}")
        return jsonify({'success': False, 'error': '添加项目用户失败'}), 500

    # Bug相关API接口
@app.route('/api/bugs', methods=['POST'])
@login_required
def api_create_bug():
    """创建Bug"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['title', 'plan_id', 'project_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, data['project_id']):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 检查计划是否存在且为bug类型
        plan = Plan.query.get(data['plan_id'])
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        if plan.plan_type != 'bug':
            return jsonify({'success': False, 'error': '只能在bug类型计划中创建bug'}), 400
        
        # 创建Bug
        bug = Bug(
            title=data['title'],
            description=data.get('description', ''),
            steps_to_reproduce=data.get('steps_to_reproduce', ''),
            expected_result=data.get('expected_result', ''),
            actual_result=data.get('actual_result', ''),
            severity=data.get('severity', 'medium'),
            priority=data.get('priority', 'p3'),
            status=data.get('status', 'new'),
            bug_type=data.get('bug_type', ''),
            environment=data.get('environment', ''),
            browser=data.get('browser', ''),
            os=data.get('os', ''),
            plan_id=data['plan_id'],
            project_id=data['project_id'],
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id'),
            attachments=data.get('attachments', '')
        )
        
        db.session.add(bug)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Bug创建成功',
            'bug': {
                'id': bug.id,
                'title': bug.title,
                'description': bug.description,
                'severity': bug.severity,
                'priority': bug.priority,
                'status': bug.status,
                'bug_type': bug.bug_type,
                'plan_id': bug.plan_id,
                'project_id': bug.project_id,
                'creator_id': bug.creator_id,
                'assignee_id': bug.assignee_id,
                'created_at': bug.created_at.isoformat(),
                'updated_at': bug.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"创建Bug失败: {e}")
        return jsonify({'success': False, 'error': '创建Bug失败'}), 500

@app.route('/api/projects/<int:project_id>/bugs', methods=['GET'])
@login_required
def api_get_project_bugs(project_id):
    """获取项目的Bug列表（分页）"""
    try:
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取计划ID参数
        plan_id = request.args.get('plan_id', type=int)
        
        # 构建查询条件
        query = Bug.query.filter_by(project_id=project_id)
        
        if plan_id is not None:
            query = query.filter_by(plan_id=plan_id)
        
        # 分页查询Bug
        pagination = query.order_by(Bug.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        bugs = []
        for bug in pagination.items:
            # 获取负责人姓名
            assignee_name = '未指派'
            if bug.assignee_id:
                user = User.query.get(bug.assignee_id)
                if user:
                    assignee_name = user.name
            
            bugs.append({
                'id': bug.id,
                'title': bug.title,
                'description': bug.description,
                'bug_type': bug.bug_type,
                'priority': bug.priority,
                'status': bug.status,
                'assignee': assignee_name,
                'plan_id': bug.plan_id,
                'created_at': bug.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'badcases': bugs, # 为了兼容前端 filteredBadcases，这里暂时使用 badcases 键名
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
    except Exception as e:
        print(f"获取项目Bug列表失败: {e}")
        return jsonify({'success': False, 'error': '获取Bug列表失败'}), 500

@app.route('/api/bugs/<int:bug_id>', methods=['GET', 'PUT'])
@login_required
def api_bug_detail(bug_id):
    """Bug详情接口：GET查询，PUT更新"""
    if request.method == 'GET':
        try:
            bug = Bug.query.get(bug_id)
            if not bug:
                return jsonify({'success': False, 'error': 'Bug不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, bug.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            # 获取评论
            comments = []
            for comment in bug.comments:
                comments.append({
                    'id': comment.id,
                    'content': comment.content,
                    'user_id': comment.user_id,
                    'user_name': comment.user.name,
                    'created_at': comment.created_at.isoformat()
                })
            
            return jsonify({
                'success': True,
                'bug': {
                    'id': bug.id,
                    'title': bug.title,
                    'description': bug.description,
                    'steps_to_reproduce': bug.steps_to_reproduce,
                    'expected_result': bug.expected_result,
                    'actual_result': bug.actual_result,
                    'severity': bug.severity,
                    'priority': bug.priority,
                    'status': bug.status,
                    'bug_type': bug.bug_type,
                    'environment': bug.environment,
                    'browser': bug.browser,
                    'os': bug.os,
                    'plan_id': bug.plan_id,
                    'project_id': bug.project_id,
                    'creator_id': bug.creator_id,
                    'assignee_id': bug.assignee_id,
                    'attachments': bug.attachments,
                    'created_at': bug.created_at.isoformat(),
                    'updated_at': bug.updated_at.isoformat(),
                    'comments': comments
                }
            })
            
        except Exception as e:
            print(f"获取Bug详情失败: {e}")
            return jsonify({'success': False, 'error': '获取Bug详情失败'}), 500
    
    elif request.method == 'PUT':
        try:
            bug = Bug.query.get(bug_id)
            if not bug:
                return jsonify({'success': False, 'error': 'Bug不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, bug.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            data = request.json
            
            # 更新字段
            if 'title' in data:
                bug.title = data['title']
            if 'description' in data:
                bug.description = data['description']
            if 'steps_to_reproduce' in data:
                bug.steps_to_reproduce = data['steps_to_reproduce']
            if 'expected_result' in data:
                bug.expected_result = data['expected_result']
            if 'actual_result' in data:
                bug.actual_result = data['actual_result']
            if 'severity' in data:
                bug.severity = data['severity']
            if 'priority' in data:
                bug.priority = data['priority']
            if 'status' in data:
                bug.status = data['status']
            if 'bug_type' in data:
                bug.bug_type = data['bug_type']
            if 'environment' in data:
                bug.environment = data['environment']
            if 'browser' in data:
                bug.browser = data['browser']
            if 'os' in data:
                bug.os = data['os']
            if 'plan_id' in data:
                bug.plan_id = data['plan_id']
            if 'assignee_id' in data:
                bug.assignee_id = data['assignee_id']
            if 'attachments' in data:
                bug.attachments = data['attachments']
            
            bug.updated_at = datetime.now()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Bug更新成功',
                'bug': {
                    'id': bug.id,
                    'title': bug.title,
                    'status': bug.status,
                    'updated_at': bug.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"更新Bug失败: {e}")
            return jsonify({'success': False, 'error': '更新Bug失败'}), 500

@app.route('/api/bugs/<int:bug_id>/comment', methods=['POST'])
@login_required
def api_add_bug_comment(bug_id):
    """为Bug添加评论"""
    try:
        bug = Bug.query.get(bug_id)
        if not bug:
            return jsonify({'success': False, 'error': 'Bug不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, bug.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        data = request.get_json()
        if not data.get('content'):
            return jsonify({'success': False, 'error': '评论内容不能为空'}), 400
        
        comment = BugComment(
            bug_id=bug_id,
            user_id=current_user.id,
            content=data['content']
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '评论添加成功',
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'user_id': comment.user_id,
                'user_name': comment.user.name,
                'created_at': comment.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"添加Bug评论失败: {e}")
        return jsonify({'success': False, 'error': '添加评论失败'}), 500

# ==================== TestCase API ====================

@app.route('/api/testcases', methods=['POST'])
@login_required
def api_create_testcase():
    """创建TestCase"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('title'):
            return jsonify({'success': False, 'error': '缺少必填字段: title'}), 400
        if not data.get('project_id'):
            return jsonify({'success': False, 'error': '缺少必填字段: project_id'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, data['project_id']):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 如果指定了plan_id，检查计划是否为testcase类型
        if data.get('plan_id'):
            plan = Plan.query.get(data['plan_id'])
            if not plan:
                return jsonify({'success': False, 'error': '计划不存在'}), 404
            if plan.plan_type != 'testcase':
                return jsonify({'success': False, 'error': '只能在testcase类型计划中创建测试用例'}), 400
        
        # 创建TestCase
        testcase = TestCase(
            title=data['title'],
            status=data.get('status', 'draft'),
            case_type=data.get('case_type', '功能测试'),
            priority=data.get('priority', 'P3'),
            test_type=data.get('test_type', '手动'),
            preconditions=data.get('preconditions', ''),
            steps=data.get('steps', []),
            remark=data.get('remark', ''),
            requirement_id=data.get('requirement_id'),
            related_defects=data.get('related_defects', []),
            baseline=data.get('baseline', ''),
            estimated_time=data.get('estimated_time', 0),
            version=data.get('version', 'v1'),
            plan_id=data.get('plan_id'),
            project_id=data['project_id'],
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id')
        )
        
        db.session.add(testcase)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '测试用例创建成功',
            'testcase': {
                'id': testcase.id,
                'title': testcase.title,
                'status': testcase.status,
                'priority': testcase.priority,
                'created_at': testcase.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"创建TestCase失败: {e}")
        return jsonify({'success': False, 'error': '创建TestCase失败'}), 500

@app.route('/api/testcases/<int:testcase_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_testcase_detail(testcase_id):
    """测试用例详情接口：GET查询，PUT更新，DELETE删除"""
    if request.method == 'GET':
        try:
            testcase = TestCase.query.get(testcase_id)
            if not testcase:
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, testcase.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            return jsonify({
                'success': True,
                'testcase': {
                    'id': testcase.id,
                    'title': testcase.title,
                    'status': testcase.status,
                    'case_type': testcase.case_type,
                    'priority': testcase.priority,
                    'test_type': testcase.test_type,
                    'preconditions': testcase.preconditions,
                    'steps': testcase.steps,
                    'remark': testcase.remark,
                    'requirement_id': testcase.requirement_id,
                    'related_defects': testcase.related_defects,
                    'baseline': testcase.baseline,
                    'estimated_time': testcase.estimated_time,
                    'actual_time': testcase.actual_time,
                    'remaining_time': testcase.remaining_time,
                    'last_executed': testcase.last_executed.isoformat() if testcase.last_executed else None,
                    'executed_by': testcase.executed_by,
                    'execution_result': testcase.execution_result,
                    'version': testcase.version,
                    'plan_id': testcase.plan_id,
                    'project_id': testcase.project_id,
                    'creator_id': testcase.creator_id,
                    'assignee_id': testcase.assignee_id,
                    'created_at': testcase.created_at.isoformat(),
                    'updated_at': testcase.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            print(f"获取TestCase详情失败: {e}")
            return jsonify({'success': False, 'error': '获取TestCase详情失败'}), 500
    
    elif request.method == 'PUT':
        try:
            testcase = TestCase.query.get(testcase_id)
            if not testcase:
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, testcase.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            data = request.json
            
            # 更新字段
            if 'title' in data:
                testcase.title = data['title']
            if 'status' in data:
                testcase.status = data['status']
            if 'case_type' in data:
                testcase.case_type = data['case_type']
            if 'priority' in data:
                testcase.priority = data['priority']
            if 'test_type' in data:
                testcase.test_type = data['test_type']
            if 'preconditions' in data:
                testcase.preconditions = data['preconditions']
            if 'steps' in data:
                testcase.steps = data['steps']
            if 'remark' in data:
                testcase.remark = data['remark']
            if 'requirement_id' in data:
                testcase.requirement_id = data['requirement_id']
            if 'related_defects' in data:
                testcase.related_defects = data['related_defects']
            if 'baseline' in data:
                testcase.baseline = data['baseline']
            if 'estimated_time' in data:
                testcase.estimated_time = data['estimated_time']
            if 'actual_time' in data:
                testcase.actual_time = data['actual_time']
            if 'remaining_time' in data:
                testcase.remaining_time = data['remaining_time']
            if 'last_executed' in data:
                testcase.last_executed = data['last_executed']
            if 'executed_by' in data:
                testcase.executed_by = data['executed_by']
            if 'execution_result' in data:
                testcase.execution_result = data['execution_result']
            if 'version' in data:
                testcase.version = data['version']
            if 'plan_id' in data:
                testcase.plan_id = data['plan_id']
            if 'assignee_id' in data:
                testcase.assignee_id = data['assignee_id']
            
            testcase.updated_at = datetime.now()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': '测试用例更新成功',
                'testcase': {
                    'id': testcase.id,
                    'title': testcase.title,
                    'status': testcase.status,
                    'updated_at': testcase.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"更新TestCase失败: {e}")
            return jsonify({'success': False, 'error': '更新TestCase失败'}), 500
    
    elif request.method == 'DELETE':
        try:
            testcase = TestCase.query.get(testcase_id)
            if not testcase:
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, testcase.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            db.session.delete(testcase)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': '测试用例删除成功'
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"删除TestCase失败: {e}")
            return jsonify({'success': False, 'error': '删除TestCase失败'}), 500

@app.route('/api/plans/<int:plan_id>/testcases', methods=['GET'])
@login_required
def api_get_plan_testcases(plan_id):
    """获取计划下的所有测试用例"""
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        testcases = TestCase.query.filter_by(plan_id=plan_id).all()
        
        testcase_list = []
        for tc in testcases:
            testcase_list.append({
                'id': tc.id,
                'title': tc.title,
                'status': tc.status,
                'case_type': tc.case_type,
                'priority': tc.priority,
                'test_type': tc.test_type,
                'version': tc.version,
                'execution_result': tc.execution_result,
                'created_at': tc.created_at.isoformat(),
                'updated_at': tc.updated_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'testcases': testcase_list
        })
        
    except Exception as e:
        print(f"获取计划TestCase列表失败: {e}")
        return jsonify({'success': False, 'error': '获取TestCase列表失败'}), 500


@app.route('/api/plans/<int:plan_id>/bugs', methods=['GET'])
@login_required
def api_get_plan_bugs(plan_id):
    """获取计划下的所有Bug"""
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        bugs = Bug.query.filter_by(plan_id=plan_id).all()
        
        bug_list = []
        for bug in bugs:
            bug_list.append({
                'id': bug.id,
                'title': bug.title,
                'status': bug.status,
                'priority': bug.priority,
                'severity': bug.severity,
                'created_at': bug.created_at.isoformat() if bug.created_at else None,
                'updated_at': bug.updated_at.isoformat() if bug.updated_at else None
            })
        
        return jsonify({
            'success': True,
            'bugs': bug_list
        })
        
    except Exception as e:
        print(f"获取计划Bug列表失败: {e}")
        return jsonify({'success': False, 'error': '获取Bug列表失败'}), 500

    # ==================== Chat Session API ====================
    
@app.route('/api/projects/<int:project_id>/chat-sessions', methods=['GET'])
@login_required
def api_get_chat_sessions(project_id):
    """获取项目的所有会话"""
    try:
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        sessions = ChatSession.query.filter_by(
            project_id=project_id,
            user_id=current_user.id
        ).order_by(ChatSession.updated_at.desc()).all()
        
        return jsonify({
            'success': True,
            'sessions': [{
                'id': s.id,
                'title': s.title,
                'is_active': s.is_active,
                'memory_enabled': s.memory_enabled,
                'created_at': s.created_at.isoformat(),
                'updated_at': s.updated_at.isoformat()
            } for s in sessions]
        })
        
    except Exception as e:
        print(f"获取会话列表失败: {e}")
        return jsonify({'success': False, 'error': '获取会话列表失败'}), 500
    
@app.route('/api/projects/<int:project_id>/chat-sessions', methods=['POST'])
@login_required
def api_create_chat_session(project_id):
    """创建新会话"""
    try:
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        data = request.get_json()
        title = data.get('title', '新建会话')
        
        session = ChatSession(
            title=title,
            project_id=project_id,
            user_id=current_user.id,
            memory_enabled=data.get('memory_enabled', True)
        )
        
        db.session.add(session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'session': {
                'id': session.id,
                'title': session.title,
                'is_active': session.is_active,
                'memory_enabled': session.memory_enabled,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"创建会话失败: {e}")
        return jsonify({'success': False, 'error': '创建会话失败'}), 500
    
@app.route('/api/chat-sessions/<int:session_id>', methods=['GET'])
@login_required
def api_get_chat_session(session_id):
    """获取会话详情"""
    try:
        session = ChatSession.query.get(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
        
        # 检查权限
        if session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '没有权限访问此会话'}), 403
        
        # 获取消息
        messages = []
        for msg in session.messages:
            messages.append({
                'id': msg.id,
                'is_user': msg.is_user,
                'content': msg.content,
                'understanding': msg.understanding,
                'steps': msg.steps,
                'execution_results': msg.execution_results,
                'agent_result': msg.agent_result,
                'evidences': msg.evidences,
                'navigation': msg.navigation,
                'final_response': msg.final_response,
                'created_at': msg.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'session': {
                'id': session.id,
                'title': session.title,
                'is_active': session.is_active,
                'memory_enabled': session.memory_enabled,
                'memory_data': session.memory_data,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'messages': messages
            }
        })
        
    except Exception as e:
        print(f"获取会话详情失败: {e}")
        return jsonify({'success': False, 'error': '获取会话详情失败'}), 500
    
@app.route('/api/chat-sessions/<int:session_id>', methods=['PUT'])
@login_required
def api_update_chat_session(session_id):
    """更新会话"""
    try:
        session = ChatSession.query.get(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
        
        # 检查权限
        if session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '没有权限修改此会话'}), 403
        
        data = request.get_json()
        if 'title' in data:
            session.title = data['title']
        if 'is_active' in data:
            session.is_active = data['is_active']
        if 'memory_enabled' in data:
            session.memory_enabled = data['memory_enabled']
        if 'memory_data' in data:
            session.memory_data = data['memory_data']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '会话更新成功'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"更新会话失败: {e}")
        return jsonify({'success': False, 'error': '更新会话失败'}), 500

@app.route('/api/chat-sessions/<int:session_id>/generate-title', methods=['POST'])
@login_required
def api_generate_session_title(session_id):
    """根据用户消息生成会话标题"""
    try:
        session = ChatSession.query.get(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
        
        # 检查权限
        if session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '没有权限修改此会话'}), 403
        
        data = request.get_json()
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({'success': False, 'error': '消息内容为空'}), 400
        
        # 调用 LLM 生成简短标题
        from llm.factory import LLMFactory
        llm = LLMFactory.create()
        
        prompt = f"""请根据以下用户消息生成一个简短的会话标题（不超过15个字），直接输出标题，不要加引号或其他符号：

用户消息：{user_message[:200]}

标题："""
        
        title = llm.chat(prompt)
        title = title.strip().strip('"').strip("'")
        
        # 限制标题长度
        if len(title) > 20:
            title = title[:20] + '...'
        
        # 更新会话标题
        session.title = title
        db.session.commit()
        
        return jsonify({
            'success': True,
            'title': title
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"生成会话标题失败: {e}")
        return jsonify({'success': False, 'error': '生成标题失败'}), 500

@app.route('/api/chat-sessions/<int:session_id>', methods=['DELETE'])
@login_required
def api_delete_chat_session(session_id):
    """删除会话"""
    try:
        session = ChatSession.query.get(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
        
        # 检查权限
        if session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '没有权限删除此会话'}), 403
        
        # 删除会话及其所有消息
        ChatMessage.query.filter_by(session_id=session_id).delete()
        db.session.delete(session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '会话删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"删除会话失败: {e}")
        return jsonify({'success': False, 'error': '删除会话失败'}), 500
    
@app.route('/api/chat-sessions/<int:session_id>/messages', methods=['POST'])
@login_required
def api_add_chat_message(session_id):
    """添加消息"""
    try:
        session = db.session.get(ChatSession, session_id)  # ✅ 使用 db.session.get() 替代旧 API
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
            
        # 检查权限
        if session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '没有权限访题此会话'}), 403
            
        data = request.get_json()
            
        message = ChatMessage(
            session_id=session_id,
            user_id=current_user.id if data.get('is_user') else None,
            is_user=data.get('is_user', True),
            content=data.get('content'),
            understanding=data.get('understanding'),
            steps=data.get('steps'),
            execution_results=data.get('execution_results'),
            agent_result=data.get('agent_result'),
            evidences=data.get('evidences'),
            navigation=data.get('navigation'),
            final_response=data.get('final_response')
        )
            
        db.session.add(message)
        session.updated_at = datetime.now(timezone.utc)  # ✅ 使用 timezone.utc 替代 utcnow()
        db.session.commit()
            
        return jsonify({
            'success': True,
            'message_id': message.id,
            'created_at': message.created_at.isoformat()
        })
            
    except Exception as e:
        db.session.rollback()
        print(f"添加消息失败: {e}")
        return jsonify({'success': False, 'error': '添加消息失败'}), 500

if __name__ == '__main__':
    print(generate_password_hash("123456"))

    with app.app_context():
        # 使用新的数据库同步函数
        if sync_database_schema():
            print("数据库初始化成功")
        else:
            print("数据库初始化失败，请检查错误信息")
    
    # 初始化MinIO
    print("正在初始化MinIO...")
    ensure_bucket_exists()
    
    # 初始化Redis
    print("正在初始化Redis...")
    app.redis_client = get_redis_client()
    if app.redis_client:
        print("✅ Redis初始化成功")
    else:
        print("❌ Redis初始化失败，缓存功能将不可用")
    
    app.run(debug=False, port=5000)