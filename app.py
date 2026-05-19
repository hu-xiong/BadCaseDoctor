# Windows 下让控制台用 UTF-8 输出中文/emoji。
# 禁止再用 TextIOWrapper 包一层替换 sys.stdout：Flask debug 重载子进程里原 buffer 可能已关闭，
# 会导致 ValueError: I/O operation on closed file，进而所有 print() 让接口 500。
import sys
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime, timedelta, timezone

# 统一日志：用 logging 代替零散 print，默认带时间戳（便于 PERF_LOG=1 追踪耗时）。
import logging
import datetime as _dt

class _LocalTZFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = _dt.datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="milliseconds")

def _setup_logging():
    perf_on = (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on")
    root = logging.getLogger()
    if root.handlers:
        # 避免重复挂 handler（debug reloader / 多次 import）
        return
    level = logging.INFO if perf_on else logging.WARNING
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        _LocalTZFormatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S.%f",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
    # Flask/Werkzeug 的请求日志也走同一套 handler
    logging.getLogger("werkzeug").setLevel(level)

_setup_logging()
import pandas as pd
import pymysql
from dotenv import load_dotenv
import random
import string
from config import Config
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError
import mimetypes
from sqlalchemy import text, inspect, Enum, or_, Text, and_, event
from sqlalchemy.dialects.mysql import LONGTEXT
from PIL import Image
import io
import time
from collections import defaultdict
import redis
import base64
from urllib.parse import unquote, quote
import subprocess
import threading
import time
import signal
import os
import enum
import hashlib

from routers.chat import chat_bp
from routers.agent import agent_bp
from routers.payment import payment_bp
from routers.sandbox import sandbox_bp
from routers.sandbox_client import sandbox_client_bp
from routers.proposal import proposal_bp
from routers.sql_preview import sql_preview_bp
from routers.summary import summary_bp
from routers.memory import memory_bp
from routers.terminal_api import terminal_bp
from routers.client_scripts import client_scripts_bp
from routers.models import models_bp

# 导入终端日志记录器
from agents.tools.terminal_logger import terminal_logger

# 导入 Prometheus
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

load_dotenv()

from workflow_notify import (
    schedule_workflow_notification,
    build_email_body_cn,
    build_email_subject_cn,
)

# 定义状态枚举
class BugStatus(enum.Enum):
    NEW = 'new'
    REOPENED = 'reopened'
    CLOSED = 'closed'
    RESOLVED = 'resolved'
    HOLD = 'hold'
    NOT_A_BUG = 'not_a_bug'
    NEW_FEATURE = 'new_feature'

class BadCaseStatus(enum.Enum):
    NEW = 'new'
    PENDING = 'pending'
    REOPENED = 'reopened'
    CLOSED = 'closed'
    RESOLVED = 'resolved'
    HOLD = 'hold'
    NOT_BADCASE = 'not_badcase'
    UNPUBLISHED = 'unpublished'  # 兼容遗留数据

class TestCaseStatus(enum.Enum):
    DRAFT = 'draft'        # 草稿
    REVIEW = 'review'      # 评审
    ACTIVE = 'active'      # 生效
    ARCHIVED = 'archived'  # 归档

class CardType(enum.Enum):
    BUG = 'bug'
    BADCASE = 'badcase'
    TESTCASE = 'testcase'
    CARD = 'card'

class ExecutionResult(enum.Enum):
    PASS = 'pass'
    FAIL = 'fail'
    BLOCKED = 'blocked'
    SKIP = 'skip'

class EnumJSONEncoder(json.JSONEncoder):
    """处理 Enum、datetime/date 等不可直接序列化的类型"""
    def default(self, obj):
        if isinstance(obj, enum.Enum):
            return obj.value
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

app = Flask(__name__)
app.json_encoder = EnumJSONEncoder
app.config.from_object(Config)

# Flask应用配置
app.config['SECRET_KEY'] = 'hxReligi12.-badcase-doctor-secret-key-2025'  # 添加SECRET_KEY配置
# Session Cookie 配置：浏览器 /api 请求携带登录态
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 允许同站请求携带 Cookie
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # 开发环境使用 HTTP
# SQLALCHEMY_DATABASE_URI 仅来自 Config / 环境变量 DATABASE_URL，主业务库固定为 MySQL（见下方校验）

# 数据库连接池（默认加大；可用环境变量覆盖，避免多进程×多 worker 撑爆 MySQL max_connections）
try:
    _sql_pool_size = int((os.getenv("SQLALCHEMY_POOL_SIZE") or "1000").strip())
except Exception:
    _sql_pool_size = 1000
try:
    _sql_max_overflow = int((os.getenv("SQLALCHEMY_MAX_OVERFLOW") or "0").strip())
except Exception:
    _sql_max_overflow = 0
_sql_pool_size = max(1, min(_sql_pool_size, 2000))
_sql_max_overflow = max(0, min(_sql_max_overflow, 500))

# PyMySQL 默认不设 connect_timeout 时，远端不可达可能拖到系统级 TCP 超时（Windows 上常见 ~20s 量级）
try:
    _mysql_connect_timeout = int((os.getenv("MYSQL_CONNECT_TIMEOUT") or "10").strip())
except Exception:
    _mysql_connect_timeout = 10
_mysql_connect_timeout = max(1, min(_mysql_connect_timeout, 120))
try:
    _mysql_read_timeout = int((os.getenv("MYSQL_READ_TIMEOUT") or "0").strip())
except Exception:
    _mysql_read_timeout = 0
_mysql_read_timeout = max(0, min(_mysql_read_timeout, 600))

_mysql_connect_args = {"connect_timeout": _mysql_connect_timeout}
if _mysql_read_timeout > 0:
    _mysql_connect_args["read_timeout"] = _mysql_read_timeout
    _mysql_connect_args["write_timeout"] = _mysql_read_timeout

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': _sql_pool_size,
    'pool_timeout': 300,
    'pool_recycle': 3600,
    'max_overflow': _sql_max_overflow,
    'pool_pre_ping': True,
    'echo': False,
    'connect_args': _mysql_connect_args,
}

# 主应用 ORM 仅允许 MySQL（与 config.py 中 DATABASE_URL 一致）；勿使用 sqlite 作为主库
_main_db_uri = str(app.config.get('SQLALCHEMY_DATABASE_URI') or '').strip().lower()
if not _main_db_uri.startswith('mysql'):
    raise RuntimeError(
        '主业务数据库必须使用 MySQL：请在环境变量 DATABASE_URL 中配置 mysql+pymysql://... '
        '（或兼容的 mysql:// 方言）。禁止将主应用 SQLALCHEMY_DATABASE_URI 指向 SQLite。'
        + (f" 当前: {_main_db_uri[:120]}" if _main_db_uri else ' 当前: (未配置)')
    )

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
app.register_blueprint(sandbox_bp)
app.register_blueprint(sandbox_client_bp)
app.register_blueprint(proposal_bp)
app.register_blueprint(sql_preview_bp)
app.register_blueprint(summary_bp)
app.register_blueprint(memory_bp)
app.register_blueprint(terminal_bp)
app.register_blueprint(client_scripts_bp)
app.register_blueprint(models_bp)

# MinIO 配置：与 config.Config 及环境变量一致（见 config.py）
MINIO_CONFIG = {
    'endpoint': Config.MINIO_ENDPOINT,
    'access_key': Config.MINIO_ACCESS_KEY,
    'secret_key': Config.MINIO_SECRET_KEY,
    'bucket_name': Config.MINIO_BUCKET_NAME,
    'saas_file_path': Config.MINIO_SAAS_FILE_PATH,
    'max_file_size': Config.MINIO_MAX_FILE_SIZE,
    'max_sum_file_size': Config.MINIO_MAX_SUM_FILE_SIZE,
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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip', 'rar'}
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

# ==================== Prometheus 指标端点 ====================

@app.route('/metrics', methods=['GET'])
def metrics():
    """
    暴露 Prometheus 指标端点
    使用 curl http://localhost:5000/metrics 查看
    """
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

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
        base_name = original_filename
        if file_extension and original_filename.lower().endswith(f'.{file_extension}'):
            base_name = original_filename[: -(len(file_extension) + 1)]
        
        # 如果是头像上传，添加项目ID到文件名中
        if folder_path == 'avatar':
            # 从请求中获取项目ID（如果有的话）
            project_id = request.args.get('project_id', 'unknown')
            if file_extension:
                safe_filename = f"project_{project_id}_{timestamp}_{base_name}.{file_extension}"
            else:
                safe_filename = f"project_{project_id}_{timestamp}_{base_name}.jpg"
        else:
            if file_extension:
                safe_filename = f"{timestamp}_{base_name}.{file_extension}"
            else:
                safe_filename = f"{timestamp}_{base_name}.jpg"
        
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
        
        # 读入内存一次：上传 MinIO 的同时写入 Redis，富文本插图 GET 可立即命中缓存
        from io import BytesIO
        file.seek(0)
        raw_bytes = file.read()
        file.seek(0)
        client.upload_fileobj(
            BytesIO(raw_bytes),
            MINIO_CONFIG['bucket_name'],
            file_path,
            ExtraArgs=extra_args
        )
        if content_type.startswith('image/') and raw_bytes:
            set_image_to_cache(get_upload_image_cache_key(file_path), raw_bytes, 3600)
        
        # 浏览器侧走同源代理，避免 MinIO 桶私有 / 跨域导致富文本内 img 无法加载
        file_url = build_upload_image_proxy_url(file_path)
        minio_direct_url = f"{MINIO_CONFIG['endpoint']}/{MINIO_CONFIG['bucket_name']}/{file_path}"
        
        print(f"文件上传成功:")
        print(f"  - 文件名: {safe_filename}")
        print(f"  - 文件路径: {file_path}")
        print(f"  - 代理URL: {file_url}")
        print(f"  - MinIO直链: {minio_direct_url}")
        
        return {
            'success': True,
            'url': file_url,
            'filename': safe_filename,
            'path': file_path,
            'minio_url': minio_direct_url,
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


def build_upload_image_proxy_url(file_path: str) -> str:
    """将 MinIO 对象键转为前端可加载的同源图片地址（需登录）。"""
    key = (file_path or '').strip().lstrip('/')
    if not key:
        return ''
    return f"/api/uploads/image/{quote(key, safe='/')}"


def minio_direct_url_to_proxy(url: str) -> str:
    """历史数据中的 MinIO 直链转为代理地址；无法识别则原样返回。"""
    raw = (url or '').strip()
    if not raw or raw.startswith('/api/uploads/image/'):
        return raw
    prefix = f"{MINIO_CONFIG['endpoint'].rstrip('/')}/{MINIO_CONFIG['bucket_name']}/"
    if raw.startswith(prefix):
        return build_upload_image_proxy_url(raw[len(prefix):].split('?')[0])
    bucket_prefix = f"/{MINIO_CONFIG['bucket_name']}/"
    idx = raw.find(bucket_prefix)
    if idx >= 0:
        return build_upload_image_proxy_url(raw[idx + len(bucket_prefix):].split('?')[0])
    return raw


def read_minio_object_bytes(get_object_response):
    """读取 boto3 get_object 结果；兼容 dict(Body=...) 与 StreamingBody。"""
    resp = get_object_response
    if isinstance(resp, dict):
        body = resp.get('Body')
        if body is None:
            raise ValueError('MinIO响应缺少Body字段')
        data = body.read()
        if hasattr(body, 'close'):
            body.close()
        return data
    if hasattr(resp, 'read'):
        data = resp.read()
        if hasattr(resp, 'close'):
            resp.close()
        return data
    raise TypeError(f'不支持的MinIO响应类型: {type(resp)}')


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


def get_upload_image_cache_key(file_path: str) -> str:
    return f"upload_img:{(file_path or '').strip().lstrip('/')}"

db = SQLAlchemy(app)

# 预热数据库连接池：启动时建立 min(50, pool_size) 个连接，避免第一个请求冷启动
try:
    _warmup_size = min(50, app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}).get('pool_size', 100))
    with app.app_context():
        for _ in range(_warmup_size):
            db.session.execute(db.text('SELECT 1'))
        print(f"[DB] 连接池预热完成，已建立 {_warmup_size} 个连接", flush=True)
except Exception as e:
    print(f"[DB] 连接池预热失败: {e}", flush=True)

mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 压缩 JSON 响应（尤其是聊天历史/终端输出这类大 payload）
@app.after_request
def _gzip_large_json_response(resp):
    try:
        if not resp:
            return resp
        from flask import request as _req
        ae = (_req.headers.get('Accept-Encoding') or '').lower()
        if 'gzip' not in ae:
            return resp
        # 仅压缩 JSON；避免对图片/流式等产生副作用
        ctype = (resp.headers.get('Content-Type') or '').lower()
        if 'application/json' not in ctype:
            return resp
        if resp.headers.get('Content-Encoding'):
            return resp
        # 保险：某些响应可能 direct_passthrough=True，get_data 为空/抛异常
        try:
            resp.direct_passthrough = False
        except Exception:
            pass
        data = resp.get_data(as_text=False)
        if not data or len(data) < 2048:
            return resp
        import gzip
        gz = gzip.compress(data, compresslevel=6)
        resp.set_data(gz)
        resp.headers['Content-Encoding'] = 'gzip'
        resp.headers['Content-Length'] = str(len(gz))
        resp.headers['Vary'] = 'Accept-Encoding'
        return resp
    except Exception:
        return resp

# 自定义未授权处理器，让API路由返回JSON错误
@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/'):
        return jsonify({'error': '未登录'}), 401
    return redirect(url_for('login'))

# 终端日志记录端点
@app.route('/api/terminal/log', methods=['POST'])
def log_terminal_output():
    data = request.json
    session_id = data.get('sessionId')
    stdout = data.get('stdout', '')
    stderr = data.get('stderr', '')
    
    if session_id:
        if stdout:
            terminal_logger.log_output(session_id, 'stdout', stdout)
        if stderr:
            terminal_logger.log_output(session_id, 'stderr', stderr)
        return jsonify({"success": True, "message": "日志记录成功"})
    return jsonify({"success": False, "error": "缺少 sessionId"})

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
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    credits = db.Column(db.Integer, default=0)  # 剩余使用次数
    total_purchased = db.Column(db.Integer, default=0)  # 累计购买次数
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaymentHistory(db.Model):
    """支付历史记录"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
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
    user_id = db.Column(db.Integer, nullable=False)

class ProjectPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, collaborator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), default='member')  # leader, member
    permissions = db.Column(db.Text)  # 权限JSON字符串
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 不使用 backref，避免依赖外键


def _json_snowflake_id(value):
    """超过 JS Number.MAX_SAFE_INTEGER 的整型主键/外键：JSON 输出为字符串，避免前端精度丢失。"""
    if value is None:
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return value


def _json_snowflake_ids_in_list(seq):
    """JSON 列中雪花 id 列表（如 related_defects）统一为字符串。"""
    if seq is None:
        return None
    if isinstance(seq, (list, tuple)):
        out = []
        for x in seq:
            if isinstance(x, dict):
                out.append(x)
            else:
                out.append(_json_snowflake_id(x) if x is not None else None)
        return out
    return seq


def _testcase_related_defects_detail_payload(testcase) -> list:
    """测例详情 API：关联缺陷返回 {id, title, plan_id}，供前端展示 Bug 标题而非纯 id。"""
    raw = getattr(testcase, "related_defects", None) or []
    ids = _json_snowflake_ids_in_list(raw)
    if not ids:
        return []
    if not isinstance(ids, list):
        return []
    id_strs = []
    for x in ids:
        if isinstance(x, dict):
            sid = _json_snowflake_id(x.get("id"))
            if sid:
                id_strs.append(str(sid))
        else:
            sid = _json_snowflake_id(x)
            if sid:
                id_strs.append(str(sid))
    if not id_strs:
        return []
    try:
        from app import Bug

        id_ints = [int(x) for x in id_strs]
        rows = (
            Bug.query.filter(
                Bug.project_id == testcase.project_id, Bug.id.in_(id_ints)
            ).all()
        )
        by_id = {}
        for b in rows:
            bid = _json_snowflake_id(b.id)
            if not bid:
                continue
            by_id[str(bid)] = {
                "id": str(bid),
                "title": (b.title or "").strip(),
                "plan_id": _json_snowflake_id(b.plan_id),
            }
        return [by_id.get(bid, {"id": bid, "title": "", "plan_id": None}) for bid in id_strs]
    except Exception as ex:
        print(f"[API] related_defects 标题补全失败: {ex}", flush=True)
        return [{"id": bid, "title": "", "plan_id": None} for bid in id_strs]


def _testcase_comments_detail_payload(test_case_id: int) -> list:
    """测例评论列表（只读展示，按时间升序）。"""
    try:
        rows = (
            db.session.query(TestCaseComment, User.name)
            .outerjoin(User, User.id == TestCaseComment.user_id)
            .filter(TestCaseComment.test_case_id == int(test_case_id))
            .order_by(TestCaseComment.created_at.asc())
            .all()
        )
        out = []
        for c, uname in rows:
            out.append(
                {
                    "id": c.id,
                    "content": c.content,
                    "user_id": c.user_id,
                    "user_name": uname or "",
                    "source_message_id": c.source_message_id,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
            )
        return out
    except Exception as ex:
        print(f"[_testcase_comments_detail_payload] {ex}", flush=True)
        return []


def _comment_author_name(user_id: int) -> str:
    try:
        u = User.query.get(int(user_id))
        if u:
            return (u.name or "").strip()
    except Exception:
        pass
    return ""


def _append_testcase_comment_row(
    testcase,
    content: str,
    user_id: int,
    source_message_id=None,
) -> dict:
    """向测例追加一条评论（不可修改历史评论）。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    row = TestCaseComment(
        test_case_id=int(testcase.id),
        user_id=int(user_id),
        content=text,
        source_message_id=_safe_mysql_int_fk_id(source_message_id),
    )
    db.session.add(row)
    db.session.flush()
    uname = _comment_author_name(user_id)
    return {
        "id": row.id,
        "content": row.content,
        "user_id": row.user_id,
        "user_name": uname,
        "source_message_id": row.source_message_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _append_bug_comment_row(bug, content: str, user_id: int, source_message_id=None) -> dict:
    text = (content or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    row = BugComment(
        bug_id=int(bug.id),
        user_id=int(user_id),
        content=text,
        source_message_id=_safe_mysql_int_fk_id(source_message_id),
    )
    db.session.add(row)
    db.session.flush()
    uname = _comment_author_name(user_id)
    return {
        "id": row.id,
        "content": row.content,
        "user_id": row.user_id,
        "user_name": uname,
        "source_message_id": row.source_message_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _append_badcase_comment_row(badcase, content: str, user_id: int, source_message_id=None) -> dict:
    text = (content or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    row = Comment(
        badcase_id=int(badcase.id),
        user_id=int(user_id),
        content=text,
        source_message_id=_safe_mysql_int_fk_id(source_message_id),
    )
    db.session.add(row)
    db.session.flush()
    uname = _comment_author_name(user_id)
    return {
        "id": row.id,
        "content": row.content,
        "user_id": row.user_id,
        "user_name": uname,
        "source_message_id": row.source_message_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class BadCase(db.Model):
    __tablename__ = 'bad_case'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    project_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.BigInteger)  # 关联计划
    creator_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200))  # BadCase标题
    case_category = db.Column(db.String(100), nullable=False)  # 问题分类
    base_problem = db.Column(db.Text, nullable=False)  # 具体问题
    reproduction_steps = db.Column(db.Text)  # 复现步骤
    badcase_result = db.Column(db.Text, nullable=False)  # badcase问题结果
    answer = db.Column(db.Text, nullable=False)  # 答案（原 correct_answer）
    correct_answer = db.Column(db.Text)  # 正确答案（原 correct_answer_final）
    problem_reason = db.Column(db.Text)  # 问题原因
    needs_processing = db.Column(db.Boolean, default=True)  # 是否需要处理
    solution = db.Column(db.Text)  # 解决方式
    is_verified = db.Column(db.Boolean, default=False)  # 是否验证
    priority = db.Column(db.String(10), default='p3')  # p1, p2, p3
    status = db.Column(Enum(BadCaseStatus, values_callable=lambda obj: [e.value for e in obj]), default=BadCaseStatus.NEW, nullable=False)
    assignee = db.Column(db.String(100))  # 负责人
    plan = db.Column(db.String(100))  # 所属计划（保留字段，用于向后兼容）
    document_type = db.Column(db.String(100))  # 文档类型
    attachments = db.Column(db.Text)  # 附件信息，JSON格式存储
    assigned_users = db.Column(db.Text)  # 指派的人员，JSON格式存储
    card_id = db.Column(db.BigInteger, nullable=True)  # 关联迭代卡片 Card.id（与 Bug.card_id 一致）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    
    def to_dict(self):
        """序列化为字典，处理枚举值"""
        return {
            'id': _json_snowflake_id(self.id),
            'project_id': self.project_id,
            'plan_id': _json_snowflake_id(self.plan_id),
            'creator_id': self.creator_id,
            'title': self.title,
            'case_category': self.case_category,
            'base_problem': self.base_problem,
            'reproduction_steps': self.reproduction_steps,
            'badcase_result': self.badcase_result,
            'answer': self.answer,
            'correct_answer': self.correct_answer,
            'problem_reason': self.problem_reason,
            'needs_processing': self.needs_processing,
            'solution': self.solution,
            'is_verified': self.is_verified,
            'priority': self.priority,
            'status': self.status.value if isinstance(self.status, BadCaseStatus) else self.status,
            'assignee': self.assignee,
            'plan': self.plan,
            'document_type': self.document_type,
            'attachments': self.attachments,
            'assigned_users': self.assigned_users,
            'card_id': _json_snowflake_id(getattr(self, 'card_id', None)),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    badcase_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)  # 富文本内容
    source_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Plan(db.Model):
    __tablename__ = 'plan'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    name = db.Column(db.String(200), nullable=False)  # 计划名称
    description = db.Column(db.Text)  # 计划描述
    status = db.Column(db.String(20), default='active')  # active, archived, completed
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    is_pinned = db.Column(db.Boolean, default=False)  # 是否置顶
    is_default = db.Column(db.Boolean, default=False)  # 是否为默认迭代
    start_date = db.Column(db.Date)  # 开始日期
    end_date = db.Column(db.Date)  # 结束日期
    progress = db.Column(db.Float, default=0.0)  # 进度百分比 0-100
    parent_id = db.Column(db.BigInteger)  # 父计划ID，支持递归
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    assignee_id = db.Column(db.Integer)  # 负责人
    scope_notification = db.Column(db.Boolean, default=False)  # 范围变更通知
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class Bug(db.Model):
    __tablename__ = 'bug'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
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
    # 可为空：与「未计划的 Bug」列表（plan_id IS NULL）一致
    plan_id = db.Column(db.BigInteger, nullable=True)
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    assignee_id = db.Column(db.Integer)  # 负责人
    attachments = db.Column(db.Text)  # 附件信息，JSON格式存储
    card_id = db.Column(db.BigInteger, nullable=True)  # 关联的卡片ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class TestCase(db.Model):
    __tablename__ = 'test_case'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    title = db.Column(db.String(200), nullable=False)  # 用例标题
    status = db.Column(Enum(TestCaseStatus, values_callable=lambda obj: [e.value for e in obj]), default=TestCaseStatus.DRAFT, nullable=False)
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
    executed_by = db.Column(db.Integer)  # 执行人
    execution_result = db.Column(Enum(ExecutionResult, values_callable=lambda obj: [e.value for e in obj]), nullable=True)  # 执行结果：pass/fail/blocked/skip，NULL 表示未执行
    
    # 执行（测试集）
    baseline = db.Column(db.String(100))  # 基线管理
    
    # 工时
    estimated_time = db.Column(db.Float)  # 预估工时（小时）
    actual_time = db.Column(db.Float)  # 实际工时（小时）
    remaining_time = db.Column(db.Float)  # 剩余工时（小时）
    
    # 关联信息
    plan_id = db.Column(db.BigInteger)  # 所属计划
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    assignee_id = db.Column(db.Integer)  # 维护人
    card_id = db.Column(db.BigInteger, nullable=True)  # 关联迭代卡片 Card.id

    # 版本信息
    version = db.Column(db.String(20), default='v1')  # 版本号
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    

    
    def to_dict(self):
        """序列化为字典，处理枚举值"""
        return {
            'id': _json_snowflake_id(self.id),
            'title': self.title,
            'status': self.status.value if isinstance(self.status, TestCaseStatus) else self.status,
            'case_type': self.case_type,
            'priority': self.priority,
            'test_type': self.test_type,
            'preconditions': self.preconditions,
            'steps': self.steps,
            'remark': self.remark,
            'requirement_id': self.requirement_id,
            'related_defects': _json_snowflake_ids_in_list(self.related_defects),
            'last_executed': self.last_executed.isoformat() if self.last_executed else None,
            'executed_by': self.executed_by,
            'execution_result': self.execution_result.value if self.execution_result and isinstance(self.execution_result, ExecutionResult) else self.execution_result,
            'baseline': self.baseline,
            'estimated_time': self.estimated_time,
            'actual_time': self.actual_time,
            'remaining_time': self.remaining_time,
            'plan_id': _json_snowflake_id(self.plan_id),
            'project_id': self.project_id,
            'creator_id': self.creator_id,
            'assignee_id': self.assignee_id,
            'card_id': _json_snowflake_id(getattr(self, 'card_id', None)),
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Card(db.Model):
    """统一的卡片模型，支持Bug、BadCase、TestCase三种类型"""
    __tablename__ = 'card'
    
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(Enum(CardType, values_callable=lambda obj: [e.value for e in obj]), default=CardType.BADCASE, nullable=False)
    priority = db.Column(db.String(10), default='p3')
    assignee_id = db.Column(db.Integer)
    project_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.BigInteger, nullable=True)
    creator_id = db.Column(db.Integer, nullable=True)  # 与 POST /api/cards、to_dict 一致；历史行可为 NULL
    description = db.Column(db.Text)
    
    # Bug特有字段
    severity = db.Column(db.String(20))
    steps_to_reproduce = db.Column(db.Text)
    expected_result = db.Column(db.Text)
    actual_result = db.Column(db.Text)
    bug_type = db.Column(db.String(50))
    environment = db.Column(db.String(100))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    
    # BadCase特有字段
    case_category = db.Column(db.String(100))
    base_problem = db.Column(db.Text)
    reproduction_steps = db.Column(db.Text)
    badcase_result = db.Column(db.Text)
    answer = db.Column(db.Text)
    correct_answer = db.Column(db.Text)
    problem_reason = db.Column(db.Text)
    solution = db.Column(db.Text)
    
    # TestCase特有字段
    case_type_test = db.Column(db.String(50))
    test_type = db.Column(db.String(50))
    preconditions = db.Column(db.Text)
    steps = db.Column(db.JSON)
    remark = db.Column(db.Text)
    requirement_id = db.Column(db.Integer)
    related_defects = db.Column(db.JSON)
    last_executed = db.Column(db.DateTime)
    executed_by = db.Column(db.Integer)
    execution_result = db.Column(Enum(ExecutionResult, values_callable=lambda obj: [e.value for e in obj]))
    baseline = db.Column(db.String(100))
    estimated_time = db.Column(db.Float)
    actual_time = db.Column(db.Float)
    remaining_time = db.Column(db.Float)
    version = db.Column(db.String(20), default='v1')
    
    # 数据迁移追溯字段
    source_type = db.Column(db.String(30), nullable=True)  # 'bug', 'bad_case', 'test_case', NULL表示新创建的卡片
    source_id = db.Column(db.BigInteger, nullable=True)  # 源表中的ID
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    

    
    def to_dict(self):
        """序列化为字典，处理枚举值"""
        # id / plan_id / source_id 可能超过 JS Number.MAX_SAFE_INTEGER，JSON 数字会被截断，必须作字符串返回
        result = {
            'id': _json_snowflake_id(self.id),
            'title': self.title,
            'type': self.type.value if isinstance(self.type, CardType) else self.type,
            'priority': self.priority,
            'assignee_id': self.assignee_id,
            'project_id': self.project_id,
            'creator_id': self.creator_id,
            'plan_id': _json_snowflake_id(self.plan_id),
            'description': self.description,
            'source_type': self.source_type,
            'source_id': _json_snowflake_id(self.source_id),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        # 根据类型添加特定字段
        if self.type == CardType.BUG:
            result.update({
                'severity': self.severity,
                'steps_to_reproduce': self.steps_to_reproduce,
                'expected_result': self.expected_result,
                'actual_result': self.actual_result,
                'bug_type': self.bug_type,
                'environment': self.environment,
                'browser': self.browser,
                'os': self.os
            })
        elif self.type == CardType.BADCASE:
            result.update({
                'case_category': self.case_category,
                'base_problem': self.base_problem,
                'reproduction_steps': self.reproduction_steps,
                'badcase_result': self.badcase_result,
                'answer': self.answer,
                'correct_answer': self.correct_answer,
                'problem_reason': self.problem_reason,
                'solution': self.solution
            })
        elif self.type == CardType.TESTCASE:
            result.update({
                'case_type_test': self.case_type_test,
                'test_type': self.test_type,
                'preconditions': self.preconditions,
                'steps': self.steps,
                'remark': self.remark,
                'requirement_id': self.requirement_id,
                'related_defects': self.related_defects,
                'last_executed': self.last_executed.isoformat() if self.last_executed else None,
                'executed_by': self.executed_by,
                'execution_result': self.execution_result.value if self.execution_result and isinstance(self.execution_result, ExecutionResult) else self.execution_result,
                'baseline': self.baseline,
                'estimated_time': self.estimated_time,
                'actual_time': self.actual_time,
                'remaining_time': self.remaining_time,
                'version': self.version
            })
        
        return result


_ENTITY_SNOWFLAKE_PK_REGISTERED = False


def _register_entity_snowflake_pk_hooks() -> None:
    """Bug / BadCase / TestCase / Card / Plan 主键共用雪花 id（同一序列空间，跨表不撞号）。"""
    global _ENTITY_SNOWFLAKE_PK_REGISTERED
    if _ENTITY_SNOWFLAKE_PK_REGISTERED:
        return
    from utils.snowflake import next_entity_snowflake_id

    def _assign_snowflake_pk(mapper, connection, target) -> None:
        if getattr(target, "id", None) in (None, 0):
            setattr(target, "id", int(next_entity_snowflake_id()))

    for _m in (Bug, BadCase, TestCase, Card, Plan):
        event.listen(_m, "before_insert", _assign_snowflake_pk, propagate=True)
    _ENTITY_SNOWFLAKE_PK_REGISTERED = True


_register_entity_snowflake_pk_hooks()


def _apply_card_type_change_defaults(card: Card, old_type: CardType) -> None:
    """
    行内切换 Card.type（无 Bug/BadCase/TestCase 源表行时）补全新类型常用字段，
    避免 MySQL NOT NULL / 业务必填导致 commit 失败。
    """
    if old_type == card.type:
        return
    new_t = card.type
    if not isinstance(new_t, CardType):
        return
    if new_t == CardType.BUG:
        if not (getattr(card, 'severity', None) or '').strip():
            card.severity = 'medium'
        if not (getattr(card, 'bug_type', None) or '').strip():
            card.bug_type = '其他'
    elif new_t == CardType.BADCASE:
        if not (getattr(card, 'case_category', None) or '').strip():
            card.case_category = '未分类'
        if not (getattr(card, 'base_problem', None) or '').strip():
            card.base_problem = (card.title or '').strip() or '（待补充）'
        if not (getattr(card, 'badcase_result', None) or '').strip():
            card.badcase_result = '（待补充）'
        if not (getattr(card, 'answer', None) or '').strip():
            card.answer = '（待补充）'
    elif new_t == CardType.TESTCASE:
        if not (getattr(card, 'version', None) or '').strip():
            card.version = 'v1'
        if not (getattr(card, 'case_type_test', None) or '').strip():
            card.case_type_test = '功能测试'
        if not (getattr(card, 'test_type', None) or '').strip():
            card.test_type = '手动'


def repair_card_source_link_if_missing(card) -> bool:
    """
    数据补全：源表行已用 card_id 指向本卡，但 Card.source_type/source_id 为空时反填。
    支持 Bug / BadCase / TestCase 卡片（与 Card.type 一致）；幂等；成功则 commit。
    """
    if card is None:
        return False
    try:
        st = (getattr(card, "source_type", None) or "").strip()
        sid = getattr(card, "source_id", None)
    except Exception:
        return False
    if (st or "").strip() and sid is not None:
        return False
    ctype = getattr(card, "type", None)
    pid = getattr(card, "project_id", None)
    if pid is None:
        return False
    try:
        cid = int(card.id)
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    src_type_val = None
    src_id_val = None

    if ctype == CardType.BUG:
        row = Bug.query.filter(Bug.card_id == cid, Bug.project_id == pid).first()
        if row is not None:
            src_type_val, src_id_val = "bug", int(row.id)
    elif ctype == CardType.BADCASE:
        row = BadCase.query.filter(BadCase.card_id == cid, BadCase.project_id == pid).first()
        if row is not None:
            src_type_val, src_id_val = "badcase", int(row.id)
    elif ctype == CardType.TESTCASE:
        row = TestCase.query.filter(TestCase.card_id == cid, TestCase.project_id == pid).first()
        if row is not None:
            src_type_val, src_id_val = "testcase", int(row.id)
    else:
        return False

    if not src_type_val or src_id_val is None or int(src_id_val) <= 0:
        return False
    try:
        card.source_type = src_type_val
        card.source_id = int(src_id_val)
        db.session.add(card)
        db.session.commit()
        print(
            f"[Card] repair_card_source_link: card.id={cid} project={pid} -> "
            f"{src_type_val}.id={src_id_val}",
            flush=True,
        )
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[Card] repair_card_source_link 失败: {e}", flush=True)
        return False


# 兼容旧调用名
repair_card_bug_source_if_missing = repair_card_source_link_if_missing


def _find_card_linking_source_record(project_id, source_id, entity_kind, prefer_plan_id=None):
    """
    源表 card_id 为空时，用 Card.source_id 反查看板卡片（迁移/历史数据常见）。
    entity_kind: 'bug' | 'badcase' | 'testcase'
    """
    if project_id is None or source_id is None:
        return None
    try:
        pid = int(project_id)
        sid = int(source_id)
    except (TypeError, ValueError):
        return None
    if pid <= 0 or sid <= 0:
        return None
    ek = str(entity_kind or '').strip().lower()
    st_expect = {
        'bug': {'bug'},
        'badcase': {'bad_case', 'badcase'},
        'testcase': {'test_case', 'testcase'},
    }.get(ek, set())
    ctype_expect = {
        'bug': CardType.BUG,
        'badcase': CardType.BADCASE,
        'testcase': CardType.TESTCASE,
    }.get(ek)

    rows = (
        Card.query.filter(Card.project_id == pid, Card.source_id == sid)
        .order_by(Card.id.desc())
        .all()
    )
    if not rows:
        return None

    def _norm_st(val):
        return str(val or '').strip().lower().replace('-', '_')

    if prefer_plan_id is not None:
        try:
            pp = int(prefer_plan_id)
            for c in rows:
                cp = getattr(c, 'plan_id', None)
                if cp is not None and int(cp) == pp:
                    return c
        except (TypeError, ValueError):
            pass

    for c in rows:
        st = _norm_st(getattr(c, 'source_type', None))
        if st in st_expect:
            return c
    if ctype_expect is not None:
        for c in rows:
            if getattr(c, 'type', None) == ctype_expect:
                return c
    return rows[0] if len(rows) == 1 else None


def _try_repair_badcase_card_id_from_source_card(bc):
    """若 bad_case.card_id 为空但 Card 已挂 source_id，则写回 ORM。返回是否修改（调用方 commit）。"""
    if bc is None:
        return False
    cid = getattr(bc, 'card_id', None)
    try:
        if cid is not None and int(cid) > 0:
            return False
    except (TypeError, ValueError):
        pass
    card = _find_card_linking_source_record(
        bc.project_id, bc.id, 'badcase', prefer_plan_id=getattr(bc, 'plan_id', None)
    )
    if card is None:
        return False
    try:
        bc.card_id = int(card.id)
        return True
    except (TypeError, ValueError):
        return False


def _badcase_assignee_id_for_card(badcase):
    """BadCase.assignee 常为 user id 字符串，转为 Card.assignee_id。"""
    av = getattr(badcase, 'assignee', None)
    if av is not None and str(av).strip().isdigit():
        try:
            return int(str(av).strip())
        except (TypeError, ValueError):
            pass
    return None


def _link_card_source_to_badcase(card, badcase):
    """已有 Card 行时补写 source_type/source_id（创建自卡片 Tab 时常见）。"""
    if card is None or badcase is None:
        return False
    changed = False
    try:
        bid = int(badcase.id)
    except (TypeError, ValueError):
        return False
    st = (getattr(card, 'source_type', None) or '').strip()
    sid = getattr(card, 'source_id', None)
    if not st or sid is None:
        card.source_type = 'badcase'
        card.source_id = bid
        changed = True
    elif int(sid) != bid:
        print(
            f"[BadCase] Card id={card.id} 已关联 source_id={sid}，"
            f"跳过绑定 badcase id={bid}",
            flush=True,
        )
    return changed


def ensure_badcase_card_link(badcase, auto_create=False, commit=True):
    """
    确保 BadCase 与 Card 双向关联，返回 card_id 或 None。
    auto_create=True 时若无任何关联则新建 Card（与 api_create_bug 一致；仅用于创建 API，
    勿在 modify 预览/取数路径开启，否则会改写 card_id 导致从原卡片 Tab 消失）。
    """
    if badcase is None:
        return None
    cid_raw = getattr(badcase, 'card_id', None)
    try:
        if cid_raw is not None and int(cid_raw) > 0:
            card = Card.query.get(int(cid_raw))
            if card is not None:
                if _link_card_source_to_badcase(card, badcase):
                    db.session.add(card)
                    if commit:
                        db.session.commit()
                return int(cid_raw)
    except (TypeError, ValueError):
        pass

    if _try_repair_badcase_card_id_from_source_card(badcase):
        if commit:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[BadCase] card_id 反查补写 commit 失败: {e}", flush=True)
                return None
        try:
            return int(badcase.card_id)
        except (TypeError, ValueError):
            pass

    if not auto_create:
        return None

    # 避免重复建卡：同计划下已有同标题、未挂 source 的 BadCase 卡片则复用
    try:
        pid = int(badcase.project_id)
        pp = getattr(badcase, 'plan_id', None)
        title_key = (badcase.title or '').strip()
        orphan_q = Card.query.filter(
            Card.project_id == pid,
            Card.type == CardType.BADCASE,
            or_(Card.source_id.is_(None), Card.source_id == 0),
        )
        if pp is not None:
            try:
                orphan_q = orphan_q.filter(Card.plan_id == int(pp))
            except (TypeError, ValueError):
                pass
        if title_key:
            orphan_q = orphan_q.filter(Card.title == title_key)
        orphan = orphan_q.order_by(Card.id.desc()).first()
        if orphan is not None:
            badcase.card_id = int(orphan.id)
            if _link_card_source_to_badcase(orphan, badcase):
                db.session.add(orphan)
            if commit:
                db.session.commit()
            print(
                f"[BadCase] 复用已有 Card id={orphan.id} 绑定 badcase id={badcase.id}",
                flush=True,
            )
            return int(orphan.id)
    except Exception as e:
        print(f"[BadCase] 复用 Card 失败: {e}", flush=True)

    try:
        _card = Card(
            title=badcase.title or '',
            type=CardType.BADCASE,
            priority=badcase.priority or 'p3',
            assignee_id=_badcase_assignee_id_for_card(badcase),
            project_id=badcase.project_id,
            creator_id=badcase.creator_id,
            plan_id=badcase.plan_id,
            description=badcase.base_problem,
            case_category=badcase.case_category,
            base_problem=badcase.base_problem,
            reproduction_steps=badcase.reproduction_steps,
            badcase_result=badcase.badcase_result,
            answer=badcase.answer,
            correct_answer=badcase.correct_answer,
            problem_reason=badcase.problem_reason,
            solution=badcase.solution,
            source_type='badcase',
            source_id=int(badcase.id),
        )
        db.session.add(_card)
        if commit:
            db.session.commit()
            db.session.refresh(_card)
        else:
            db.session.flush()
        badcase.card_id = int(_card.id)
        if commit:
            db.session.commit()
            db.session.refresh(badcase)
        print(
            f"[BadCase] 已为 id={badcase.id} 自动创建 Card id={_card.id}",
            flush=True,
        )
        return int(_card.id)
    except Exception as e:
        db.session.rollback()
        print(f"[BadCase] 自动创建 Card 失败 id={getattr(badcase, 'id', None)}: {e}", flush=True)
        return None


class CardTypeDefinition(db.Model):
    """卡片类型定义表 - 支持自定义卡片类型扩展"""
    __tablename__ = 'card_type'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(50), nullable=False)  # 类型名称
    code = db.Column(db.String(30), nullable=False, unique=True)  # 类型代码 (bug, badcase, testcase, 或自定义)
    icon = db.Column(db.String(50))  # 图标
    color = db.Column(db.String(20))  # 颜色
    description = db.Column(db.Text)  # 描述
    
    # 字段配置 (JSON格式，定义该类型支持的字段)
    fields_config = db.Column(db.JSON)  # {'severity': {'type': 'select', 'options': [...]}, ...}
    
    # 状态配置 (JSON格式，定义该类型的可用状态)
    status_config = db.Column(db.JSON)  # ['open', 'in_progress', 'resolved', 'closed']
    
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    sort_order = db.Column(db.Integer, default=0)  # 排序
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    

    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'code': self.code,
            'icon': self.icon,
            'color': self.color,
            'description': self.description,
            'fields_config': self.fields_config,
            'status_config': self.status_config,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class CardPlanRelation(db.Model):
    """卡片与计划的关联关系表 - 支持卡片在多个计划之间移动"""
    __tablename__ = 'card_plan_relation'
    
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, nullable=False)  # 对应 Card.id；与 __table_args__ / to_dict 一致
    plan_id = db.Column(db.BigInteger, nullable=False)
    
    # 关联关系类型
    relation_type = db.Column(db.String(20), default='primary')  # primary(主要), related(关联), blocked_by(被阻塞)
    
    # 在计划中的状态
    status_in_plan = db.Column(db.String(20))  # 该卡片在该计划中的状态
    
    # 添加时间
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)  # 移除时间 (软删除)
    
    # 排序
    sort_order = db.Column(db.Integer, default=0)
    

    
    # 复合唯一索引
    __table_args__ = (
        db.UniqueConstraint('card_id', 'plan_id', 'relation_type', name='uix_card_plan_type'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'card_id': _json_snowflake_id(self.card_id),
            'plan_id': _json_snowflake_id(self.plan_id),
            'relation_type': self.relation_type,
            'status_in_plan': self.status_in_plan,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'sort_order': self.sort_order
        }


class ProposalStatus(enum.Enum):
    """提案状态"""
    PENDING = 'pending'          # 待审核
    APPROVED = 'approved'        # 已审核通过，待执行
    APPLIED = 'applied'          # 已执行
    REJECTED = 'rejected'        # 已拒绝
    ROLLED_BACK = 'rolled_back'  # 标记为回滚
    CONFLICT = 'conflict'        # 与当前数据冲突


class Proposal(db.Model):
    """Text2SQL 修改提案元数据"""
    __tablename__ = 'proposal'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)

    # 多租户标识，对应沙箱中的 tenant_id（如 default / p{project_id}）
    tenant_id = db.Column(db.String(64), nullable=False, index=True)

    # 目标表：目前支持 'bug' / 'bad_case' / 'test_case'
    target_table = db.Column(db.String(64), nullable=False)

    # 给人看的摘要
    summary = db.Column(db.String(255), nullable=False)

    # 待执行的 SQL（UPDATE / DELETE），生成提案时不会直接执行
    sql_text = db.Column(db.Text, nullable=False)

    # 预估影响行数（生成提案时根据快照 rows 长度/COUNT 得出）
    affected_rows_estimate = db.Column(db.Integer)

    # 状态机
    status = db.Column(Enum(ProposalStatus, values_callable=lambda obj: [e.value for e in obj]),
                       default=ProposalStatus.PENDING,
                       nullable=False,
                       index=True)
    has_conflict = db.Column(db.Boolean, default=False)

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime)
    applied_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)
    rolled_back_at = db.Column(db.DateTime)

    # 额外元数据，例如生成时使用的模型、提示词摘要等
    meta = db.Column(db.JSON)




class ProposalSnapshot(db.Model):
    """提案快照：记录修改前的行数据，用于精确 diff 与并发控制"""
    __tablename__ = 'proposal_snapshot'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proposal_id = db.Column(db.Integer,
                            nullable=False, index=True)

    tenant_id = db.Column(db.String(64), nullable=False, index=True)
    target_table = db.Column(db.String(64), nullable=False)

    # 被修改行的主键值（默认使用 id 列）
    row_id = db.Column(db.Integer, nullable=False, index=True)

    # 修改前整行数据（字段 -> 值），使用 JSON 存储
    before_data = db.Column(db.JSON, nullable=False)

    # 乐观锁字段：记录快照时行的 updated_at，用于 apply 前冲突检查
    row_updated_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)



class ChatSession(db.Model):
    __tablename__ = 'chat_session'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    project_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    memory_enabled = db.Column(db.Boolean, default=True)
    memory_data = db.Column(db.Text)  # JSON格式存储
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    


class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer)
    is_user = db.Column(db.Boolean, default=True)
    content = db.Column(db.Text)
    understanding = db.Column(db.Text)
    reasoning = db.Column(db.Text)  # 思考过程（推理内容）
    steps = db.Column(db.Text)  # JSON格式存储
    execution_results = db.Column(db.Text)  # JSON格式存储executionResults
    agent_result = db.Column(db.Text)  # JSON格式存储agentResult
    evidences = db.Column(db.Text)  # JSON格式存储evidences
    navigation = db.Column(db.Text)  # JSON格式存储navigation（点击跳转Bug）
    modify_navigation = db.Column(db.Text)  # JSON格式存储modifyNavigation（修改预览导航）
    modify_groups = db.Column(db.Text)  # JSON格式存储modifyGroups（分组修改预览）
    delete_navigation = db.Column(db.Text)  # JSON：delete 工具 confirm=false 预览（与前端 deleteNavigation 对齐）
    final_response = db.Column(db.Text)
    # 本条消息发起请求时选用的模型 id（用户消息=所选模型；助手消息=生成该条回复的请求模型，便于排查效果问题）
    llm_model = db.Column(db.String(128))
    # 用户消息附图：JSON 字符串，项为 { data: dataURL|base64, filename? }；MySQL 用 LONGTEXT 避免单图超 TEXT 64KB
    images = db.Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 不使用 backref，避免依赖外键


class DiffReviewState(db.Model):
    """主表仅保留 pending；采纳/拒绝后在业务路径上物理删除，避免膨胀与状态双写"""
    __tablename__ = 'diff_review_state'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    target = db.Column(db.String(32), nullable=False, index=True)  # badcase/bug/testcase
    target_id = db.Column(db.BigInteger, nullable=False, index=True)
    plan_id = db.Column(db.BigInteger, nullable=True, index=True)
    lifecycle_id = db.Column(db.Integer, default=1, nullable=False)
    diff_fingerprint = db.Column(db.String(64), nullable=False, default='')
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    diff_payload = db.Column(db.Text, nullable=True)  # JSON string
    modifications_payload = db.Column(db.Text, nullable=True)  # JSON string
    source_message_id = db.Column(db.Integer, nullable=True)
    source_session_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    adopted_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    # 待采纳/待拒绝 Diff 的操作者：仅该用户可见 pending 与可执行采纳/拒绝（NULL 为历史数据兼容）
    operator_id = db.Column(db.Integer, nullable=True, index=True)

    # 不使用 backref，避免依赖外键

class BugComment(db.Model):
    __tablename__ = 'bug_comment'
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)  # 富文本内容
    source_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TestCaseComment(db.Model):
    __tablename__ = 'test_case_comment'
    id = db.Column(db.Integer, primary_key=True)
    test_case_id = db.Column(db.BigInteger, nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    source_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PromptTemplate(db.Model):
    __tablename__ = 'prompt_template'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AgentTask(db.Model):
    """ReAct 工具调用的持久化任务单元，支持 DAG 依赖与恢复（见 docs/需求文档_Agent任务状态管理与DAG并发调度_MySQL.md）。"""
    __tablename__ = 'agent_tasks'

    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    params = db.Column(db.JSON, nullable=True)
    result = db.Column(db.JSON, nullable=True)
    error = db.Column(db.Text, nullable=True)
    dependencies = db.Column(db.JSON, nullable=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)


class TerminalAudit(db.Model):
    """嵌入式终端审计：会话开始、AI 建议等（不含逐键记录）。"""
    __tablename__ = 'terminal_audit'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    event_type = db.Column(db.String(40), nullable=False)
    client_session_id = db.Column(db.String(64), nullable=True, index=True)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class QuickCommand(db.Model):
    """用户快速命令：云端同步，支持多项目。"""
    __tablename__ = 'quick_command'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    command = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkflowInAppNotification(db.Model):
    """站内工作流通知：与邮件/CLI 同源 payload 落库，供用户检索。"""
    __tablename__ = 'workflow_in_app_notification'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    actor_id = db.Column(db.Integer, nullable=True)
    actor_name = db.Column(db.String(120), nullable=True)
    event = db.Column(db.String(40), nullable=False)
    entity_type = db.Column(db.String(20), nullable=False, index=True)
    entity_id = db.Column(db.BigInteger, nullable=False, index=True)
    title = db.Column(db.String(500), nullable=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    project_name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(64), nullable=True)
    previous_status = db.Column(db.String(64), nullable=True)
    search_blob = db.Column(db.Text, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


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


def _badcase_status_str(badcase):
    s = getattr(badcase, "status", None)
    if s is None:
        return ""
    return s.value if hasattr(s, "value") else str(s)


def _try_repair_badcase_plan_id_from_legacy_plan_string(badcase):
    """plan_id 为空但 plan 列是纯数字计划 id 时写回 plan_id（旧数据或异常 PUT 体）。"""
    if badcase.plan_id is not None:
        return False
    raw = getattr(badcase, "plan", None)
    if raw is None:
        return False
    s = str(raw).strip()
    if not s.isdigit():
        return False
    try:
        pid = int(s)
        if pid <= 0:
            return False
    except ValueError:
        return False
    row = Plan.query.get(pid)
    if not row or row.project_id != badcase.project_id:
        return False
    badcase.plan_id = pid
    return True


def _testcase_status_str(testcase):
    s = getattr(testcase, "status", None)
    if s is None:
        return ""
    return s.value if hasattr(s, "value") else str(s)


def _workflow_recipients_from_user_ids(user_ids):
    ids = []
    for x in user_ids or []:
        if x is None:
            continue
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list({i for i in ids if i > 0})
    if not ids:
        return []
    rows = db.session.query(User.id, User.email, User.name).filter(User.id.in_(ids)).all()
    return [{"user_id": r.id, "email": r.email, "name": r.name} for r in rows]


def _workflow_recipients_badcase(badcase):
    raw = getattr(badcase, "assignee", None)
    if not raw:
        return []
    s = str(raw).strip()
    if not s:
        return []
    ids = []
    try:
        if "," in s:
            for p in s.split(","):
                p = p.strip()
                if p:
                    ids.append(int(p))
        else:
            ids.append(int(s))
    except (ValueError, TypeError):
        return []
    return _workflow_recipients_from_user_ids(ids)


def _workflow_recipients_bug(bug):
    if getattr(bug, "assignee_id", None):
        return _workflow_recipients_from_user_ids([bug.assignee_id])
    return []


def _workflow_recipients_testcase(tc):
    if getattr(tc, "assignee_id", None):
        return _workflow_recipients_from_user_ids([tc.assignee_id])
    return []


def _workflow_merge_creator_if_empty(recipients, creator_id):
    if recipients:
        return recipients
    if creator_id:
        return _workflow_recipients_from_user_ids([creator_id])
    return []


def _workflow_project_name(project_id):
    p = Project.query.get(project_id)
    return p.name if p else str(project_id)


def _persist_workflow_inapp_rows(payload):
    """每位收件人一条站内通知；独立 commit，失败不影响邮件/CLI 异步发送。"""
    recs = payload.get("recipients") or []
    if not recs:
        return
    parts = [
        payload.get("event"),
        payload.get("entity_type"),
        payload.get("entity_id"),
        payload.get("title"),
        payload.get("project_name"),
        payload.get("status"),
        payload.get("previous_status"),
        payload.get("actor_name"),
    ]
    search_blob = " ".join(str(p) for p in parts if p is not None and str(p) != "")
    rows = []
    for r in recs:
        uid = r.get("user_id")
        if uid is None:
            continue
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        if uid <= 0:
            continue
        rows.append(
            WorkflowInAppNotification(
                user_id=uid,
                actor_id=payload.get("actor_id"),
                actor_name=(payload.get("actor_name") or "")[:120] or None,
                event=str(payload.get("event") or "")[:40],
                entity_type=str(payload.get("entity_type") or "")[:20],
                entity_id=int(payload.get("entity_id") or 0),
                title=(payload.get("title") or "")[:500] or None,
                project_id=payload.get("project_id"),
                project_name=(payload.get("project_name") or "")[:200] or None,
                status=(str(payload.get("status"))[:64] if payload.get("status") is not None else None),
                previous_status=(
                    str(payload.get("previous_status"))[:64]
                    if payload.get("previous_status") is not None
                    else None
                ),
                search_blob=search_blob[:65000] if search_blob else None,
            )
        )
    if not rows:
        return
    db.session.add_all(rows)
    db.session.commit()


def _schedule_workflow_notify(
    event,
    entity_type,
    entity_id,
    title,
    project_id,
    project_name,
    status,
    previous_status,
    recipients,
    *,
    actor_id,
    actor_name,
):
    """异步：站内通知落库 + 飞书/钉钉 CLI + 邮件；无收件人则跳过。

    站内通知落库若在请求线程中 commit，会明显拉长接口耗时，因此这里统一后台化。
    actor / project_name 须在请求线程内传入（避免后台线程再查 DB）。
    """
    if not recipients:
        return
    payload = {
        "event": event,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title or "",
        "status": status,
        "previous_status": previous_status,
        "project_id": project_id,
        "project_name": project_name or str(project_id),
        "actor_id": actor_id,
        "actor_name": actor_name,
        "recipients": recipients,
    }
    payload["email_subject"] = build_email_subject_cn(payload)
    payload["email_body"] = build_email_body_cn(payload)

    # 站内通知落库：后台线程，避免阻塞 HTTP 请求
    try:
        from flask import current_app
        import threading

        app_obj = current_app._get_current_object()

        def _persist_job():
            try:
                with app_obj.app_context():
                    _persist_workflow_inapp_rows(payload)
            except Exception as _pe:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[workflow_notify] 站内通知落库失败: {_pe}")

        threading.Thread(target=_persist_job, daemon=True).start()
    except Exception as _e:
        print(f"[workflow_notify] 站内通知异步调度失败: {_e}")

    # 外部通知（CLI/邮件）本身已异步
    schedule_workflow_notification(payload, send_email_fn=send_email)


# 生成验证码
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def _model_for_user_collaborator_access(model_cls, entity_id: int, user_id: int):
    """
    单次 SQL：实体 + 项目 owner + 当前用户 ProjectPermission，
    与 has_project_permission(user_id, project_id, 'collaborator') 一致。
    返回 (instance|None, err)，err 为 None | 'not_found' | 'forbidden'。
    """
    row = (
        db.session.query(model_cls, Project.user_id, ProjectPermission.role)
        .join(Project, Project.id == model_cls.project_id)
        .outerjoin(
            ProjectPermission,
            and_(ProjectPermission.project_id == Project.id, ProjectPermission.user_id == user_id),
        )
        .filter(model_cls.id == entity_id)
        .first()
    )
    if not row:
        return None, 'not_found'
    entity, owner_id, role = row
    allowed = owner_id == user_id or (role in ('admin', 'collaborator'))
    if not allowed:
        return None, 'forbidden'
    return entity, None


def _project_for_user_collaborator_access(project_id: int, user_id: int):
    """
    编辑上下文等：一次 SQL 取 Project + 当前用户 ProjectPermission。
    与历史 edit-context 一致：负责人任意；非负责人只要在 project_permission 有记录即可访问。
    返回 (project|None, err)，err 为 None | 'not_found' | 'forbidden'。
    """
    row = (
        db.session.query(Project, ProjectPermission.role)
        .outerjoin(
            ProjectPermission,
            and_(ProjectPermission.project_id == Project.id, ProjectPermission.user_id == user_id),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not row:
        return None, 'not_found'
    project, role = row
    # 与历史 edit-context 一致：负责人任意；非负责人只要有权限表记录即可（不按 role 细筛）
    allowed = project.user_id == user_id or role is not None
    if not allowed:
        return None, 'forbidden'
    return project, None


# 检查用户是否有项目权限
def has_project_permission(user_id, project_id, required_role='collaborator'):
    """
    权限检查带 2 秒缓存，同一用户对同一项目的权限在短时间内不会变。
    """
    # 先检查缓存
    cache_key = (user_id, project_id, required_role)
    cache_hit, cached = _cache_get(('perm',) + cache_key, ttl_s=2.0)
    if cache_hit:
        if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
            print(f"[PERF] has_project_permission(project_id={project_id}, user_id={user_id}) cache_hit", flush=True)
        return cached
    
    # 尽量只做 1 次查询：同时拿到 owner_id + 当前用户在该项目的权限 role
    t0 = time.perf_counter()
    row = (
        db.session.query(Project.user_id, ProjectPermission.role)
        .outerjoin(
            ProjectPermission,
            and_(ProjectPermission.project_id == Project.id, ProjectPermission.user_id == user_id),
        )
        .filter(Project.id == project_id)
        .first()
    )
    dt_ms = (time.perf_counter() - t0) * 1000
    if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
        print(
            f"[PERF] has_project_permission(project_id={project_id}, user_id={user_id}, required_role={required_role}) db={dt_ms:.1f}ms",
            flush=True,
        )
    if not row:
        _cache_set(('perm',) + cache_key, False)
        return False
    owner_id, role = row
    result = True if owner_id == user_id else (role in (['admin', 'collaborator'] if required_role != 'admin' else ['admin']))
    _cache_set(('perm',) + cache_key, result)
    return result


# 轻量缓存：降低同页重复请求的耗时（plans/members 变更不频繁，短 TTL 足够）
_PROJECT_CTX_CACHE = {}

def _cache_get(key, ttl_s: float):
    """返回 (hit: bool, value: any)"""
    try:
        entry = _PROJECT_CTX_CACHE.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if (time.time() - ts) <= ttl_s:
            return True, value
        # 已过期，删除并返回 miss
        _PROJECT_CTX_CACHE.pop(key, None)
        return False, None
    except Exception:
        return False, None

def _cache_set(key, value):
    _PROJECT_CTX_CACHE[key] = (time.time(), value)


def _cache_invalidate_plans(project_id: int):
    """测试用例/Bug/BadCase 变更后使计划列表缓存失效（内存 + Redis 双清）"""
    to_del = [k for k in _PROJECT_CTX_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[0] == 'plans' and k[1] == project_id]
    for k in to_del:
        _PROJECT_CTX_CACHE.pop(k, None)
    # 同步清除 Redis 中该项目的所有相关缓存
    _redis_cache_invalidate_project(project_id)


def _cache_invalidate_cards(project_id: int):
    """卡片列表短缓存失效；避免返回旧 JSON（含错误 number id）。"""
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return
    to_del = [
        k
        for k in list(_PROJECT_CTX_CACHE.keys())
        if isinstance(k, tuple) and len(k) >= 2 and k[0] == 'cards' and k[1] == pid
    ]
    for k in to_del:
        _PROJECT_CTX_CACHE.pop(k, None)


def _parse_query_optional_int64(arg_name: str):
    """从 request.args 解析可选雪花 id（查询串用字符串，避免依赖 type=int）。"""
    raw = request.args.get(arg_name)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        v = int(str(raw).strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_query_int_optional(arg_name: str):
    """读取 query 中的整数（含 0）；缺失为 None。用于 plan_id=0 表示未计划等。"""
    raw = request.args.get(arg_name)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _coerce_optional_bigint_json(val):
    """请求 JSON 中的可选雪花 id，写入 ORM BigInteger 列。"""
    if val is None or val == '':
        return None
    try:
        v = int(str(val).strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


# ==================== Redis 缓存层 ====================
# 对 projects / plans / members / edit-context 等高频只读接口做 Redis 缓存，
# 写操作时主动失效；projects 列表另见进程内短缓存 api_projects。

import json as _json

REDIS_CACHE_PREFIX = 'bcd:cache:'

def _redis_cache_get(key: str):
    """从 Redis 获取缓存，返回 (hit: bool, value: any)"""
    try:
        rc = get_redis_client()
        if rc is None:
            return False, None
        raw = rc.get(REDIS_CACHE_PREFIX + key)
        if raw is None:
            return False, None
        return True, _json.loads(raw)
    except Exception:
        return False, None


def _redis_cache_set(key: str, value, ttl_s: int = 10):
    """写入 Redis 缓存，默认 10 秒过期"""
    try:
        rc = get_redis_client()
        if rc is None:
            return
        rc.setex(REDIS_CACHE_PREFIX + key, ttl_s, _json.dumps(value, ensure_ascii=False))
    except Exception:
        pass


def _redis_cache_delete(key: str):
    """删除单条 Redis 缓存"""
    try:
        rc = get_redis_client()
        if rc is None:
            return
        rc.delete(REDIS_CACHE_PREFIX + key)
    except Exception:
        pass


def _redis_cache_invalidate_project(project_id: int):
    """项目数据变更时，清除该项目相关的所有 Redis 缓存（plans/members/edit-context/cards）"""
    for suffix in ('plans', 'members', 'edit-context', 'cards'):
        _redis_cache_delete(f'{suffix}:{project_id}')


def _redis_cache_invalidate_projects(user_id: int):
    """项目列表变更时，清除 /api/projects 的 Redis 与进程内缓存"""
    _redis_cache_delete(f'projects:{user_id}')
    try:
        _PROJECT_CTX_CACHE.pop(('api_projects', user_id), None)
    except Exception:
        pass


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
            'badcases': [{'id': b.id} for b in BadCase.query.filter_by(project_id=p.id).limit(100).all()]
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
            answer=request.form['answer'],
            correct_answer=request.form.get('correct_answer', ''),
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
    
    # 获取项目成员（避免 N+1：一次 JOIN 查询）
    from sqlalchemy.orm import joinedload
    permissions = (
        db.session.query(ProjectPermission)
        .join(User, User.id == ProjectPermission.user_id)
        .filter(ProjectPermission.project_id == badcase.project_id)
        .add_columns(User.id, User.name, User.email)
        .all()
    )
    project_members = [
        {'id': uid, 'name': uname, 'email': uemail, 'role': perm.role}
        for perm, uid, uname, uemail in permissions
    ]
    
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
                        answer=row.get('answer', row.get('correct_answer', '')),
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
                    answer=row.get('answer', row.get('correct_answer', '')),
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


def _normalize_diff_target(target):
    t = (target or '').strip().lower().replace('-', '_')
    if t == 'test_case':
        return 'testcase'
    if t in ('bug', 'badcase', 'testcase'):
        return t
    return t or 'badcase'


def _collect_badcases_for_badcase_card(card):
    """
    与某张 BadCase 类型看板卡片关联的全部 BadCase：
    - bad_case.card_id 指向该卡片；
    - 或卡片 source 指向某条 BadCase（与 card_id 互补的历史数据）。
    """
    if card is None:
        return []
    pid = getattr(card, 'project_id', None)
    cid = getattr(card, 'id', None)
    if pid is None or cid is None:
        return []
    try:
        pid = int(pid)
        cid = int(cid)
    except (TypeError, ValueError):
        return []
    by_id = {}
    for bc in BadCase.query.filter(BadCase.project_id == pid, BadCase.card_id == cid).all():
        by_id[int(bc.id)] = bc
    st = str(getattr(card, 'source_type', None) or '').strip().lower().replace('-', '_')
    sid = getattr(card, 'source_id', None)
    if sid is not None:
        try:
            bid = int(sid)
        except (TypeError, ValueError):
            bid = None
        if bid and st in ('badcase', 'bad_case'):
            bc = BadCase.query.filter(BadCase.project_id == pid, BadCase.id == bid).first()
            if bc:
                by_id[int(bc.id)] = bc
    return list(by_id.values())


def _collect_bugs_for_bug_card(card):
    """与 Bug 类型看板卡片关联的全部 Bug：bug.card_id 或卡片 source 指向 Bug。"""
    if card is None:
        return []
    pid = getattr(card, 'project_id', None)
    cid = getattr(card, 'id', None)
    if pid is None or cid is None:
        return []
    try:
        pid = int(pid)
        cid = int(cid)
    except (TypeError, ValueError):
        return []
    by_id = {}
    for b in Bug.query.filter(Bug.project_id == pid, Bug.card_id == cid).all():
        by_id[int(b.id)] = b
    st = str(getattr(card, 'source_type', None) or '').strip().lower().replace('-', '_')
    sid = getattr(card, 'source_id', None)
    if sid is not None:
        try:
            bid = int(sid)
        except (TypeError, ValueError):
            bid = None
        if bid and st in ('bug',):
            b = Bug.query.filter(Bug.project_id == pid, Bug.id == bid).first()
            if b:
                by_id[int(b.id)] = b
    return list(by_id.values())


def _collect_testcases_for_testcase_card(card):
    """与 TestCase 类型看板卡片关联的全部用例：test_case.card_id 或卡片 source 指向用例。"""
    if card is None:
        return []
    pid = getattr(card, 'project_id', None)
    cid = getattr(card, 'id', None)
    if pid is None or cid is None:
        return []
    try:
        pid = int(pid)
        cid = int(cid)
    except (TypeError, ValueError):
        return []
    by_id = {}
    for tc in TestCase.query.filter(TestCase.project_id == pid, TestCase.card_id == cid).all():
        by_id[int(tc.id)] = tc
    st = str(getattr(card, 'source_type', None) or '').strip().lower().replace('-', '_')
    sid = getattr(card, 'source_id', None)
    if sid is not None:
        try:
            tid = int(sid)
        except (TypeError, ValueError):
            tid = None
        if tid and st in ('testcase', 'test_case'):
            tc = TestCase.query.filter(TestCase.project_id == pid, TestCase.id == tid).first()
            if tc:
                by_id[int(tc.id)] = tc
    return list(by_id.values())


def _canonical_modifications(modifications):
    if not isinstance(modifications, dict):
        return {}
    out = {}
    for k in sorted(modifications.keys()):
        v = modifications.get(k)
        if isinstance(v, dict):
            out[k] = {'old': v.get('old', ''), 'new': v.get('new', '')}
        else:
            out[k] = {'old': '', 'new': v}
    return out


def _fingerprint_for_diff(target, target_id, modifications):
    payload = {
        'target': _normalize_diff_target(target),
        'target_id': int(target_id),
        'modifications': _canonical_modifications(modifications),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _delete_diff_review_state_rows(project_id, target, target_ids, operator_user_id=None):
    """采纳/拒绝后物理删除 pending 行；target_ids 为 int 列表。"""
    nt = _normalize_diff_target(target)
    ids = []
    for x in target_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not ids:
        return 0
    q = DiffReviewState.query.filter(
        DiffReviewState.project_id == project_id,
        DiffReviewState.target == nt,
        DiffReviewState.target_id.in_(ids),
    )
    if operator_user_id is not None:
        q = q.filter(
            or_(
                DiffReviewState.operator_id == operator_user_id,
                DiffReviewState.operator_id.is_(None),
            )
        )
    rows = q.all()
    n = len(rows)
    for r in rows:
        db.session.delete(r)
    if n:
        db.session.commit()
    return n


def _upsert_diff_review_state(
    project_id,
    target,
    target_id,
    plan_id,
    diff,
    modifications,
    source_message_id=None,
    source_session_id=None,
    operator_id=None,
):
    """主表仅 pending：无则插入；有 pending 则更新；遗留 adopted/rejected/superseded 整键删掉后新建 pending。"""
    nt = _normalize_diff_target(target)
    tid = int(str(target_id).strip())
    canonical_mods = _canonical_modifications(modifications)
    fp = _fingerprint_for_diff(nt, tid, canonical_mods)
    now = datetime.utcnow()
    all_rows = (
        DiffReviewState.query
        .filter_by(project_id=project_id, target=nt, target_id=tid)
        .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
        .all()
    )
    row = all_rows[0] if all_rows else None

    if row is None:
        row = DiffReviewState(
            project_id=project_id,
            target=nt,
            target_id=tid,
            plan_id=plan_id,
            lifecycle_id=1,
            diff_fingerprint=fp,
            status='pending',
            diff_payload=json.dumps(diff or [], ensure_ascii=False),
            modifications_payload=json.dumps(canonical_mods, ensure_ascii=False),
            source_message_id=source_message_id,
            source_session_id=source_session_id,
            operator_id=operator_id,
            updated_at=now,
        )
        db.session.add(row)
        db.session.flush()
        return row, False

    if row.status == 'pending':
        row.plan_id = plan_id
        row.diff_fingerprint = fp
        row.diff_payload = json.dumps(diff or [], ensure_ascii=False)
        row.modifications_payload = json.dumps(canonical_mods, ensure_ascii=False)
        row.updated_at = now
        if operator_id is not None:
            row.operator_id = operator_id
        if source_message_id is not None:
            row.source_message_id = source_message_id
        if source_session_id is not None:
            row.source_session_id = source_session_id
        for old in all_rows[1:]:
            db.session.delete(old)
        db.session.flush()
        return row, False

    # 遗留非 pending：删键后重建一条 pending
    prev_lifecycle = int(row.lifecycle_id or 1)
    for old in all_rows:
        db.session.delete(old)
    db.session.flush()
    row = DiffReviewState(
        project_id=project_id,
        target=nt,
        target_id=tid,
        plan_id=plan_id,
        lifecycle_id=prev_lifecycle + 1,
        diff_fingerprint=fp,
        status='pending',
        diff_payload=json.dumps(diff or [], ensure_ascii=False),
        modifications_payload=json.dumps(canonical_mods, ensure_ascii=False),
        source_message_id=source_message_id,
        source_session_id=source_session_id,
        operator_id=operator_id,
        updated_at=now,
    )
    db.session.add(row)
    db.session.flush()
    return row, False


@app.route('/api/projects/<int:project_id>/diff-reviews/upsert', methods=['POST'])
@login_required
def api_upsert_diff_review(project_id):
    try:
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        data = request.get_json() or {}
        target = data.get('target')
        target_id = data.get('target_id')
        if target is None or target_id is None:
            return jsonify({'success': False, 'error': '缺少 target/target_id'}), 400
        row, suppressed = _upsert_diff_review_state(
            project_id=project_id,
            target=target,
            target_id=target_id,
            plan_id=data.get('plan_id'),
            diff=data.get('diff') or [],
            modifications=data.get('modifications') or {},
            source_message_id=_safe_mysql_int_fk_id(data.get('message_id')),
            source_session_id=_safe_mysql_int_fk_id(data.get('session_id')),
            operator_id=current_user.id,
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'suppressed': bool(suppressed),
            'record': {
                'id': row.id,
                'project_id': row.project_id,
                'target': row.target,
                'target_id': _json_snowflake_id(row.target_id),
                'plan_id': _json_snowflake_id(row.plan_id),
                'status': row.status,
                'lifecycle_id': row.lifecycle_id,
                'diff_fingerprint': row.diff_fingerprint,
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"[DIFF-UPSERT] 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<int:project_id>/diff-reviews/resolve', methods=['POST'])
@login_required
def api_resolve_diff_review(project_id):
    try:
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        data = request.get_json() or {}
        target = _normalize_diff_target(data.get('target'))
        target_id = data.get('target_id')
        action = (data.get('action') or '').strip().lower()
        if not target or target_id is None or action not in ('confirm', 'reject'):
            return jsonify({'success': False, 'error': '参数错误'}), 400

        rows = (
            DiffReviewState.query
            .filter_by(project_id=project_id, target=target, target_id=int(str(target_id)))
            .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
            .all()
        )
        if not rows:
            return jsonify({'success': True, 'message': '无可更新记录（幂等）'})
        row = rows[0]

        if row.operator_id is not None and row.operator_id != current_user.id:
            return jsonify({'success': False, 'error': '无权处理他人待确认的变更'}), 403

        # 采纳与拒绝均物理删除；采纳主路径在 POST /modify 内已删，此处幂等兼容旧客户端仅调 resolve 的场景
        for r in rows:
            db.session.delete(r)
        db.session.commit()
        return jsonify({'success': True, 'status': 'deleted'})
    except Exception as e:
        db.session.rollback()
        print(f"[DIFF-RESOLVE] 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<int:project_id>/diff-reviews', methods=['GET'])
@login_required
def api_list_diff_reviews(project_id):
    t0 = time.perf_counter()
    try:
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        status_raw = (request.args.get('status') or 'pending').strip().lower()
        status_filter = {s.strip() for s in status_raw.split(',') if s and s.strip()}
        
        # 使用子查询获取每个 (target, target_id) 组合的最新记录，避免全量查询
        t_sql0 = time.perf_counter()
        latest_subq = (
            db.session.query(
                DiffReviewState.target,
                DiffReviewState.target_id,
                db.func.max(DiffReviewState.updated_at).label('max_updated'),
                db.func.max(DiffReviewState.id).label('max_id')
            )
            .filter(DiffReviewState.project_id == project_id)
            .group_by(DiffReviewState.target, DiffReviewState.target_id)
            .subquery()
        )
        
        rows = (
            DiffReviewState.query
            .join(latest_subq,
                  db.and_(
                      DiffReviewState.target == latest_subq.c.target,
                      DiffReviewState.target_id == latest_subq.c.target_id,
                      DiffReviewState.updated_at == latest_subq.c.max_updated,
                      DiffReviewState.id == latest_subq.c.max_id
                  ))
            .filter(DiffReviewState.project_id == project_id)
            .all()
        )
        t_sql1 = time.perf_counter()
        
        result = []
        for r in rows:
            if status_filter and r.status not in status_filter:
                continue
            if r.status in ('pending', 'rejected'):
                if r.operator_id is not None and r.operator_id != current_user.id:
                    continue
            try:
                diff = json.loads(r.diff_payload) if r.diff_payload else []
            except Exception:
                diff = []
            try:
                mods = json.loads(r.modifications_payload) if r.modifications_payload else {}
            except Exception:
                mods = {}
            result.append({
                'target': r.target,
                'target_id': _json_snowflake_id(r.target_id),
                'plan_id': _json_snowflake_id(r.plan_id),
                'status': r.status,
                'lifecycle_id': r.lifecycle_id,
                'diff_fingerprint': r.diff_fingerprint,
                'diff': diff,
                'modifications': mods,
                'message_id': r.source_message_id,
                'session_id': r.source_session_id,
                'operator_id': r.operator_id,
            })
        t_total = (time.perf_counter() - t0) * 1000
        print(f"[PERF] GET /api/projects/{project_id}/diff-reviews sql={((t_sql1-t_sql0)*1000):.0f}ms total={t_total:.0f}ms rows={len(rows)}", flush=True)
        return jsonify({'success': True, 'items': result})
    except Exception as e:
        print(f"[DIFF-LIST] 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _normalize_chat_message_id(message_id):
    if message_id is None:
        return None
    try:
        return int(message_id)
    except (TypeError, ValueError):
        return None


# chat_message.id / chat_session.id / diff_review_state.source_* 均为 MySQL INT：前端常用 Date.now() 作临时消息 id，会溢出
_MYSQL_SIGNED_INT_MAX = 2147483647


def _safe_mysql_int_fk_id(value):
    """可写入 INT 列的外键类 id；非法或超范围（含 JS 临时大整数）返回 None，避免 INSERT 1264。"""
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 1 or n > _MYSQL_SIGNED_INT_MAX:
        return None
    return n


def _grep_nav_item_record_id(item, target_norm):
    """与 grep_tool 导航项一致：按 target 取 record_id / bug_id / source_id / card_id。"""
    if not isinstance(item, dict):
        return None
    t = str(item.get('target') or '').strip().lower().replace('-', '_')
    if t == 'test_case':
        t = 'testcase'
    if t != target_norm:
        return None
    rid = item.get('record_id')
    if rid is None:
        if target_norm == 'bug':
            rid = item.get('bug_id')
        elif target_norm in ('badcase', 'testcase'):
            rid = item.get('source_id')
        elif target_norm == 'card':
            rid = item.get('card_id') if item.get('card_id') is not None else item.get('id')
    try:
        return int(rid) if rid is not None else None
    except (TypeError, ValueError):
        return None


def _patch_grep_nav_items_list(items, target_norm, entity_id_int, new_title):
    if not isinstance(items, list) or not new_title:
        return False
    changed = False
    for it in items:
        if not isinstance(it, dict):
            continue
        rid = _grep_nav_item_record_id(it, target_norm)
        if rid is None or int(entity_id_int) != int(rid):
            continue
        it['title'] = new_title
        if target_norm == 'bug':
            it['bug_title'] = new_title
        changed = True
    return changed


def _patch_navigation_blob_for_title(nav, target_norm, entity_id_int, new_title):
    if not isinstance(nav, dict) or nav.get('type') != 'multiple':
        return False
    return _patch_grep_nav_items_list(nav.get('items'), target_norm, entity_id_int, new_title)


def _patch_steps_blob_for_title(steps, target_norm, entity_id_int, new_title):
    if not isinstance(steps, list):
        return False
    changed = False
    for step in steps:
        if not isinstance(step, dict):
            continue
        gn = step.get('grepNavigation')
        if isinstance(gn, dict) and gn.get('type') == 'multiple':
            if _patch_grep_nav_items_list(gn.get('items'), target_norm, entity_id_int, new_title):
                changed = True
    return changed


def _patch_execution_results_modify_titles(obj, target_norm, entity_id_int, new_title):
    """递归修正 modify 相关块里 before/after.title，避免清空 modify_navigation 后仍从 execution_results 恢复旧标题。"""
    changed = False
    if isinstance(obj, dict):
        tid = obj.get('target_id') if obj.get('target_id') is not None else obj.get('targetId')
        if tid is not None:
            try:
                if int(tid) == int(entity_id_int):
                    ot = str(obj.get('target') or '').strip().lower().replace('-', '_')
                    if ot == 'test_case':
                        ot = 'testcase'
                    if not ot or ot == target_norm or (target_norm == 'bug' and ot == 'bug'):
                        for side in ('before', 'after'):
                            sub = obj.get(side)
                            if isinstance(sub, dict) and 'title' in sub:
                                sub['title'] = new_title
                                changed = True
            except (TypeError, ValueError):
                pass
        for v in obj.values():
            if _patch_execution_results_modify_titles(v, target_norm, entity_id_int, new_title):
                changed = True
    elif isinstance(obj, list):
        for x in obj:
            if _patch_execution_results_modify_titles(x, target_norm, entity_id_int, new_title):
                changed = True
    return changed


def _patch_chat_message_record_titles(msg, target, target_id, new_title):
    """将本条助手消息上 grep 导航、步骤内 grep、execution_results 中与 target_id 相关的展示标题统一为 new_title。"""
    import json

    tgt = _normalize_diff_target(target)
    if tgt not in ('bug', 'badcase', 'testcase', 'card'):
        tgt = str(target or '').strip().lower().replace('-', '_')
        if tgt == 'test_case':
            tgt = 'testcase'
    try:
        eid = int(str(target_id).strip())
    except (TypeError, ValueError):
        return
    nt = (new_title or '').strip()
    if not nt:
        return
    if msg.navigation:
        try:
            nav = json.loads(msg.navigation) if isinstance(msg.navigation, str) else msg.navigation
            if _patch_navigation_blob_for_title(nav, tgt, eid, nt):
                msg.navigation = json.dumps(nav, ensure_ascii=False)
        except Exception as e:
            print(f"[MODIFY-BG] patch navigation 失败: {e}")
    if msg.steps:
        try:
            steps = json.loads(msg.steps) if isinstance(msg.steps, str) else msg.steps
            if _patch_steps_blob_for_title(steps, tgt, eid, nt):
                msg.steps = json.dumps(steps, ensure_ascii=False)
        except Exception as e:
            print(f"[MODIFY-BG] patch steps 失败: {e}")
    if msg.execution_results:
        try:
            er = (
                json.loads(msg.execution_results)
                if isinstance(msg.execution_results, str)
                else msg.execution_results
            )
            if _patch_execution_results_modify_titles(er, tgt, eid, nt):
                msg.execution_results = json.dumps(er, ensure_ascii=False)
        except Exception as e:
            print(f"[MODIFY-BG] patch execution_results 失败: {e}")


def _finalize_chat_message_after_modify_adopt(message_id, target=None, target_id=None, modifications=None):
    """采纳落库成功后：若有标题变更则同步修正本条消息上的定位/执行结果文案，再清空沙箱预览字段。"""
    mid = _normalize_chat_message_id(message_id)
    if mid is None:
        return
    try:
        db.session.expire_all()
        msg = db.session.get(ChatMessage, mid)
        if not msg:
            print(f"[MODIFY-BG] ChatMessage id={mid} 不存在，跳过 finalize")
            return
        new_title = None
        if isinstance(modifications, dict):
            tv = modifications.get('title')
            if isinstance(tv, str) and tv.strip():
                new_title = tv.strip()
        if new_title and target is not None and target_id is not None:
            try:
                _patch_chat_message_record_titles(msg, target, target_id, new_title)
            except Exception as e:
                print(f"[MODIFY-BG] 记录标题同步失败 id={mid}: {e}")
        msg.modify_groups = None
        msg.modify_navigation = None
        msg.delete_navigation = None
        db.session.commit()
        print(f"[MODIFY-BG] 已 finalize 消息 {mid}（标题同步 + 清空 modify_*）")
    except Exception as e:
        print(f"[MODIFY-BG] finalize 消息失败 id={mid}: {e}")
        db.session.rollback()


def _run_modify_in_background(
    project_id,
    target,
    target_id,
    modifications,
    message_id,
    db_uri,
    natural_query=None,
    operator_user_id=None,
):
    """后台线程执行采纳落库，使用独立 app_context 和 db.session，避免阻塞主请求"""
    import asyncio
    import json
    with app.app_context():
        try:
            from agents.tools.modify_tool import ModifyTool
            modify_tool = ModifyTool(db.session, database_uri=db_uri)
            result = asyncio.run(modify_tool.execute(
                target=target,
                target_id=int(target_id),
                modifications=modifications,
                project_id=project_id,
                confirm=True,
                natural_query=natural_query,
                message_id=message_id,
                operator_user_id=operator_user_id,
            ))
            if result.get('success') and message_id:
                _finalize_chat_message_after_modify_adopt(
                    message_id,
                    target=target,
                    target_id=int(target_id),
                    modifications=dict(modifications or {}),
                )
        except Exception as e:
            print(f"[MODIFY-BG] 后台采纳失败: {e}")


def _run_modify_batch_in_background(project_id, target, items, message_id, db_uri):
    """同一线程内顺序采纳多条，仅结束时清理消息预览一次；用于前端单次 HTTP 批量采纳。"""
    import asyncio

    with app.app_context():
        from agents.tools.modify_tool import ModifyTool

        modify_tool = ModifyTool(db.session, database_uri=db_uri)
        any_success = False
        succeeded_items = []
        try:
            for it in items:
                tid = int(it["target_id"])
                modifications = dict(it["modifications"])
                nq = it.get("natural_query")
                result = asyncio.run(
                    modify_tool.execute(
                        target=target,
                        target_id=tid,
                        modifications=modifications,
                        project_id=project_id,
                        confirm=True,
                        natural_query=nq,
                    )
                )
                if result.get("success"):
                    any_success = True
                    succeeded_items.append(it)
        except Exception as e:
            print(f"[MODIFY-BG-BATCH] 批量采纳失败: {e}")
        if any_success and message_id:
            mid = _normalize_chat_message_id(message_id)
            if mid is None:
                return
            try:
                db.session.expire_all()
                msg = db.session.get(ChatMessage, mid)
                if not msg:
                    print(f"[MODIFY-BG-BATCH] ChatMessage id={mid} 不存在，跳过 finalize")
                    return
                for it in succeeded_items:
                    mods = dict(it.get("modifications") or {})
                    tv = mods.get("title")
                    if isinstance(tv, str) and tv.strip():
                        try:
                            _patch_chat_message_record_titles(
                                msg, target, int(it["target_id"]), tv.strip()
                            )
                        except Exception as e:
                            print(f"[MODIFY-BG-BATCH] 标题同步失败 tid={it.get('target_id')}: {e}")
                msg.modify_groups = None
                msg.modify_navigation = None
                msg.delete_navigation = None
                db.session.commit()
                print(f"[MODIFY-BG-BATCH] 已 finalize 消息 {mid}（批量标题同步 + 清空 modify_*）")
            except Exception as e:
                print(f"[MODIFY-BG-BATCH] finalize 失败 id={mid}: {e}")
                db.session.rollback()


@app.route('/api/projects/<int:project_id>/modify', methods=['POST'])
@login_required
def api_project_modify(project_id):
    """沙箱确认后应用修改 - 采纳时异步落库，避免阻塞"""
    import asyncio
    import json
    import threading
    from agents.tools.modify_tool import ModifyTool
    from flask import current_app
    
    try:
        data = request.get_json() or {}
        target = data.get('target', 'bug')
        target_id = data.get('target_id')
        modifications = data.get('modifications', {})
        confirm = data.get('confirm', True)
        message_id = _normalize_chat_message_id(data.get('message_id'))
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        natural_query_top = data.get("natural_query")
        if isinstance(natural_query_top, str):
            natural_query_top = natural_query_top.strip() or None
        else:
            natural_query_top = None

        # ---------- 批量采纳：单次 HTTP，body.items = [{ target_id, modifications }, ...] ----------
        raw_items = data.get('items')
        if raw_items is not None:
            if not isinstance(raw_items, list) or len(raw_items) == 0:
                return jsonify({"success": False, "error": "items 必须为非空数组"}), 400
            if not confirm:
                return jsonify({"success": False, "error": "批量仅支持采纳(confirm=true)"}), 400
            nt = _normalize_diff_target(target)
            normalized = []
            for it in raw_items:
                if not isinstance(it, dict):
                    return jsonify({"success": False, "error": "items 元素必须为对象"}), 400
                tid = it.get('target_id')
                mods = it.get('modifications')
                if tid is None or not mods:
                    return jsonify({"success": False, "error": "每项需含 target_id 与 modifications"}), 400
                nq_item = it.get("natural_query")
                if isinstance(nq_item, str):
                    nq_item = nq_item.strip() or None
                else:
                    nq_item = None
                if nq_item is None and natural_query_top:
                    nq_item = natural_query_top
                normalized.append(
                    {
                        "target_id": int(tid),
                        "modifications": dict(mods),
                        "natural_query": nq_item,
                    }
                )
            for it in normalized:
                tid = it['target_id']
                pend = (
                    DiffReviewState.query.filter_by(
                        project_id=project_id, target=nt, target_id=tid
                    )
                    .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
                    .first()
                )
                if pend and pend.status == 'pending':
                    if pend.operator_id is not None and pend.operator_id != current_user.id:
                        return jsonify(
                            {"success": False, "error": f"无权采纳他人待确认的变更 (target_id={tid})"}
                        ), 403
            _delete_diff_review_state_rows(
                project_id,
                target,
                [it["target_id"] for it in normalized],
                current_user.id,
            )
            thread = threading.Thread(
                target=_run_modify_batch_in_background,
                args=(project_id, target, normalized, message_id, db_uri),
                daemon=True,
            )
            thread.start()
            return jsonify({
                "success": True,
                "message": "正在批量保存",
                "async": True,
                "batch": True,
                "count": len(normalized),
            })

        if not target_id or not modifications:
            return jsonify({"success": False, "error": "target_id 和 modifications 不能为空"}), 400
        
        if confirm:
            nt = _normalize_diff_target(target)
            tid = int(target_id)
            pend = (
                DiffReviewState.query.filter_by(
                    project_id=project_id, target=nt, target_id=tid
                )
                .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
                .first()
            )
            if pend and pend.status == 'pending':
                if pend.operator_id is not None and pend.operator_id != current_user.id:
                    return jsonify({"success": False, "error": "无权采纳他人待确认的变更"}), 403
            _delete_diff_review_state_rows(project_id, target, [tid], current_user.id)
            # 采纳即落库：后台异步执行 ModifyTool，立即返回（diff 行已同步删除）
            thread = threading.Thread(
                target=_run_modify_in_background,
                args=(
                    project_id,
                    target,
                    target_id,
                    dict(modifications),
                    message_id,
                    db_uri,
                    natural_query_top,
                    current_user.id,
                ),
                daemon=True
            )
            thread.start()
            return jsonify({
                "success": True,
                "message": "正在保存",
                "async": True,
                "before": None, "after": None, "diff": None
            })
        
        # 沙箱预览：同步执行
        modify_tool = ModifyTool(db.session, database_uri=db_uri)
        async def run_modify():
            return await modify_tool.execute(
                target=target, target_id=target_id, modifications=modifications,
                project_id=project_id, confirm=False
            )
        result = asyncio.run(run_modify())
        
        if result.get('success'):
            # 更新数据库中消息的 modify_navigation 字段
            if message_id:
                try:
                    message = ChatMessage.query.get(message_id)
                    if message and message.modify_navigation:
                        modify_nav = json.loads(message.modify_navigation) if isinstance(message.modify_navigation, str) else message.modify_navigation
                        modify_nav['success'] = True
                        modify_nav['confirmation_required'] = False
                        message.modify_navigation = json.dumps(modify_nav, ensure_ascii=False)
                        db.session.commit()
                        print(f"[MODIFY-API] 已更新消息 {message_id} 的 modify_navigation 状态")
                except Exception as e:
                    print(f"[MODIFY-API] 更新消息状态失败: {e}")
            
            return jsonify({
                "success": True,
                "message": result.get('message', '修改成功'),
                "before": result.get('before'),
                "after": result.get('after'),
                "diff": result.get('diff')
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get('error', '修改失败')
            }), 500
            
    except Exception as e:
        print(f"[MODIFY-API] 修改失败: {e}")
        return jsonify({"success": False, "error": f"修改失败: {str(e)}"}), 500

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


@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload_file():
    """富文本附件上传：走 /api 前缀以便 Vite 代理与 axios 同源带 Cookie。"""
    return upload_file()


@app.route('/api/uploads/image/<path:file_path>', methods=['GET'])
@login_required
def api_get_upload_image(file_path):
    """富文本/附件图片：经后端从 MinIO 拉取，避免浏览器直连私有桶失败。"""
    try:
        decoded_path = unquote(file_path).strip().lstrip('/')
        if not decoded_path or '..' in decoded_path.split('/'):
            return jsonify({'error': '无效路径'}), 400

        saas_prefix = (MINIO_CONFIG['saas_file_path'] or '').strip().lstrip('/')
        if saas_prefix and not decoded_path.startswith(saas_prefix):
            full_path = f"{MINIO_CONFIG['saas_file_path']}{decoded_path}"
        else:
            full_path = decoded_path

        cache_key = get_upload_image_cache_key(full_path)
        cached_image_data = get_image_from_cache(cache_key)
        if cached_image_data:
            image_data = cached_image_data
        else:
            client = get_minio_client()
            try:
                client.head_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
            except ClientError as e:
                if e.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound'):
                    return jsonify({'error': '文件不存在'}), 404
                raise

            raw = client.get_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
            image_data = read_minio_object_bytes(raw)

        lower = decoded_path.lower()
        mime_type = mimetypes.guess_type(decoded_path)[0] or 'application/octet-stream'
        if lower.endswith('.png'):
            mime_type = 'image/png'
        elif lower.endswith('.gif'):
            mime_type = 'image/gif'
        elif lower.endswith('.webp'):
            mime_type = 'image/webp'
        elif lower.endswith(('.jpg', '.jpeg')):
            mime_type = 'image/jpeg'

        if not cached_image_data and mime_type.startswith('image/'):
            set_image_to_cache(cache_key, image_data, 3600)

        resp = app.response_class(image_data, status=200, mimetype=mime_type)
        resp.headers['Cache-Control'] = 'private, max-age=3600'
        resp.headers['Content-Type'] = mime_type
        return resp
    except ClientError as e:
        print(f"获取上传图片失败: {e}")
        return jsonify({'error': '获取图片失败'}), 500
    except Exception as e:
        print(f"获取上传图片异常: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


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
    t0 = time.perf_counter()
    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问'}), 403
    
    # 使用 JOIN 一次性查询，避免 N+1 问题
    rows = (
        db.session.query(User.id, User.name, User.email, ProjectPermission.role)
        .join(ProjectPermission, User.id == ProjectPermission.user_id)
        .filter(ProjectPermission.project_id == project_id)
        .all()
    )
    
    members = [{'id': r.id, 'name': r.name, 'email': r.email, 'role': r.role} for r in rows]
    
    t_total = (time.perf_counter() - t0) * 1000
    print(f"[PERF] GET /api/project/{project_id}/members total={t_total:.1f}ms count={len(members)}", flush=True)
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
    _redis_cache_invalidate_project(project_id)
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
    _redis_cache_invalidate_project(project_id)
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
    _redis_cache_invalidate_project(project_id)
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
                    answer=row.get('answer', row.get('correct_answer', '')),
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
                    answer=row.get('answer', row.get('correct_answer', '')),
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


def _safe_parse_project_login_configs(raw):
    """解析 project.login_configs；迁移/脏数据下可能不是合法 JSON，避免拖垮项目详情接口。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    s = str(raw).strip()
    if not s:
        return []
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return [v]
        return []
    except (json.JSONDecodeError, TypeError, ValueError):
        print(f"[_safe_parse_project_login_configs] 无效 JSON，已置空 preview={s[:160]!r}")
        return []


# API端点 - 项目管理
@app.route('/api/projects', methods=['GET'])
@login_required
def api_get_projects():
    t0 = time.perf_counter()
    try:
        # Redis 缓存（按用户维度）；无 Redis 时走下方进程内短缓存 + 轻量 SQL
        redis_hit, redis_cached = _redis_cache_get(f'projects:{current_user.id}')
        if redis_hit:
            t_total = (time.perf_counter() - t0) * 1000
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(f"[PERF] GET /api/projects redis_hit total={t_total:.1f}ms", flush=True)
            return jsonify(redis_cached)

        mem_hit, mem_cached = _cache_get(('api_projects', current_user.id), ttl_s=20.0)
        if mem_hit:
            t_total = (time.perf_counter() - t0) * 1000
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(f"[PERF] GET /api/projects mem_hit total={t_total:.1f}ms", flush=True)
            return jsonify(mem_cached)

        uid = current_user.id
        t1 = time.perf_counter()
        # 拆成两次窄查询：均走 user_id / (user_id,project_id) 索引友好路径，且只取列表字段，避免 ORM 加载 login_configs、intro 等大列
        owned_rows = (
            db.session.query(
                Project.id,
                Project.name,
                Project.description,
                Project.avatar,
                Project.owner,
                Project.status,
                Project.created_at,
            )
            .filter(Project.user_id == uid)
            .order_by(Project.created_at.desc())
            .limit(100)
            .all()
        )
        shared_rows = (
            db.session.query(
                Project.id,
                Project.name,
                Project.description,
                Project.avatar,
                Project.owner,
                Project.status,
                Project.created_at,
                ProjectPermission.role,
            )
            .join(ProjectPermission, Project.id == ProjectPermission.project_id)
            .filter(ProjectPermission.user_id == uid, Project.user_id != uid)
            .order_by(Project.created_at.desc())
            .limit(100)
            .all()
        )
        t_q = (time.perf_counter() - t1) * 1000

        by_pid = {}
        for rid, name, desc, av, ow, st, cat in owned_rows:
            by_pid[rid] = {
                'id': rid,
                'name': name,
                'description': desc,
                'avatar': av,
                'owner': ow,
                'status': st,
                'created_at': cat.isoformat() if cat else '',
                'role': 'admin',
            }
        for rid, name, desc, av, ow, st, cat, role in shared_rows:
            if rid in by_pid:
                continue
            by_pid[rid] = {
                'id': rid,
                'name': name,
                'description': desc,
                'avatar': av,
                'owner': ow,
                'status': st,
                'created_at': cat.isoformat() if cat else '',
                'role': role or 'collaborator',
            }

        user_projects = list(by_pid.values())
        user_projects.sort(key=lambda x: x['created_at'], reverse=True)

        t_total = (time.perf_counter() - t0) * 1000
        if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
            print(
                f"[PERF] GET /api/projects total={t_total:.1f}ms q={t_q:.1f}ms "
                f"owned={len(owned_rows)} shared={len(shared_rows)} merged={len(user_projects)}",
                flush=True,
            )
        result = {'success': True, 'projects': user_projects}
        _redis_cache_set(f'projects:{current_user.id}', result, ttl_s=60)
        _cache_set(('api_projects', current_user.id), result)
        return jsonify(result)
        
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
        
        # 创建默认迭代
        default_plan = Plan(
            name='迭代 1',
            description='项目默认迭代',
            status='active',
            project_id=project.id,
            creator_id=current_user.id,
            is_default=True
        )
        db.session.add(default_plan)
        db.session.commit()
        print(f"已为用户 {current_user.id} 添加项目 {project.id} 的管理员权限")
        print(f"已为项目 {project.id} 创建默认迭代，ID: {default_plan.id}")
        
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
        _redis_cache_invalidate_projects(current_user.id)
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
        # 只获取项目基本信息，不包含BadCase列表（并避免重复查询 Project）
        # 勿用 get_or_404：NotFound 会被下方 except Exception 吞掉并误返回 500
        project = Project.query.get(project_id)
        if not project:
            return jsonify({'success': False, 'error': '项目不存在'}), 404
        if project.user_id != current_user.id:
            has_perm = ProjectPermission.query.filter_by(
                user_id=current_user.id,
                project_id=project_id
            ).first() is not None
            if not has_perm:
                print(f"权限检查失败: 用户 {current_user.id} 无权访问项目 {project_id}")
                return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        print(f"项目信息获取成功: {project.name}")
        
        # 获取BadCase统计信息（快速统计）；状态与 BadCaseStatus 枚举对齐（closed 非 close）
        total_bc = pending_bc = resolved_bc = closed_bc = 0
        try:
            st = db.session.query(
                db.func.count(BadCase.id),
                db.func.sum(db.case((BadCase.status == BadCaseStatus.PENDING, 1), else_=0)),
                db.func.sum(db.case((BadCase.status == BadCaseStatus.RESOLVED, 1), else_=0)),
                db.func.sum(db.case((BadCase.status == BadCaseStatus.CLOSED, 1), else_=0)),
            ).filter(BadCase.project_id == project_id).first()
            if st:
                total_bc = int(st[0] or 0)
                pending_bc = int(st[1] or 0)
                resolved_bc = int(st[2] or 0)
                closed_bc = int(st[3] or 0)
        except Exception as se:
            print(f"[api_get_project_detail] BadCase 统计查询失败(已降级为0): {se}")
            import traceback
            traceback.print_exc()

        print(
            f"BadCase统计完成: 总计={total_bc}, 待处理={pending_bc}, "
            f"已解决={resolved_bc}, 已关闭={closed_bc}"
        )

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
                'login_configs': _safe_parse_project_login_configs(project.login_configs),
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'badcase_stats': {
                    'total': total_bc,
                    'pending': pending_bc,
                    'resolved': resolved_bc,
                    'close': closed_bc,
                }
            }
        })
    except Exception as e:
        print(f"获取项目详情失败: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取项目信息失败'}), 500

@app.route('/api/projects/<int:project_id>/edit-context', methods=['GET'])
@login_required
def api_get_project_edit_context(project_id):
    """编辑页专用：一次性返回最小必要上下文（project + plans + members）"""
    t0 = time.perf_counter()
    try:
        # Redis 缓存检查（优先于内存缓存，跨进程共享）
        redis_hit, redis_cached = _redis_cache_get(f'edit-context:{project_id}')
        if redis_hit:
            t_total = (time.perf_counter() - t0) * 1000
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(f"[PERF] GET /api/projects/{project_id}/edit-context redis_hit total={t_total:.1f}ms", flush=True)
            return jsonify(redis_cached)

        t_access0 = time.perf_counter()
        project, access_err = _project_for_user_collaborator_access(project_id, current_user.id)
        if access_err == 'not_found':
            return jsonify({'success': False, 'error': '项目不存在'}), 404
        if access_err == 'forbidden':
            return jsonify({'success': False, 'error': '没有项目权限'}), 403

        t_plans0 = time.perf_counter()
        # plans：沿用 /plans 的批量统计逻辑（无 N+1）
        plans = Plan.query.filter_by(project_id=project_id).all()
        children_map = {}
        plan_by_id = {}
        for p in plans:
            plan_by_id[p.id] = p
            children_map.setdefault(p.parent_id, []).append(p)

        plan_ids = list(plan_by_id.keys())
        badcase_counts = {}
        bug_counts = {}
        testcase_counts = {}
        t_counts0 = time.perf_counter()
        if plan_ids:
            # 单次 RTT：bad_case / bug / test_case 三个聚合（原为 3 条独立查询）
            ids_sql = ','.join(str(int(x)) for x in plan_ids)
            cnt_rows = db.session.execute(
                text(
                    "SELECT 'bc' AS k, plan_id, COUNT(*) AS c FROM bad_case "
                    f"WHERE plan_id IN ({ids_sql}) GROUP BY plan_id "
                    "UNION ALL SELECT 'bug', plan_id, COUNT(*) FROM bug "
                    f"WHERE plan_id IN ({ids_sql}) GROUP BY plan_id "
                    "UNION ALL SELECT 'tc', plan_id, COUNT(*) FROM test_case "
                    f"WHERE plan_id IN ({ids_sql}) GROUP BY plan_id"
                )
            ).fetchall()
            for row in cnt_rows:
                k, pid, c = row[0], row[1], int(row[2])
                if k == 'bc':
                    badcase_counts[pid] = c
                elif k == 'bug':
                    bug_counts[pid] = c
                else:
                    testcase_counts[pid] = c
        t_counts1 = time.perf_counter()

        def _sort_key(p: Plan):
            pinned = 1 if getattr(p, "is_pinned", False) else 0
            created = getattr(p, "created_at", None)
            ts = 0
            if created:
                try:
                    ts = int(created.timestamp())
                except Exception:
                    ts = 0
            return (-pinned, -ts)

        def build_plan_tree(plan: Plan):
            children = [build_plan_tree(c) for c in sorted(children_map.get(plan.id, []), key=_sort_key)]
            bc = int(badcase_counts.get(plan.id, 0))
            bug = int(bug_counts.get(plan.id, 0))
            tc = int(testcase_counts.get(plan.id, 0))
            for c in children:
                bc += c.get('badcase_count', 0)
                bug += c.get('bug_count', 0)
                tc += c.get('test_case_count', 0)
            return {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'is_pinned': plan.is_pinned,
                'is_default': plan.is_default,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
                'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
                'children': children,
                'badcase_count': bc,
                'bug_count': bug,
                'test_case_count': tc,
            }

        root_plans = sorted(children_map.get(None, []), key=_sort_key)
        plans_tree = [build_plan_tree(p) for p in root_plans]

        t_mem0 = time.perf_counter()
        # 直接成员 + 团队成员合并为 1 次 UNION；字符串列显式 COLLATE，避免 MySQL 1271 Illegal mix of collations
        _pid = int(project_id)
        _ut = User.__table__.name
        _ppt = ProjectPermission.__table__.name
        _tmt = TeamMember.__table__.name
        _tt = Team.__table__.name

        def _qb(n):
            return f'`{n}`' if n else n

        _cs = "utf8mb4_general_ci"
        mem_sql = text(
            f"SELECT CONVERT('direct' USING utf8mb4) COLLATE {_cs} AS src, u.id, "
            f"CONVERT(u.name USING utf8mb4) COLLATE {_cs} AS name, "
            f"CONVERT(u.email USING utf8mb4) COLLATE {_cs} AS email, "
            f"CONVERT(pp.role USING utf8mb4) COLLATE {_cs} AS role, "
            f"CAST(NULL AS CHAR(200) CHARACTER SET utf8mb4) COLLATE {_cs} AS team_name "
            f"FROM {_qb(_ut)} u INNER JOIN {_qb(_ppt)} pp ON pp.user_id = u.id WHERE pp.project_id = :pid "
            f"UNION ALL "
            f"SELECT CONVERT('team' USING utf8mb4) COLLATE {_cs} AS src, u.id, "
            f"CONVERT(u.name USING utf8mb4) COLLATE {_cs}, "
            f"CONVERT(u.email USING utf8mb4) COLLATE {_cs}, "
            f"CONVERT(tm.role USING utf8mb4) COLLATE {_cs}, "
            f"CONVERT(t.name USING utf8mb4) COLLATE {_cs} AS team_name "
            f"FROM {_qb(_ut)} u INNER JOIN {_qb(_tmt)} tm ON tm.user_id = u.id "
            f"INNER JOIN {_qb(_tt)} t ON t.id = tm.team_id WHERE t.project_id = :pid"
        )
        mem_rows = db.session.execute(mem_sql, {'pid': _pid}).fetchall()
        t_mem_fetch = time.perf_counter()
        direct_member_map = {}
        team_candidates = []
        for row in mem_rows:
            src, uid, name, email, role, team_name = (
                row[0], row[1], row[2], row[3], row[4], row[5]
            )
            if src == 'direct':
                direct_member_map[uid] = {
                    'id': uid,
                    'name': name,
                    'email': email,
                    'role': role,
                    'source': 'direct_permission',
                }
            else:
                team_candidates.append((uid, name, email, role, team_name))
        team_members = []
        for uid, name, email, role, team_name in team_candidates:
            if uid in direct_member_map:
                continue
            team_members.append({
                'id': uid,
                'name': name,
                'email': email,
                'role': role,
                'source': f'team_{team_name}',
            })

        t_mem1 = time.perf_counter()
        t_total = (time.perf_counter() - t0) * 1000
        if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
            print(
                f"[PERF] GET /api/projects/{project_id}/edit-context total={t_total:.1f}ms "
                f"access={(t_plans0 - t_access0) * 1000:.1f}ms "
                f"plans={(t_counts0 - t_plans0) * 1000:.1f}ms "
                f"counts={(t_counts1 - t_counts0) * 1000:.1f}ms "
                f"tree={(t_mem0 - t_counts1) * 1000:.1f}ms "
                f"members={(t_mem1 - t_mem0) * 1000:.1f}ms "
                f"(members_sql={(t_mem_fetch - t_mem0) * 1000:.1f}ms members_py={(t_mem1 - t_mem_fetch) * 1000:.1f}ms)",
                flush=True,
            )
        result = {
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
            },
            'plans': plans_tree,
            'members': list(direct_member_map.values()) + team_members,
        }
        _redis_cache_set(f'edit-context:{project_id}', result, ttl_s=30)
        return jsonify(result)

    except Exception as e:
        import traceback
        print(f"获取编辑页上下文失败: {e}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取编辑页上下文失败'}), 500

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
        _redis_cache_invalidate_project(project_id)
        _redis_cache_invalidate_projects(current_user.id)
        
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
        plan_id = _parse_query_int_optional('plan_id')
        card_id = _parse_query_optional_int64('card_id')
        
        # 获取状态类型和内容类型参数
        status_type = request.args.get('status_type')
        content_type = request.args.get('content_type')
        
        # 构建查询条件
        query = BadCase.query.filter_by(project_id=project_id)
        
        # 卡片分类型：优先按 card_id 过滤（与 Bug 列表一致）
        if card_id is not None:
            query = query.filter(BadCase.card_id == card_id)
            print(f"按卡片ID过滤BadCase: card_id={card_id}", flush=True)
        # 处理status_type和content_type参数
        elif status_type == 'unplanned':
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

        # 自动修补：plan_id 为空但 plan 列为数字 id 时写回（避免一直落在「未计划」列表）
        _repaired = False
        for _bc in pagination.items:
            if _try_repair_badcase_plan_id_from_legacy_plan_string(_bc):
                _repaired = True
        if _repaired:
            db.session.commit()
            _cache_invalidate_plans(project_id)

        _card_repaired = False
        for _bc in pagination.items:
            if _try_repair_badcase_card_id_from_source_card(_bc):
                _card_repaired = True
        if _card_repaired:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[BadCase列表] card_id 反查补写 commit 失败: {e}", flush=True)

        # 批量解析 assignee -> user.name，避免 N+1
        def _parse_assignee_ids(raw):
            if raw is None:
                return []
            s = str(raw).strip()
            if not s:
                return []
            try:
                if ',' in s:
                    return [int(x.strip()) for x in s.split(',') if x.strip()]
                return [int(s)]
            except (ValueError, TypeError):
                return []

        all_user_ids = set()
        assignee_id_lists = {}
        for bc in pagination.items:
            ids = _parse_assignee_ids(bc.assignee)
            assignee_id_lists[bc.id] = ids
            all_user_ids.update(ids)

        user_name_map = {}
        if all_user_ids:
            rows = db.session.query(User.id, User.name).filter(User.id.in_(list(all_user_ids))).all()
            user_name_map = {uid: name for uid, name in rows}

        badcases = []
        for bc in pagination.items:
            assignee_display = '未指派'
            ids = assignee_id_lists.get(bc.id) or []
            if ids:
                # 兼容单选/多选展示
                first_name = user_name_map.get(ids[0])
                if first_name:
                    assignee_display = first_name if len(ids) == 1 else f"{first_name}..."
                else:
                    assignee_display = str(bc.assignee)
            elif bc.assignee:
                # 非法格式直接回显
                assignee_display = str(bc.assignee)

            badcases.append({
                'id': _json_snowflake_id(bc.id),
                'title': bc.title,
                'case_category': bc.case_category,
                'base_problem': (bc.base_problem[:100] + '...') if bc.base_problem and len(bc.base_problem) > 100 else (bc.base_problem or ''),
                'priority': bc.priority,
                'status': bc.status.value if hasattr(bc.status, 'value') else bc.status,  # 枚举类型转换为值
                'assignee': assignee_display,
                'plan_id': _json_snowflake_id(bc.plan_id),  # 添加计划ID字段
                'card_id': _json_snowflake_id(getattr(bc, 'card_id', None)),
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
        import traceback
        print(f"获取项目BadCase列表失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
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

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
def api_delete_project(project_id):
    """删除项目"""
    print(f"=== 开始删除项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 先获取项目信息检查是否是所有者
        project = Project.query.get_or_404(project_id)
        print(f"项目所有者(user_id): {project.user_id}, 当前用户: {current_user.id}")
        
        # 检查是否是项目所有者(user_id)，或者有管理员权限
        is_owner = project.user_id == current_user.id
        has_admin = has_project_permission(current_user.id, project_id, 'admin')
        
        print(f"是否所有者: {is_owner}, 是否有管理员权限: {has_admin}")
        
        if not is_owner and not has_admin:
            print(f"权限检查失败: 用户 {current_user.id} 无权删除项目 {project_id}")
            return jsonify({'success': False, 'error': '无权删除此项目，只有项目创建者或管理员可以删除'}), 403
        print("权限检查通过")
        
        print(f"项目信息: ID={project.id}, 名称={project.name}")
        project_name = project.name
        
        # 手动删除所有关联数据
        print("开始删除关联数据...")
        
        from sqlalchemy import text
        
        # 使用原生 SQL 删除，避免 SQLAlchemy 关系行为干扰
        
        # 删除关联的 BadCase
        result = db.session.execute(text("DELETE FROM bad_case WHERE project_id = :pid"), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 BadCase...")
        
        # 删除关联的 TestCase
        result = db.session.execute(text("DELETE FROM test_case WHERE project_id = :pid"), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 TestCase...")
        
        # 删除关联的 Bug（包括关联到该项目下所有 Plan 的 Bug）
        result = db.session.execute(text("""
            DELETE FROM bug WHERE project_id = :pid OR plan_id IN (
                SELECT id FROM plan WHERE project_id = :pid
            )
        """), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 Bug...")
        
        # 删除关联的 Plan
        result = db.session.execute(text("DELETE FROM plan WHERE project_id = :pid"), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 Plan...")
        
        # 删除关联的 Team
        teams = Team.query.filter_by(project_id=project_id).all()
        print(f"删除 {len(teams)} 个 Team...")
        for team in teams:
            # 删除团队成员
            TeamMember.query.filter_by(team_id=team.id).delete()
            db.session.delete(team)
        
        # 删除关联的 ProjectPermission
        permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
        print(f"删除 {len(permissions)} 个 ProjectPermission...")
        for perm in permissions:
            db.session.delete(perm)
        
        # 最后删除项目本身
        print("删除项目本身...")
        db.session.delete(project)
        print(f"项目已标记删除: {project_name}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        response_data = {
            'success': True,
            'message': f'项目 "{project_name}" 删除成功'
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 删除完成 ===")
        _redis_cache_invalidate_project(project_id)
        _redis_cache_invalidate_projects(current_user.id)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"删除项目时发生错误: {str(e)}")
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
        base_problem = (data.get('base_problem') or '').strip()
        badcase_result = data.get('badcase_result')
        answer = data.get('answer')
        correct_answer = data.get('correct_answer')
        
        # 检查必要字段
        missing_fields = []
        if not project_id:
            missing_fields.append('project_id')
        if not title:
            missing_fields.append('title')
        if not case_category:
            missing_fields.append('case_category')
        if not badcase_result:
            missing_fields.append('badcase_result')
        if not answer:
            missing_fields.append('answer')
            
        if missing_fields:
            return jsonify({
                'success': False, 
                'error': f'缺少必要字段: {", ".join(missing_fields)}'
            }), 400
        
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权在此项目中创建BadCase'}), 403
        
        # 如果提供了 card_id，按卡片类型校验（卡片分类型，计划不分类型）
        raw_card = data.get('card_id')
        card_id_val = None
        if raw_card is not None and str(raw_card).strip() != '':
            try:
                ci = int(raw_card)
                if ci != 0:
                    card_id_val = ci
            except (TypeError, ValueError):
                card_id_val = None
        
        if card_id_val is not None:
            # 按卡片类型校验
            card = Card.query.get(card_id_val)
            if not card:
                return jsonify({'success': False, 'error': '卡片不存在'}), 404
            # 检查卡片类型是否为 badcase
            card_type_value = card.type.value if hasattr(card.type, 'value') else str(card.type)
            if card_type_value != 'badcase':
                return jsonify({'success': False, 'error': '只能在badcase类型卡片中创建badcase'}), 400
        
        # 处理附件数据
        import json
        attachments_json = json.dumps(data.get('attachments', [])) if data.get('attachments') else None
        
        _pid = data.get('plan_id')
        if _pid in (None, '', 0, '0'):
            _pid = None
        else:
            try:
                _pid = int(_pid)
            except (TypeError, ValueError):
                _pid = None
        # 兼容旧前端：只把所选迭代写在 plan（字符串数字）里、未传 plan_id
        if _pid is None:
            _legacy = data.get('plan')
            if _legacy not in (None, '', 'unplanned'):
                s = str(_legacy).strip()
                if s.isdigit():
                    try:
                        _pid = int(s)
                    except ValueError:
                        _pid = None

        badcase = BadCase(
            project_id=project_id,
            plan_id=_pid,
            card_id=card_id_val,
            creator_id=current_user.id,
            title=title,
            case_category=case_category,
            base_problem=base_problem,
            reproduction_steps=data.get('reproduction_steps', ''),
            badcase_result=badcase_result,
            answer=answer,
            correct_answer=correct_answer or '',
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
        db.session.refresh(badcase)
        _cache_invalidate_plans(project_id)

        linked_cid = ensure_badcase_card_link(badcase, auto_create=(card_id_val is None))
        if linked_cid is None and card_id_val is not None:
            print(
                f"[api_create_badcase] 警告: 已传 card_id={card_id_val} 但未能建立双向关联，"
                f"badcase id={badcase.id}",
                flush=True,
            )
        
        print(f"BadCase创建成功，ID: {badcase.id}, card_id: {getattr(badcase, 'card_id', None)}")
        try:
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_badcase(badcase), badcase.creator_id
            )
            _schedule_workflow_notify(
                "created",
                "badcase",
                badcase.id,
                badcase.title or "",
                badcase.project_id,
                _workflow_project_name(badcase.project_id),
                _badcase_status_str(badcase),
                None,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] BadCase 创建通知调度失败: {_e}")
        
        return jsonify({
            'success': True,
            'badcase': {
                'id': _json_snowflake_id(badcase.id),
                'title': badcase.title,
                'project_id': badcase.project_id,
                'plan_id': _json_snowflake_id(badcase.plan_id),
                'card_id': _json_snowflake_id(getattr(badcase, 'card_id', None)),
                'creator_id': badcase.creator_id,
                'case_category': badcase.case_category,
                'base_problem': badcase.base_problem,
                'badcase_result': badcase.badcase_result,
                'answer': badcase.answer,
                'correct_answer': badcase.correct_answer,
                'priority': badcase.priority,
                'status': badcase.status.value if hasattr(badcase.status, 'value') else badcase.status,
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
    badcase, access_err = _model_for_user_collaborator_access(BadCase, badcase_id, current_user.id)
    if access_err == 'not_found':
        return jsonify({'success': False, 'error': 'BadCase不存在'}), 404
    if access_err == 'forbidden':
        return jsonify({'success': False, 'error': '无权访问此BadCase'}), 403
    
    # 评论 + 用户名一次 JOIN；负责人姓名仍按需补查（常与评论用户不重叠）
    comment_rows = (
        db.session.query(
            Comment.id,
            Comment.content,
            Comment.user_id,
            Comment.created_at,
            Comment.source_message_id,
            User.name,
        )
        .outerjoin(User, User.id == Comment.user_id)
        .filter(Comment.badcase_id == badcase_id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    
    # 解析附件数据
    import json
    attachments = []
    if badcase.attachments:
        try:
            attachments = json.loads(badcase.attachments)
        except:
            attachments = []
    
    # 解析负责人字段（支持单个/逗号分隔 ID），并批量查 user_map，避免 N+1
    def _parse_assignee_ids(raw):
        if raw is None:
            return []
        s = str(raw).strip()
        if not s:
            return []
        try:
            if ',' in s:
                return [int(x.strip()) for x in s.split(',') if x.strip()]
            return [int(s)]
        except (ValueError, TypeError):
            return []

    assignee_ids = _parse_assignee_ids(badcase.assignee)
    assignee_id = assignee_ids[0] if assignee_ids else None

    user_name_map = {}
    for (_cid, _content, uid, _dt, uname) in comment_rows:
        if uid and uid not in user_name_map:
            user_name_map[uid] = uname or ''
    missing_assignee = set(assignee_ids) - set(user_name_map.keys())
    if missing_assignee:
        rows = db.session.query(User.id, User.name).filter(User.id.in_(list(missing_assignee))).all()
        for uid, name in rows:
            user_name_map[uid] = name or ''

    if assignee_ids:
        first_name = user_name_map.get(assignee_ids[0])
        if first_name:
            assignee_name = first_name if len(assignee_ids) == 1 else f"{first_name}..."
        else:
            assignee_name = str(badcase.assignee)
    else:
        assignee_name = str(badcase.assignee) if badcase.assignee else ''

    if _try_repair_badcase_plan_id_from_legacy_plan_string(badcase):
        db.session.commit()
        _cache_invalidate_plans(badcase.project_id)

    if _try_repair_badcase_card_id_from_source_card(badcase):
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[BadCase详情] card_id 反查补写失败: {e}", flush=True)

    return jsonify({
        'success': True,
        'badcase': {
            'id': _json_snowflake_id(badcase.id),
            'project_id': badcase.project_id,  # 添加项目ID字段
            'plan_id': _json_snowflake_id(badcase.plan_id),
            'card_id': _json_snowflake_id(getattr(badcase, 'card_id', None)),
            'title': badcase.title,
            'case_category': badcase.case_category,
            'base_problem': badcase.base_problem,
            'reproduction_steps': badcase.reproduction_steps,
            'badcase_result': badcase.badcase_result,
            'answer': badcase.answer,
            'correct_answer': badcase.correct_answer,
            'problem_reason': badcase.problem_reason,
            'solution': badcase.solution,
            'priority': badcase.priority,
            'status': badcase.status.value if hasattr(badcase.status, 'value') else badcase.status,  # 枚举类型转换为值
            'assignee': assignee_name,  # 用户名用于显示
            'assignee_id': assignee_id,  # 用户ID用于下拉框选中
            'plan': badcase.plan,
            'document_type': badcase.document_type,
            'attachments': attachments,
            'assigned_users': badcase.assigned_users,
            'created_at': badcase.created_at.isoformat(),
            'updated_at': badcase.updated_at.isoformat(),
            'comments': [{
                'id': cid,
                'content': content,
                'user_id': uid,
                'user_name': uname or '',
                'source_message_id': smid,
                'created_at': created_at.isoformat()
            } for (cid, content, uid, created_at, smid, uname) in comment_rows]
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
    old_status = _badcase_status_str(badcase)
    
    if status:
        badcase.status = status
    if assigned_users is not None:
        badcase.assigned_users = assigned_users
    
    db.session.commit()
    new_status = _badcase_status_str(badcase)
    try:
        _rec = _workflow_merge_creator_if_empty(
            _workflow_recipients_badcase(badcase), badcase.creator_id
        )
        _ev = (
            "status_changed"
            if status and old_status != new_status
            else "updated"
        )
        _prev = old_status if (status and old_status != new_status) else None
        _schedule_workflow_notify(
            _ev,
            "badcase",
            badcase.id,
            badcase.title or "",
            badcase.project_id,
            _workflow_project_name(badcase.project_id),
            new_status,
            _prev,
            _rec,
            actor_id=current_user.id,
            actor_name=getattr(current_user, "name", "") or "",
        )
    except Exception as _e:
        print(f"[workflow_notify] BadCase 状态接口通知失败: {_e}")
    
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
    
    try:
        comment = _append_badcase_comment_row(
            badcase,
            content,
            current_user.id,
            source_message_id=data.get('message_id'),
        )
        db.session.commit()
        return jsonify({'success': True, 'comment': comment})
    except Exception as e:
        db.session.rollback()
        print(f"[API] 追加 BadCase 评论失败: {e}", flush=True)
        return jsonify({'success': False, 'error': '追加评论失败'}), 500

@app.route('/api/badcases/<int:badcase_id>', methods=['PUT', 'DELETE'])
@login_required
def api_update_badcase(badcase_id):
    """更新BadCase信息"""
    print(f"=== 更新/删除 BadCase {badcase_id} ===")
    
    # 删除
    if request.method == 'DELETE':
        try:
            badcase = BadCase.query.get_or_404(badcase_id)
            
            if not has_project_permission(current_user.id, badcase.project_id):
                return jsonify({'success': False, 'error': '无权删除此BadCase'}), 403
            
            _pid = badcase.project_id
            _title = badcase.title or ""
            _st = _badcase_status_str(badcase)
            _pn = _workflow_project_name(_pid)
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_badcase(badcase), badcase.creator_id
            )
            db.session.delete(badcase)
            db.session.commit()
            _cache_invalidate_plans(_pid)
            try:
                _schedule_workflow_notify(
                    "deleted",
                    "badcase",
                    badcase_id,
                    _title,
                    _pid,
                    _pn,
                    _st,
                    None,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] BadCase 删除通知失败: {_e}")
            
            return jsonify({'success': True, 'message': 'BadCase删除成功'})
        except Exception as e:
            db.session.rollback()
            print(f"删除BadCase失败: {e}")
            return jsonify({'success': False, 'error': '删除BadCase失败'}), 500
    
    # 更新
    print(f"=== 更新BadCase {badcase_id} ===")
    
    try:
        badcase = BadCase.query.get_or_404(badcase_id)
        
        if not has_project_permission(current_user.id, badcase.project_id):
            return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        print(f"更新数据: {data}")
        
        old_status = _badcase_status_str(badcase)
        
        # 更新BadCase字段
        if 'title' in data:
            badcase.title = data['title']
        if 'case_category' in data:
            badcase.case_category = data['case_category']
        if 'base_problem' in data:
            badcase.base_problem = (data['base_problem'] or '').strip()
        if 'badcase_result' in data:
            badcase.badcase_result = data['badcase_result']
        if 'answer' in data:
            badcase.answer = data['answer']
        if 'correct_answer' in data:
            badcase.correct_answer = data['correct_answer']
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
        if 'plan_id' in data:
            _pid = data.get('plan_id')
            if _pid in (None, '', 0, '0'):
                badcase.plan_id = None
            else:
                try:
                    badcase.plan_id = int(_pid)
                except (TypeError, ValueError):
                    pass
        if 'plan' in data:
            badcase.plan = data['plan']
            # 前端常同时传 plan 与 plan_id；若 plan_id 显式为空，仍应用 plan 里的数字 id
            _pid_missing = 'plan_id' not in data
            _pid_empty = (not _pid_missing) and data.get('plan_id') in (None, '', 0, '0')
            if _pid_missing or _pid_empty:
                pv = data.get('plan')
                if pv in (None, '', 'unplanned'):
                    badcase.plan_id = None
                else:
                    s = str(pv).strip()
                    if s.isdigit():
                        try:
                            badcase.plan_id = int(s)
                        except ValueError:
                            pass
        _try_repair_badcase_plan_id_from_legacy_plan_string(badcase)
        if 'document_type' in data:
            badcase.document_type = data['document_type']
        if 'attachments' in data:
            import json
            badcase.attachments = json.dumps(data['attachments']) if data['attachments'] else None
        if 'assigned_users' in data:
            badcase.assigned_users = data['assigned_users']
        
        db.session.commit()
        _cache_invalidate_plans(badcase.project_id)
        print("BadCase更新成功")
        try:
            new_status = _badcase_status_str(badcase)
            _ev = (
                "status_changed"
                if "status" in data and old_status != new_status
                else "updated"
            )
            _prev = (
                old_status
                if ("status" in data and old_status != new_status)
                else None
            )
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_badcase(badcase), badcase.creator_id
            )
            _schedule_workflow_notify(
                _ev,
                "badcase",
                badcase.id,
                badcase.title or "",
                badcase.project_id,
                _workflow_project_name(badcase.project_id),
                new_status,
                _prev,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] BadCase 更新通知失败: {_e}")
        
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
    
    old_status = _badcase_status_str(badcase)
    badcase.status = 'close'
    db.session.commit()
    try:
        _rec = _workflow_merge_creator_if_empty(
            _workflow_recipients_badcase(badcase), badcase.creator_id
        )
        _schedule_workflow_notify(
            "closed",
            "badcase",
            badcase.id,
            badcase.title or "",
            badcase.project_id,
            _workflow_project_name(badcase.project_id),
            "close",
            old_status,
            _rec,
            actor_id=current_user.id,
            actor_name=getattr(current_user, "name", "") or "",
        )
    except Exception as _e:
        print(f"[workflow_notify] BadCase 关闭通知失败: {_e}")
    
    return jsonify({'success': True})

# Card相关的API端点
@app.route('/api/cards', methods=['POST'])
@login_required
def api_create_card():
    """创建卡片"""
    print(f"=== 创建卡片 ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        # 获取参数
        title = data.get('title', '').strip()
        card_type_str = data.get('type', 'badcase')
        project_id = data.get('project_id')
        
        if not title:
            return jsonify({'success': False, 'error': '标题不能为空'}), 400
        
        if not project_id:
            return jsonify({'success': False, 'error': '项目ID不能为空'}), 400
        
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 将字符串转换为枚举
        try:
            card_type = CardType(card_type_str)
        except ValueError:
            return jsonify({'success': False, 'error': f'无效的卡片类型: {card_type_str}'}), 400
        
        # 创建卡片
        card = Card(
            title=title,
            type=card_type,
            project_id=project_id,
            creator_id=current_user.id,
            priority='p3'
        )
        # 与前端「当前选中迭代」对齐（可选）
        raw_pid = data.get('plan_id')
        if raw_pid is not None and raw_pid != '':
            try:
                pid = int(raw_pid)
                card.plan_id = pid if pid > 0 else None
            except (TypeError, ValueError):
                card.plan_id = None
        else:
            card.plan_id = None
        
        # 根据类型设置特定字段
        if card_type == CardType.BUG:
            card.severity = data.get('severity', 'medium')
            card.steps_to_reproduce = data.get('steps_to_reproduce')
            card.expected_result = data.get('expected_result')
            card.actual_result = data.get('actual_result')
            card.bug_type = data.get('bug_type')
            card.environment = data.get('environment')
            card.browser = data.get('browser')
            card.os = data.get('os')
        elif card_type == CardType.BADCASE:
            card.case_category = data.get('case_category')
            card.base_problem = data.get('base_problem')
            card.reproduction_steps = data.get('reproduction_steps')
            card.badcase_result = data.get('badcase_result')
            card.answer = data.get('answer')
            card.correct_answer = data.get('correct_answer')
            card.problem_reason = data.get('problem_reason')
            card.solution = data.get('solution')
        elif card_type == CardType.TESTCASE:
            card.case_type_test = data.get('case_type_test')
            card.test_type = data.get('test_type')
            card.preconditions = data.get('preconditions')
            card.steps = data.get('steps')
            card.remark = data.get('remark')
            card.requirement_id = data.get('requirement_id')
            card.related_defects = data.get('related_defects')
            card.baseline = data.get('baseline')
            card.estimated_time = data.get('estimated_time')
            card.actual_time = data.get('actual_time')
            card.remaining_time = data.get('remaining_time')
            card.version = data.get('version', 'v1')
        elif card_type == CardType.CARD:
            card.description = data.get('description')

        db.session.add(card)
        db.session.commit()
        _cache_invalidate_cards(project_id)
        
        print(f"✅ 卡片创建成功: {card.id}")
        return jsonify({'success': True, 'data': card.to_dict()})
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 创建卡片失败: {e}")
        return jsonify({'success': False, 'error': f'创建卡片失败: {str(e)}'}), 500


def _plan_subtree_ids_for_project(project_id: int, root_plan_id: int):
    """
    返回某项目下，以 root_plan_id 为根的迭代子树中全部计划 id（含根自身）。
    列表页选中顶层「迭代」时，前端传的是根计划 id；卡片 plan_id 往往在子计划下，
    仅用 Card.plan_id == 根 id 会漏数据。
    """
    rows = db.session.query(Plan.id, Plan.parent_id).filter(Plan.project_id == project_id).all()
    children_map = {}
    for pid, parent_id in rows:
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(pid)
    out = []
    stack = [root_plan_id]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        for cid in children_map.get(pid, ()):
            stack.append(cid)
    return out


@app.route('/api/projects/<int:project_id>/cards', methods=['GET'])
@login_required
def api_get_project_cards(project_id):
    """获取项目的卡片列表"""
    t0 = time.perf_counter()
    
    try:
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取卡片类型参数
        card_type = request.args.get('type')
        # 迭代计划下卡片列表：与前端 selectedPlan 对齐
        plan_id_param = _parse_query_optional_int64('plan_id')
        
        # 短期缓存 key（须包含 plan 维度，避免错命中）
        cache_key = ('cards', project_id, card_type or '', plan_id_param if plan_id_param is not None else '', page, per_page)
        cache_hit, cached = _cache_get(cache_key, ttl_s=0.5)
        if cache_hit:
            t_total = (time.perf_counter() - t0) * 1000
            print(f"[PERF] GET /api/projects/{project_id}/cards cache_hit total={t_total:.1f}ms", flush=True)
            return jsonify(cached)
        
        # 构建查询条件
        query = Card.query.filter_by(project_id=project_id)
        
        if plan_id_param is not None and plan_id_param > 0:
            plan_ids = _plan_subtree_ids_for_project(project_id, plan_id_param)
            if plan_ids:
                query = query.filter(Card.plan_id.in_(plan_ids))
        
        # 根据类型过滤
        if card_type:
            try:
                ct = CardType(card_type) if isinstance(card_type, str) else card_type
                query = query.filter(Card.type == ct)
            except Exception:
                query = query.filter(Card.type == card_type)
        
        # 分页查询
        pagination = query.order_by(Card.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        cards = [card.to_dict() for card in pagination.items]
        
        payload = {
            'success': True,
            'data': cards,
            'pagination': {
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page,
                'per_page': per_page
            }
        }
        _cache_set(cache_key, payload)
        
        t_total = (time.perf_counter() - t0) * 1000
        print(f"[PERF] GET /api/projects/{project_id}/cards sql total={t_total:.1f}ms count={len(cards)}", flush=True)
        return jsonify(payload)
    
    except Exception as e:
        print(f"❌ 获取卡片列表失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片列表失败: {str(e)}'}), 500


@app.route('/api/projects/<int:project_id>/cards/resolve-source', methods=['GET'])
@login_required
def api_resolve_project_card_by_source(project_id):
    """
    按 Card.source_id（及类型）精确定位卡片，不受「按 plan 分页拉卡」限制。
    用于 Bug/BadCase/TestCase 行缺 card_id 或 Card.plan_id 不在当前迭代子树时的列表 / 沙箱 Tab 导航。
    """
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403
    try:
        source_type = (request.args.get('source_type') or '').strip().lower().replace('-', '_')
        source_id = _parse_query_optional_int64('source_id')
        prefer_plan_id = _parse_query_optional_int64('prefer_plan_id')
        if source_id is None or source_id <= 0:
            return jsonify({'success': True, 'data': {'card': None}})
        if source_type in ('test_case',):
            kind = 'testcase'
        elif source_type in ('bad_case',):
            kind = 'badcase'
        elif source_type in ('bug', 'badcase', 'testcase'):
            kind = source_type
        else:
            return jsonify({'success': False, 'error': '无效的 source_type'}), 400
        card = _find_card_linking_source_record(
            project_id, source_id, kind, prefer_plan_id=prefer_plan_id
        )
        if card is None:
            return jsonify({'success': True, 'data': {'card': None}})
        return jsonify({'success': True, 'data': {'card': card.to_dict()}})
    except Exception as e:
        print(f"❌ resolve-source 卡片失败: {e}")
        return jsonify({'success': False, 'error': f'解析卡片失败: {str(e)}'}), 500


@app.route('/api/cards/<int:card_id>', methods=['GET'])
@login_required
def api_get_card_detail(card_id):
    """获取卡片详情"""
    print(f"=== 获取卡片详情 {card_id} ===")
    
    try:
        card = Card.query.get_or_404(card_id)
        repair_card_source_link_if_missing(card)
        db.session.refresh(card)

        # 检查权限
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权访问此卡片'}), 403
        
        return jsonify({'success': True, 'data': card.to_dict()})
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 获取卡片详情失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片详情失败: {str(e)}'}), 500

@app.route('/api/cards/<int:card_id>', methods=['PUT'])
@login_required
def api_update_card(card_id):
    """更新卡片"""
    print(f"=== 更新卡片 {card_id} ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        card = Card.query.get_or_404(card_id)
        
        # 检查权限
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权修改此卡片'}), 403
        
        old_card_type = card.type
        
        # 更新字段
        if 'title' in data:
            card.title = data['title']
        if 'priority' in data:
            card.priority = data['priority']
        if 'assignee_id' in data:
            card.assignee_id = data['assignee_id']
        if 'plan_id' in data:
            card.plan_id = _coerce_optional_bigint_json(data['plan_id'])
        if 'description' in data:
            card.description = data['description']
        
        # 更新类型字段
        if 'type' in data:
            try:
                new_type_str = data['type']
                # 转换下划线格式
                if new_type_str == 'test_case':
                    new_type_str = 'testcase'
                card.type = CardType(new_type_str)
            except ValueError:
                return jsonify({'success': False, 'error': f'无效的卡片类型: {data["type"]}'}), 400
        
        # 根据类型更新特定字段
        if card.type == CardType.BUG:
            if 'severity' in data:
                card.severity = data['severity']
            if 'steps_to_reproduce' in data:
                card.steps_to_reproduce = data['steps_to_reproduce']
            if 'expected_result' in data:
                card.expected_result = data['expected_result']
            if 'actual_result' in data:
                card.actual_result = data['actual_result']
            if 'bug_type' in data:
                card.bug_type = data['bug_type']
            if 'environment' in data:
                card.environment = data['environment']
            if 'browser' in data:
                card.browser = data['browser']
            if 'os' in data:
                card.os = data['os']
        elif card.type == CardType.BADCASE:
            if 'case_category' in data:
                card.case_category = data['case_category']
            if 'base_problem' in data:
                card.base_problem = data['base_problem']
            if 'reproduction_steps' in data:
                card.reproduction_steps = data['reproduction_steps']
            if 'badcase_result' in data:
                card.badcase_result = data['badcase_result']
            if 'answer' in data:
                card.answer = data['answer']
            if 'correct_answer' in data:
                card.correct_answer = data['correct_answer']
            if 'problem_reason' in data:
                card.problem_reason = data['problem_reason']
            if 'solution' in data:
                card.solution = data['solution']
        elif card.type == CardType.TESTCASE:
            if 'case_type_test' in data:
                card.case_type_test = data['case_type_test']
            if 'test_type' in data:
                card.test_type = data['test_type']
            if 'preconditions' in data:
                card.preconditions = data['preconditions']
            if 'steps' in data:
                card.steps = data['steps']
            if 'remark' in data:
                card.remark = data['remark']
            if 'requirement_id' in data:
                card.requirement_id = data['requirement_id']
            if 'related_defects' in data:
                card.related_defects = data['related_defects']
            if 'baseline' in data:
                card.baseline = data['baseline']
            if 'estimated_time' in data:
                card.estimated_time = data['estimated_time']
            if 'actual_time' in data:
                card.actual_time = data['actual_time']
            if 'remaining_time' in data:
                card.remaining_time = data['remaining_time']
            if 'version' in data:
                card.version = data['version']
        
        _apply_card_type_change_defaults(card, old_card_type)
        
        card.updated_at = datetime.utcnow()
        db.session.commit()
        _cache_invalidate_cards(card.project_id)
        
        print(f"✅ 卡片更新成功: {card.id}")
        return jsonify({'success': True, 'data': card.to_dict()})
    
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        print(f"❌ 更新卡片失败: {e}")
        return jsonify({'success': False, 'error': f'更新卡片失败: {str(e)}'}), 500

@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
@login_required
def api_delete_card(card_id):
    """删除卡片。Bug / BadCase / TestCase 类型卡片若仍关联源表记录，需二次确认后级联删除。"""
    print(f"=== 删除卡片 {card_id} ===")

    try:
        card = Card.query.get_or_404(card_id)

        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权删除此卡片'}), 403

        _pid = card.project_id
        payload = request.get_json(silent=True) or {}
        confirm_cascade = any(
            [
                payload.get('confirm_cascade_sources') is True,
                payload.get('confirm_cascade_badcases') is True,
                payload.get('confirm_cascade_bugs') is True,
                payload.get('confirm_cascade_testcases') is True,
            ]
        )

        ctype = getattr(card, 'type', None)
        linked_badcases = []
        linked_bugs = []
        linked_testcases = []
        source_kind = None

        if ctype == CardType.BADCASE:
            linked_badcases = _collect_badcases_for_badcase_card(card)
            if linked_badcases:
                source_kind = 'badcase'
        elif ctype == CardType.BUG:
            linked_bugs = _collect_bugs_for_bug_card(card)
            if linked_bugs:
                source_kind = 'bug'
        elif ctype == CardType.TESTCASE:
            linked_testcases = _collect_testcases_for_testcase_card(card)
            if linked_testcases:
                source_kind = 'testcase'

        def _linked_items_payload(rows, title_attr='title'):
            out = []
            for r in rows:
                tid = getattr(r, 'id', None)
                if tid is None:
                    continue
                try:
                    tid_s = _json_snowflake_id(int(tid))
                except (TypeError, ValueError):
                    continue
                tv = getattr(r, title_attr, None) or ''
                out.append({'id': tid_s, 'title': (str(tv) or '')[:200]})
            return out

        need_confirm = (
            (linked_badcases or linked_bugs or linked_testcases) and not confirm_cascade
        )
        if need_confirm:
            rows = linked_badcases or linked_bugs or linked_testcases
            n = len(rows)
            sk = source_kind or 'badcase'
            err_cn = {
                'badcase': f'该 BadCase 卡片仍关联 {n} 条 BadCase，删除将永久删除源记录（含评论）及待审核修改。',
                'bug': f'该 Bug 卡片仍关联 {n} 条缺陷，删除将永久删除这些 Bug（含评论）及待审核修改。',
                'testcase': f'该测试用例卡片仍关联 {n} 条用例，删除将永久删除这些 TestCase 及待审核修改。',
            }.get(sk, f'该卡片仍关联 {n} 条源表记录。')
            return (
                jsonify(
                    {
                        'success': False,
                        'code': 'CASCADE_CARD_SOURCES_REQUIRED',
                        'source_kind': sk,
                        'error': err_cn + ' 请确认后请求体带上 confirm_cascade_sources=true 重试。',
                        'count': n,
                        'linked_items': _linked_items_payload(rows),
                        'linked_badcases': _linked_items_payload(linked_badcases)
                        if linked_badcases
                        else [],
                        'linked_bugs': _linked_items_payload(linked_bugs) if linked_bugs else [],
                        'linked_testcases': _linked_items_payload(linked_testcases)
                        if linked_testcases
                        else [],
                    }
                ),
                409,
            )

        deleted_bc = deleted_bug = deleted_tc = 0

        if linked_badcases and confirm_cascade:
            ids = [int(bc.id) for bc in linked_badcases]
            try:
                Comment.query.filter(Comment.badcase_id.in_(ids)).delete(synchronize_session=False)
            except Exception as _ce:
                print(f"[DELETE-CARD] 清理 Comment 失败（继续）: {_ce}", flush=True)
            try:
                _delete_diff_review_state_rows(_pid, 'badcase', ids, None)
            except Exception as _de:
                print(f"[DELETE-CARD] 清理 diff_review_state(badcase) 失败（继续）: {_de}", flush=True)
            try:
                BadCase.query.filter(BadCase.id.in_(ids)).delete(synchronize_session=False)
                deleted_bc = len(ids)
            except Exception as _be:
                db.session.rollback()
                print(f"❌ 级联删除 BadCase 失败: {_be}", flush=True)
                return jsonify({'success': False, 'error': f'级联删除 BadCase 失败: {str(_be)}'}), 500
            print(f"[DELETE-CARD] 卡片 {card_id} 级联删除 {deleted_bc} 条 bad_case", flush=True)

        if linked_bugs and confirm_cascade:
            ids = [int(b.id) for b in linked_bugs]
            try:
                BugComment.query.filter(BugComment.bug_id.in_(ids)).delete(synchronize_session=False)
            except Exception as _ce:
                print(f"[DELETE-CARD] 清理 bug_comment 失败（继续）: {_ce}", flush=True)
            try:
                _delete_diff_review_state_rows(_pid, 'bug', ids, None)
            except Exception as _de:
                print(f"[DELETE-CARD] 清理 diff_review_state(bug) 失败（继续）: {_de}", flush=True)
            try:
                Bug.query.filter(Bug.id.in_(ids)).delete(synchronize_session=False)
                deleted_bug = len(ids)
            except Exception as _be:
                db.session.rollback()
                print(f"❌ 级联删除 Bug 失败: {_be}", flush=True)
                return jsonify({'success': False, 'error': f'级联删除 Bug 失败: {str(_be)}'}), 500
            print(f"[DELETE-CARD] 卡片 {card_id} 级联删除 {deleted_bug} 条 bug", flush=True)

        if linked_testcases and confirm_cascade:
            ids = [int(tc.id) for tc in linked_testcases]
            try:
                _delete_diff_review_state_rows(_pid, 'testcase', ids, None)
            except Exception as _de:
                print(f"[DELETE-CARD] 清理 diff_review_state(testcase) 失败（继续）: {_de}", flush=True)
            try:
                TestCase.query.filter(TestCase.id.in_(ids)).delete(synchronize_session=False)
                deleted_tc = len(ids)
            except Exception as _be:
                db.session.rollback()
                print(f"❌ 级联删除 TestCase 失败: {_be}", flush=True)
                return jsonify({'success': False, 'error': f'级联删除 TestCase 失败: {str(_be)}'}), 500
            print(f"[DELETE-CARD] 卡片 {card_id} 级联删除 {deleted_tc} 条 test_case", flush=True)

        try:
            CardPlanRelation.query.filter(CardPlanRelation.card_id == int(card_id)).delete(
                synchronize_session=False
            )
        except Exception as _re:
            print(f"[DELETE-CARD] 清理 card_plan_relation 失败（继续）: {_re}", flush=True)

        db.session.delete(card)
        db.session.commit()
        _cache_invalidate_cards(_pid)
        _cache_invalidate_plans(_pid)

        print(f"✅ 卡片删除成功: {card.id}")
        return jsonify(
            {
                'success': True,
                'message': '卡片删除成功',
                'deleted_linked_badcases': deleted_bc,
                'deleted_linked_bugs': deleted_bug,
                'deleted_linked_testcases': deleted_tc,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        print(f"❌ 删除卡片失败: {e}")
        return jsonify({'success': False, 'error': f'删除卡片失败: {str(e)}'}), 500


def _user_name_map(user_ids):
    ids = [int(x) for x in user_ids if x is not None]
    if not ids:
        return {}
    rows = db.session.query(User.id, User.name).filter(User.id.in_(ids)).all()
    return {uid: name for uid, name in rows}


@app.route('/api/projects/<int:project_id>/global-search', methods=['GET'])
@login_required
def api_project_global_search(project_id):
    """项目内全局搜索：计划、卡片、BadCase、Bug、测试用例（单次请求、库内 ilike 过滤）"""
    try:
        query_text = (request.args.get('query') or '').strip()
        per_type = min(max(request.args.get('per_type', 30, type=int), 1), 50)

        if not query_text:
            return jsonify({'success': True, 'results': []})

        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403

        pattern = f'%{query_text}%'
        results = []

        # 迭代计划
        plan_rows = (
            Plan.query.filter(Plan.project_id == project_id)
            .filter(db.or_(Plan.name.ilike(pattern), Plan.description.ilike(pattern)))
            .order_by(Plan.updated_at.desc())
            .limit(per_type)
            .all()
        )
        for p in plan_rows:
            results.append(
                {
                    'type': 'plan',
                    'id': _json_snowflake_id(p.id),
                    'title': p.name or f'Plan#{p.id}',
                    'status': p.status or '',
                    'status_text': p.status or '',
                    'details': [],
                }
            )

        # 迭代卡片
        card_rows = (
            Card.query.filter(Card.project_id == project_id)
            .filter(Card.type.in_([CardType.BUG, CardType.BADCASE, CardType.TESTCASE]))
            .filter(db.or_(Card.title.ilike(pattern), Card.description.ilike(pattern)))
            .order_by(Card.updated_at.desc())
            .limit(per_type)
            .all()
        )
        card_assignee_map = _user_name_map([c.assignee_id for c in card_rows])
        for c in card_rows:
            ctype = c.type.value if isinstance(c.type, CardType) else str(c.type or '')
            results.append(
                {
                    'type': 'card',
                    'groupKey': ctype if ctype in ('bug', 'badcase', 'testcase') else 'card',
                    'id': _json_snowflake_id(c.id),
                    'title': c.title,
                    'plan_id': _json_snowflake_id(c.plan_id),
                    'cardType': ctype,
                    'status': '',
                    'status_text': '',
                    'assignee': card_assignee_map.get(c.assignee_id) if c.assignee_id else None,
                    'details': [],
                }
            )

        # BadCase 实体
        bc_rows = (
            BadCase.query.filter(BadCase.project_id == project_id)
            .filter(
                db.or_(
                    BadCase.title.ilike(pattern),
                    BadCase.case_category.ilike(pattern),
                    BadCase.base_problem.ilike(pattern),
                    BadCase.reproduction_steps.ilike(pattern),
                    BadCase.answer.ilike(pattern),
                    BadCase.correct_answer.ilike(pattern),
                )
            )
            .order_by(BadCase.updated_at.desc())
            .limit(per_type)
            .all()
        )
        for bc in bc_rows:
            st = _badcase_status_str(bc)
            results.append(
                {
                    'type': 'badcase',
                    'groupKey': 'badcase',
                    'id': _json_snowflake_id(bc.id),
                    'title': bc.title or bc.case_category or f'BadCase#{bc.id}',
                    'status': st or 'open',
                    'status_text': st,
                    'plan_id': _json_snowflake_id(bc.plan_id),
                    'card_id': _json_snowflake_id(getattr(bc, 'card_id', None)),
                    'details': [],
                }
            )

        # Bug 实体
        bug_rows = (
            Bug.query.filter(Bug.project_id == project_id)
            .filter(
                db.or_(
                    Bug.title.ilike(pattern),
                    Bug.description.ilike(pattern),
                    Bug.bug_type.ilike(pattern),
                )
            )
            .order_by(Bug.updated_at.desc())
            .limit(per_type)
            .all()
        )
        bug_assignee_map = _user_name_map([b.assignee_id for b in bug_rows])
        for b in bug_rows:
            results.append(
                {
                    'type': 'bug',
                    'groupKey': 'bug',
                    'id': _json_snowflake_id(b.id),
                    'title': b.title,
                    'status': b.status or 'open',
                    'status_text': b.status or '',
                    'plan_id': _json_snowflake_id(b.plan_id),
                    'card_id': _json_snowflake_id(b.card_id),
                    'assignee': bug_assignee_map.get(b.assignee_id) if b.assignee_id else None,
                    'details': [],
                }
            )

        # 测试用例实体
        tc_rows = (
            TestCase.query.filter(TestCase.project_id == project_id)
            .filter(
                db.or_(
                    TestCase.title.ilike(pattern),
                    TestCase.case_type.ilike(pattern),
                    TestCase.remark.ilike(pattern),
                )
            )
            .order_by(TestCase.updated_at.desc())
            .limit(per_type)
            .all()
        )
        tc_assignee_map = _user_name_map([t.assignee_id for t in tc_rows])
        for t in tc_rows:
            st = _testcase_status_str(t)
            results.append(
                {
                    'type': 'testcase',
                    'groupKey': 'testcase',
                    'id': _json_snowflake_id(t.id),
                    'title': t.title,
                    'status': st or 'active',
                    'status_text': st,
                    'plan_id': _json_snowflake_id(t.plan_id),
                    'card_id': _json_snowflake_id(getattr(t, 'card_id', None)),
                    'assignee': tc_assignee_map.get(t.assignee_id) if t.assignee_id else None,
                    'details': [],
                }
            )

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        print(f'❌ 全局搜索失败: {e}')
        return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'}), 500


@app.route('/api/cards/search', methods=['GET'])
@login_required
def api_search_cards():
    """全局搜索卡片"""
    print(f"=== 全局搜索卡片 ===")
    
    try:
        query_text = request.args.get('query', '').strip()
        types_param = request.args.get('types', 'bug,badcase,testcase')
        project_id = request.args.get('project_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        if not query_text:
            return jsonify({
                'success': True,
                'data': {'results': [], 'counts': {}}
            })
        
        # 解析类型
        types = [t.strip() for t in types_param.split(',') if t.strip()]
        
        # 构建基础查询
        base_query = Card.query
        
        # 项目过滤
        if project_id:
            base_query = base_query.filter(Card.project_id == project_id)
        
        # 类型过滤
        if types:
            base_query = base_query.filter(Card.type.in_(types))
        
        # 全文搜索 (标题和描述)
        search_pattern = f'%{query_text}%'
        base_query = base_query.filter(
            db.or_(
                Card.title.ilike(search_pattern),
                Card.description.ilike(search_pattern)
            )
        )
        
        # 分页查询
        pagination = base_query.order_by(Card.updated_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        results = [card.to_dict() for card in pagination.items]
        
        assignee_map = _user_name_map([r.get('assignee_id') for r in results])
        for result in results:
            aid = result.get('assignee_id')
            if aid and assignee_map.get(aid):
                result['assignee'] = assignee_map[aid]

        counts = {}
        if (request.args.get('include_counts') or '').strip().lower() in ('1', 'true', 'yes'):
            counts_query = Card.query
            if project_id:
                counts_query = counts_query.filter(Card.project_id == project_id)
            for t in types:
                counts[t] = counts_query.filter(Card.type == t).filter(
                    db.or_(
                        Card.title.ilike(search_pattern),
                        Card.description.ilike(search_pattern),
                    )
                ).count()
        
        print(f"✅ 搜索完成，找到 {len(results)} 条结果")
        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'counts': counts,
                'pagination': {
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'current_page': page,
                    'per_page': per_page
                }
            }
        })
    
    except Exception as e:
        print(f"❌ 搜索卡片失败: {e}")
        return jsonify({'success': False, 'error': f'搜索卡片失败: {str(e)}'}), 500

@app.route('/api/cards/<int:card_id>/move', methods=['POST'])
@login_required
def api_move_card(card_id):
    """移动卡片到指定计划"""
    print(f"=== 移动卡片 {card_id} ===")
    
    try:
        card = Card.query.get_or_404(card_id)
        
        # 检查权限
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权移动此卡片'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        target_plan_id = data.get('plan_id')  # None表示移至未计划
        
        # 验证目标计划存在（如果指定了）
        if target_plan_id is not None and str(target_plan_id).strip() != '':
            tid = _coerce_optional_bigint_json(target_plan_id)
            plan = Plan.query.get(tid) if tid is not None else None
            if not plan:
                return jsonify({'success': False, 'error': '目标计划不存在'}), 404
            if plan.project_id != card.project_id:
                return jsonify({'success': False, 'error': '目标计划不属于同一项目'}), 400
            target_plan_id = tid
        else:
            target_plan_id = None
        
        old_plan_id = card.plan_id
        card.plan_id = target_plan_id
        card.updated_at = datetime.utcnow()
        
        db.session.commit()
        _cache_invalidate_cards(card.project_id)
        
        print(f"✅ 卡片移动成功: {card.id}, 从计划 {old_plan_id} -> {target_plan_id}")
        return jsonify({
            'success': True,
            'data': card.to_dict(),
            'message': f'卡片已移动至{"计划 " + str(target_plan_id) if target_plan_id else "未计划"}'
        })
    
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        print(f"❌ 移动卡片失败: {e}")
        return jsonify({'success': False, 'error': f'移动卡片失败: {str(e)}'}), 500

# ==================== 卡片类型管理 API ====================

@app.route('/api/card-types', methods=['GET'])
@login_required
def api_get_card_types():
    """获取卡片类型列表"""
    print(f"=== 获取卡片类型列表 ===")
    
    try:
        project_id = request.args.get('project_id', type=int)
        
        query = CardTypeDefinition.query
        
        if project_id:
            query = query.filter(CardTypeDefinition.project_id == project_id)
        
        # 只返回启用的类型
        query = query.filter(CardTypeDefinition.is_active == True)
        
        types = query.order_by(CardTypeDefinition.sort_order.asc()).all()
        
        return jsonify({
            'success': True,
            'data': [t.to_dict() for t in types]
        })
    
    except Exception as e:
        print(f"❌ 获取卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片类型失败: {str(e)}'}), 500

@app.route('/api/card-types', methods=['POST'])
@login_required
def api_create_card_type():
    """创建卡片类型"""
    print(f"=== 创建卡片类型 ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        project_id = data.get('project_id')
        name = data.get('name')
        code = data.get('code')
        
        if not all([project_id, name, code]):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400
        
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权创建此卡片类型'}), 403
        
        # 检查code唯一性
        existing = CardTypeDefinition.query.filter_by(code=code).first()
        if existing:
            return jsonify({'success': False, 'error': '类型代码已存在'}), 400
        
        card_type = CardTypeDefinition(
            project_id=project_id,
            name=name,
            code=code,
            icon=data.get('icon'),
            color=data.get('color'),
            description=data.get('description'),
            fields_config=data.get('fields_config'),
            status_config=data.get('status_config'),
            sort_order=data.get('sort_order', 0)
        )
        
        db.session.add(card_type)
        db.session.commit()
        
        print(f"✅ 卡片类型创建成功: {card_type.id}")
        return jsonify({
            'success': True,
            'data': card_type.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 创建卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'创建卡片类型失败: {str(e)}'}), 500

@app.route('/api/card-types/<int:type_id>', methods=['PUT'])
@login_required
def api_update_card_type(type_id):
    """更新卡片类型"""
    print(f"=== 更新卡片类型 {type_id} ===")
    
    try:
        card_type = CardTypeDefinition.query.get_or_404(type_id)
        
        if not has_project_permission(current_user.id, card_type.project_id):
            return jsonify({'success': False, 'error': '无权修改此卡片类型'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        # 更新字段
        for field in ['name', 'icon', 'color', 'description', 'fields_config', 'status_config', 'sort_order', 'is_active']:
            if field in data:
                setattr(card_type, field, data[field])
        
        db.session.commit()
        
        print(f"✅ 卡片类型更新成功: {card_type.id}")
        return jsonify({
            'success': True,
            'data': card_type.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 更新卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'更新卡片类型失败: {str(e)}'}), 500

@app.route('/api/card-types/<int:type_id>', methods=['DELETE'])
@login_required
def api_delete_card_type(type_id):
    """删除卡片类型"""
    print(f"=== 删除卡片类型 {type_id} ===")
    
    try:
        card_type = CardTypeDefinition.query.get_or_404(type_id)
        
        if not has_project_permission(current_user.id, card_type.project_id):
            return jsonify({'success': False, 'error': '无权删除此卡片类型'}), 403
        
        # 软删除
        card_type.is_active = False
        db.session.commit()
        
        print(f"✅ 卡片类型删除成功: {card_type.id}")
        return jsonify({
            'success': True,
            'message': '卡片类型删除成功'
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 删除卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'删除卡片类型失败: {str(e)}'}), 500

# ==================== 卡片计划关联关系 API ====================

@app.route('/api/card-plan-relations', methods=['GET'])
@login_required
def api_get_card_plan_relations():
    """获取卡片与计划的关联关系"""
    print(f"=== 获取卡片计划关联关系 ===")
    
    try:
        card_id = _parse_query_optional_int64('card_id')
        plan_id = _parse_query_optional_int64('plan_id')
        include_removed = request.args.get('include_removed', 'false').lower() == 'true'
        
        query = CardPlanRelation.query
        
        if card_id:
            query = query.filter(CardPlanRelation.card_id == card_id)
        if plan_id:
            query = query.filter(CardPlanRelation.plan_id == plan_id)
        if not include_removed:
            query = query.filter(CardPlanRelation.removed_at.is_(None))
        
        relations = query.order_by(CardPlanRelation.sort_order.asc()).all()
        
        return jsonify({
            'success': True,
            'data': [r.to_dict() for r in relations]
        })
    
    except Exception as e:
        print(f"❌ 获取关联关系失败: {e}")
        return jsonify({'success': False, 'error': f'获取关联关系失败: {str(e)}'}), 500

@app.route('/api/card-plan-relations', methods=['POST'])
@login_required
def api_create_card_plan_relation():
    """创建卡片与计划的关联"""
    print(f"=== 创建卡片计划关联 ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        card_id = data.get('card_id')
        plan_id = data.get('plan_id')
        
        if not all([card_id, plan_id]):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400
        
        # 检查卡片是否存在
        card = Card.query.get(card_id)
        if not card:
            return jsonify({'success': False, 'error': '卡片不存在'}), 404
        
        # 检查计划是否存在
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查是否已存在关联
        relation_type = data.get('relation_type', 'primary')
        existing = CardPlanRelation.query.filter_by(
            card_id=card_id,
            plan_id=plan_id,
            relation_type=relation_type
        ).filter(CardPlanRelation.removed_at.is_(None)).first()
        
        if existing:
            return jsonify({'success': False, 'error': '关联关系已存在'}), 400
        
        relation = CardPlanRelation(
            card_id=card_id,
            plan_id=plan_id,
            relation_type=relation_type,
            status_in_plan=data.get('status_in_plan'),
            sort_order=data.get('sort_order', 0)
        )
        
        db.session.add(relation)
        db.session.commit()
        
        print(f"✅ 关联关系创建成功: {relation.id}")
        return jsonify({
            'success': True,
            'data': relation.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 创建关联关系失败: {e}")
        return jsonify({'success': False, 'error': f'创建关联关系失败: {str(e)}'}), 500

@app.route('/api/card-plan-relations/<int:relation_id>', methods=['DELETE'])
@login_required
def api_delete_card_plan_relation(relation_id):
    """删除卡片与计划的关联（软删除）"""
    print(f"=== 删除卡片计划关联 {relation_id} ===")
    
    try:
        relation = CardPlanRelation.query.get_or_404(relation_id)
        
        # 软删除
        relation.removed_at = datetime.utcnow()
        db.session.commit()
        
        print(f"✅ 关联关系删除成功: {relation.id}")
        return jsonify({
            'success': True,
            'message': '关联关系删除成功'
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 删除关联关系失败: {e}")
        return jsonify({'success': False, 'error': f'删除关联关系失败: {str(e)}'}), 500

@app.route('/api/cards/<int:card_id>/history', methods=['GET'])
@login_required
def api_get_card_plan_history(card_id):
    """获取卡片的计划变更历史"""
    print(f"=== 获取卡片 {card_id} 的计划变更历史 ===")
    
    try:
        card = Card.query.get_or_404(card_id)
        
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权查看此卡片'}), 403
        
        # 获取该卡片的所有关联关系（包括已移除的）
        relations = CardPlanRelation.query.filter_by(card_id=card_id).order_by(
            CardPlanRelation.added_at.desc()
        ).all()
        
        # 获取计划信息
        history = []
        for rel in relations:
            plan = Plan.query.get(rel.plan_id)
            if plan:
                history.append({
                    'relation_id': rel.id,
                    'plan_id': _json_snowflake_id(rel.plan_id),
                    'plan_name': plan.name,
                    'relation_type': rel.relation_type,
                    'status_in_plan': rel.status_in_plan,
                    'added_at': rel.added_at.isoformat() if rel.added_at else None,
                    'removed_at': rel.removed_at.isoformat() if rel.removed_at else None,
                    'is_current': rel.removed_at is None and rel.plan_id == card.plan_id
                })
        
        return jsonify({
            'success': True,
            'data': history
        })
    
    except Exception as e:
        print(f"❌ 获取卡片历史失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片历史失败: {str(e)}'}), 500

# CORS已在上面配置，这里不需要重复配置

def _adapt_create_table_columns_for_dialect(columns):
    """CREATE TABLE 列定义：SQLite 用 AUTOINCREMENT，MySQL 用 AUTO_INCREMENT。"""
    dialect = (db.engine.dialect.name or "").lower()
    if dialect != "mysql":
        return columns
    return [
        c.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER PRIMARY KEY AUTO_INCREMENT")
        .replace("AUTOINCREMENT", "AUTO_INCREMENT")
        for c in columns
    ]


def sync_database_schema():
    """同步数据库表结构，确保与代码中的模型完全一致"""
    try:
        print("开始同步数据库表结构...")
        
        # 获取数据库检查器
        inspector = inspect(db.engine)

        # === 兼容迁移：bad_case 字段重命名（避免 answer/correct_answer 混淆） ===
        # correct_answer      -> answer
        # correct_answer_final-> correct_answer
        def _migrate_bad_case_answer_fields():
            try:
                cols = inspector.get_columns('bad_case')
                col_names = {c.get('name') for c in (cols or [])}
                # 先把 correct_answer 重命名为 answer
                if 'correct_answer' in col_names and 'answer' not in col_names:
                    print("[DB] 迁移: bad_case.correct_answer -> bad_case.answer")
                    db.session.execute(text('ALTER TABLE bad_case RENAME COLUMN correct_answer TO answer'))
                    db.session.commit()
                    cols = inspector.get_columns('bad_case')
                    col_names = {c.get('name') for c in (cols or [])}
                # 再把 correct_answer_final 重命名为 correct_answer
                if 'correct_answer_final' in col_names and 'correct_answer' not in col_names:
                    print("[DB] 迁移: bad_case.correct_answer_final -> bad_case.correct_answer")
                    db.session.execute(text('ALTER TABLE bad_case RENAME COLUMN correct_answer_final TO correct_answer'))
                    db.session.commit()
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[DB] ⚠️ bad_case 字段迁移失败(可忽略/手动处理): {e}")

        def _migrate_bug_plan_id_nullable():
            """历史库 bug.plan_id 常为 NOT NULL，与 ORM Bug.plan_id nullable=True /「未计划 Bug」不一致，会导致 plan_id=NULL 插入失败。"""
            try:
                insp = inspect(db.engine)
                if not insp.has_table('bug'):
                    return
                cols = insp.get_columns('bug')
                plan_col = next((c for c in cols if c.get('name') == 'plan_id'), None)
                if not plan_col:
                    return
                if plan_col.get('nullable', True):
                    return
                dialect = (db.engine.dialect.name or '').lower()
                if dialect == 'mysql':
                    print("[DB] 迁移: bug.plan_id 允许 NULL（未计划 Bug / create 预览 plan_id 为空）")
                    db.session.execute(text('ALTER TABLE bug MODIFY COLUMN plan_id BIGINT NULL'))
                    db.session.commit()
                elif dialect in ('postgresql', 'postgres'):
                    db.session.execute(text('ALTER TABLE bug ALTER COLUMN plan_id DROP NOT NULL'))
                    db.session.commit()
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[DB] ⚠️ bug.plan_id 可空迁移失败(可手动执行 ALTER): {e}")

        _migrate_bad_case_answer_fields()
        _migrate_bug_plan_id_nullable()

        def _migrate_badcase_testcase_card_id_columns():
            """bad_case / test_case 增加 card_id，并从已有 Card.source_type/source_id 回填。"""
            try:

                def _ensure_col(table: str) -> None:
                    ins = inspect(db.engine)
                    if not ins.has_table(table):
                        return
                    cols = {c.get("name") for c in (ins.get_columns(table) or [])}
                    if "card_id" in cols:
                        return
                    dialect = (db.engine.dialect.name or "").lower()
                    print(f"[DB] 迁移: {table}.card_id 可空 BIGINT（雪花/跨表 id）")
                    if dialect == "mysql":
                        db.session.execute(
                            text(f"ALTER TABLE {table} ADD COLUMN card_id BIGINT NULL")
                        )
                    else:
                        db.session.execute(
                            text(f"ALTER TABLE {table} ADD COLUMN card_id INTEGER")
                        )
                    db.session.commit()

                _ensure_col("bad_case")
                _ensure_col("test_case")

                # 从 Card 映射回填源表 card_id（老数据仅有 source_* 时）
                if inspect(db.engine).has_table("bad_case") and inspect(
                    db.engine
                ).has_table("card"):
                    qcards = (
                        Card.query.filter(
                            Card.type == CardType.BADCASE,
                            or_(
                                Card.source_type == "badcase",
                                Card.source_type == "bad_case",
                            ),
                            Card.source_id.isnot(None),
                        )
                        .all()
                    )
                    nbc = 0
                    for c in qcards:
                        try:
                            bid = int(c.source_id)
                        except (TypeError, ValueError):
                            continue
                        bc = BadCase.query.get(bid)
                        if (
                            bc
                            and int(bc.project_id) == int(c.project_id)
                            and (getattr(bc, "card_id", None) in (None, 0))
                        ):
                            bc.card_id = int(c.id)
                            nbc += 1
                    if nbc:
                        db.session.commit()
                        print(f"[DB] 回填 bad_case.card_id 自 Card: {nbc} 条", flush=True)

                if inspect(db.engine).has_table("test_case") and inspect(
                    db.engine
                ).has_table("card"):
                    qcards = (
                        Card.query.filter(
                            Card.type == CardType.TESTCASE,
                            or_(
                                Card.source_type == "testcase",
                                Card.source_type == "test_case",
                            ),
                            Card.source_id.isnot(None),
                        )
                        .all()
                    )
                    ntc = 0
                    for c in qcards:
                        try:
                            tid = int(c.source_id)
                        except (TypeError, ValueError):
                            continue
                        tc = TestCase.query.get(tid)
                        if (
                            tc
                            and int(tc.project_id) == int(c.project_id)
                            and (getattr(tc, "card_id", None) in (None, 0))
                        ):
                            tc.card_id = int(c.id)
                            ntc += 1
                    if ntc:
                        db.session.commit()
                        print(f"[DB] 回填 test_case.card_id 自 Card: {ntc} 条", flush=True)
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(
                    f"[DB] ⚠️ bad_case/test_case card_id 迁移失败(可手动 ALTER): {e}",
                    flush=True,
                )

        _migrate_badcase_testcase_card_id_columns()

        def _migrate_mysql_entity_ids_bigint_for_snowflake():
            """MySQL：将 Bug/Card/BadCase/TestCase/Plan 主键及引用列扩为 BIGINT，便于雪花 id。需 SNOWFLAKE_ENTITY_PK_MIGRATE=1。"""
            if (db.engine.dialect.name or "").lower() != "mysql":
                return
            if (os.getenv("SNOWFLAKE_ENTITY_PK_MIGRATE") or "").strip() != "1":
                return
            stmts = [
                "ALTER TABLE bug MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE bad_case MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE test_case MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE card MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE card_plan_relation MODIFY COLUMN plan_id BIGINT NOT NULL",
                "ALTER TABLE diff_review_state MODIFY COLUMN plan_id BIGINT NULL",
                "ALTER TABLE bug MODIFY COLUMN card_id BIGINT NULL",
                "ALTER TABLE bad_case MODIFY COLUMN card_id BIGINT NULL",
                "ALTER TABLE test_case MODIFY COLUMN card_id BIGINT NULL",
                "ALTER TABLE card MODIFY COLUMN source_id BIGINT NULL",
                "ALTER TABLE comment MODIFY COLUMN badcase_id BIGINT NOT NULL",
                "ALTER TABLE bug_comment MODIFY COLUMN bug_id BIGINT NOT NULL",
                "ALTER TABLE card_plan_relation MODIFY COLUMN card_id BIGINT NOT NULL",
                "ALTER TABLE diff_review_state MODIFY COLUMN target_id BIGINT NOT NULL",
                "ALTER TABLE workflow_in_app_notification MODIFY COLUMN entity_id BIGINT NOT NULL",
                "ALTER TABLE bug MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE bad_case MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE test_case MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE card MODIFY COLUMN id BIGINT NOT NULL",
                "ALTER TABLE plan MODIFY COLUMN parent_id BIGINT NULL",
                "ALTER TABLE plan MODIFY COLUMN id BIGINT NOT NULL",
            ]
            for sql in stmts:
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"[DB] 雪花列迁移 OK: {sql}", flush=True)
                except Exception as ex:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    print(f"[DB] 雪花列迁移跳过: {sql} ({ex})", flush=True)

        _migrate_mysql_entity_ids_bigint_for_snowflake()

        def _warn_mysql_int_entity_pk_if_needed():
            if (db.engine.dialect.name or "").lower() != "mysql":
                return
            if (os.getenv("SNOWFLAKE_ENTITY_PK_MIGRATE") or "").strip() == "1":
                return
            try:
                insp = inspect(db.engine)
                if not insp.has_table("bug"):
                    return
                for c in insp.get_columns("bug") or []:
                    if c.get("name") != "id":
                        continue
                    t = c.get("type")
                    tn = (getattr(t, "__visit_name__", None) or str(t)).lower()
                    if "bigint" in tn:
                        return
                    print(
                        "[DB] 提示：Bug/Card/Plan 等主键已改为应用层雪花；MySQL 表 bug.id 等仍为整型时，"
                        "请先设环境变量 SNOWFLAKE_ENTITY_PK_MIGRATE=1 启动一次以执行 ALTER 扩 BIGINT，"
                        "否则新插入雪花 id 会失败。",
                        flush=True,
                    )
                    break
            except Exception:
                pass

        _warn_mysql_int_entity_pk_if_needed()

        # 重要：SQLite ALTER TABLE 后 inspector 可能缓存旧列信息，重新创建 inspector 避免重复加列
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
                    # 与 ORM Project.login_configs 对齐；缺列时由上方向现有表 ADD COLUMN
                    'login_configs TEXT',
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
                    'id BIGINT PRIMARY KEY',
                    'project_id INT NOT NULL',
                    'plan_id BIGINT',
                    'creator_id INT NOT NULL',
                    'title VARCHAR(200)',
                    'case_category VARCHAR(100) NOT NULL',
                    'base_problem TEXT NOT NULL',
                    'reproduction_steps TEXT',
                    'badcase_result TEXT NOT NULL',
                    'answer TEXT NOT NULL',
                    'correct_answer TEXT',
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
                    'badcase_id BIGINT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'source_message_id INT',
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
                    'id BIGINT PRIMARY KEY',
                    'name VARCHAR(200) NOT NULL',
                    'description TEXT',
                    'status VARCHAR(20) DEFAULT "active"',
                    'priority VARCHAR(10) DEFAULT "medium"',
                    'is_pinned BOOLEAN DEFAULT FALSE',
                    'start_date DATE',
                    'end_date DATE',
                    'progress FLOAT DEFAULT 0.0',
                    'parent_id BIGINT',
                    'project_id INT NOT NULL',
                    'creator_id INT NOT NULL',
                    'assignee_id INT',
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
                    'id BIGINT PRIMARY KEY',
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
                    'plan_id BIGINT',
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
                    'bug_id BIGINT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'source_message_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (bug_id) REFERENCES bug(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'test_case_comment': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'test_case_id BIGINT NOT NULL',
                    'user_id INT NOT NULL',
                    'content TEXT NOT NULL',
                    'source_message_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (test_case_id) REFERENCES test_case(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'test_case': {
                'columns': [
                    'id BIGINT PRIMARY KEY',
                    'title VARCHAR(200) NOT NULL',
                    'status VARCHAR(20) DEFAULT "draft"',
                    'case_type VARCHAR(50) DEFAULT "功能测试"',
                    'priority VARCHAR(10) DEFAULT "P3"',
                    'test_type VARCHAR(20) DEFAULT "手动"',
                    'preconditions TEXT',
                    'steps TEXT',
                    'remark TEXT',
                    'requirement_id INT',
                    'related_defects TEXT',
                    'baseline VARCHAR(100)',
                    'estimated_time INT DEFAULT 0',
                    'actual_time INT',
                    'remaining_time INT',
                    'last_executed DATETIME',
                    'executed_by INT',
                    'execution_result VARCHAR(20)',
                    'version VARCHAR(20) DEFAULT "v1"',
                    'plan_id BIGINT',
                    'project_id INT NOT NULL',
                    'creator_id INT',
                    'assignee_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (plan_id) REFERENCES plan(id)',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (creator_id) REFERENCES user(id)',
                    'FOREIGN KEY (assignee_id) REFERENCES user(id)'
                ]
            },
            'workflow_in_app_notification': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTO_INCREMENT',
                    'user_id INT NOT NULL',
                    'actor_id INT',
                    'actor_name VARCHAR(120)',
                    'event VARCHAR(40) NOT NULL',
                    'entity_type VARCHAR(20) NOT NULL',
                    'entity_id BIGINT NOT NULL',
                    'title VARCHAR(500)',
                    'project_id INT',
                    'project_name VARCHAR(200)',
                    'status VARCHAR(64)',
                    'previous_status VARCHAR(64)',
                    'search_blob TEXT',
                    'read_at DATETIME',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (user_id) REFERENCES user(id)',
                    'FOREIGN KEY (actor_id) REFERENCES user(id)',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
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
                    'reasoning TEXT',
                    'steps TEXT',
                    'execution_results TEXT',
                    'agent_result TEXT',
                    'evidences TEXT',
                    'navigation TEXT',
                    'modify_navigation TEXT',
                    'modify_groups TEXT',
                    'delete_navigation TEXT',
                    'final_response TEXT',
                    'llm_model VARCHAR(128)',
                    'images LONGTEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (session_id) REFERENCES chat_session(id)',
                    'FOREIGN KEY (user_id) REFERENCES user(id)'
                ]
            },
            'diff_review_state': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTOINCREMENT',
                    'project_id INT NOT NULL',
                    'target VARCHAR(32) NOT NULL',
                    'target_id BIGINT NOT NULL',
                    'plan_id BIGINT',
                    'lifecycle_id INT DEFAULT 1',
                    'diff_fingerprint VARCHAR(64) DEFAULT ""',
                    'status VARCHAR(20) DEFAULT "pending"',
                    'diff_payload TEXT',
                    'modifications_payload TEXT',
                    'source_message_id INT',
                    'source_session_id INT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'updated_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'adopted_at DATETIME',
                    'rejected_at DATETIME',
                    'operator_id INT',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                    'FOREIGN KEY (operator_id) REFERENCES user(id)'
                ]
            },
            'agent_tasks': {
                'columns': [
                    'id VARCHAR(36) PRIMARY KEY',
                    'name VARCHAR(100) NOT NULL',
                    'status VARCHAR(20) NOT NULL DEFAULT "pending"',
                    'params TEXT',
                    'result TEXT',
                    'error TEXT',
                    'dependencies TEXT',
                    'session_id VARCHAR(64)',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'started_at DATETIME',
                    'finished_at DATETIME',
                ]
            },
            'terminal_audit': {
                'columns': [
                    'id INTEGER PRIMARY KEY AUTO_INCREMENT',
                    'user_id INT NOT NULL',
                    'project_id INT',
                    'event_type VARCHAR(40) NOT NULL',
                    'client_session_id VARCHAR(64)',
                    'detail TEXT',
                    'created_at DATETIME DEFAULT CURRENT_TIMESTAMP',
                    'FOREIGN KEY (user_id) REFERENCES user(id)',
                    'FOREIGN KEY (project_id) REFERENCES project(id)',
                ]
            },
        }
        
        # 检查并创建/更新每个表
        for table_name, definition in table_definitions.items():
            # 检查表是否存在
            table_exists = inspector.has_table(table_name)
            
            if not table_exists:
                # 创建新表
                cols = _adapt_create_table_columns_for_dialect(definition["columns"])
                create_sql = f"CREATE TABLE {table_name} (\n    " + ",\n    ".join(cols) + "\n)"
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
        
        # 先清理 diff_review_state 历史脏数据（同记录多条状态），再建索引
        cleanup_diff_review_duplicates()
        # 旧数据 operator_id 为空时回填为指定用户（默认 id=33）
        backfill_diff_review_legacy_operator(33)

        # 创建性能优化索引
        create_performance_indexes()

        reset_agent_tasks_stuck_running()
        
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

def reset_agent_tasks_stuck_running():
    """进程重启后：将 agent_tasks 中 running 重置为 pending，便于调度器重新领取（需求 6.5）。"""
    try:
        if not inspect(db.engine).has_table('agent_tasks'):
            return
        n = (
            AgentTask.query.filter(AgentTask.status == 'running')
            .update(
                {'status': 'pending', 'started_at': None},
                synchronize_session=False,
            )
        )
        if n:
            db.session.commit()
            print(f"[AGENT_TASK] 已将 {n} 条 running 任务重置为 pending")
        else:
            db.session.commit()
    except Exception as e:
        print(f"[AGENT_TASK] running→pending 重置失败: {e}")
        db.session.rollback()


def cleanup_diff_review_duplicates():
    """清理 diff_review_state 脏数据：同 (project_id,target,target_id) 仅保留最新一条。"""
    try:
        if not inspect(db.engine).has_table('diff_review_state'):
            return
        rows = (
            DiffReviewState.query
            .order_by(
                DiffReviewState.project_id.asc(),
                DiffReviewState.target.asc(),
                DiffReviewState.target_id.asc(),
                DiffReviewState.updated_at.desc(),
                DiffReviewState.id.desc(),
            )
            .all()
        )
        keep_keys = set()
        delete_ids = []
        for r in rows:
            k = (r.project_id, r.target, r.target_id)
            if k in keep_keys:
                delete_ids.append(r.id)
            else:
                keep_keys.add(k)
        if delete_ids:
            DiffReviewState.query.filter(DiffReviewState.id.in_(delete_ids)).delete(synchronize_session=False)
            db.session.commit()
            print(f"[DIFF-CLEANUP] 已删除重复状态行: {len(delete_ids)}")
        else:
            print("[DIFF-CLEANUP] 无重复状态行")
    except Exception as e:
        print(f"[DIFF-CLEANUP] 清理失败: {e}")
        db.session.rollback()


def backfill_diff_review_legacy_operator(default_user_id=33):
    """历史 diff_review_state.operator_id 为 NULL 时回填为指定用户 id（默认 33）。"""
    try:
        if not inspect(db.engine).has_table('diff_review_state'):
            return
        cols = [c['name'] for c in inspect(db.engine).get_columns('diff_review_state')]
        if 'operator_id' not in cols:
            return
        if db.session.get(User, default_user_id) is None:
            print(f"[DIFF-BACKFILL] 用户 id={default_user_id} 不存在，跳过 operator_id 回填")
            return
        res = db.session.execute(
            text('UPDATE diff_review_state SET operator_id = :uid WHERE operator_id IS NULL'),
            {'uid': default_user_id},
        )
        db.session.commit()
        n = getattr(res, 'rowcount', None)
        if n is not None and n > 0:
            print(f'[DIFF-BACKFILL] 已将 {n} 条 operator_id 为空的记录回填为 user_id={default_user_id}')
    except Exception as e:
        db.session.rollback()
        print(f'[DIFF-BACKFILL] 回填失败: {e}')


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
            # 计划类型字段已移除
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
            ("idx_test_case_comment_tc_id", "CREATE INDEX idx_test_case_comment_tc_id ON test_case_comment(test_case_id)"),
            ("idx_test_case_comment_user_id", "CREATE INDEX idx_test_case_comment_user_id ON test_case_comment(user_id)"),
            ("idx_test_case_comment_msg_id", "CREATE INDEX idx_test_case_comment_msg_id ON test_case_comment(source_message_id)"),
            
            # BadCase表新增索引
            ("idx_badcase_plan_id", "CREATE INDEX idx_badcase_plan_id ON bad_case(plan_id)"),

            # DiffReview 持久化索引
            ("idx_diff_review_project_target", "CREATE INDEX idx_diff_review_project_target ON diff_review_state(project_id, target, target_id)"),
            ("idx_diff_review_project_status", "CREATE INDEX idx_diff_review_project_status ON diff_review_state(project_id, status)"),
            ("idx_diff_review_plan", "CREATE INDEX idx_diff_review_plan ON diff_review_state(project_id, plan_id)"),
            ("unique_diff_review_record", "CREATE UNIQUE INDEX unique_diff_review_record ON diff_review_state(project_id, target, target_id)"),

            # 聊天历史：按会话分页取最新（GET /api/chat-sessions/:id?limit&before_id）
            # 关键查询形态：WHERE session_id=? AND id<? ORDER BY id DESC LIMIT ?
            ("idx_chat_message_session_id_id", "CREATE INDEX idx_chat_message_session_id_id ON chat_message(session_id, id)"),
            # 兼容旧路径（按时间排序/统计）
            ("idx_chat_message_session_created", "CREATE INDEX idx_chat_message_session_created ON chat_message(session_id, created_at)"),

            ("idx_wf_inapp_user_created", "CREATE INDEX idx_wf_inapp_user_created ON workflow_in_app_notification(user_id, created_at)"),
            ("idx_wf_inapp_project", "CREATE INDEX idx_wf_inapp_project ON workflow_in_app_notification(project_id)"),
            ("idx_wf_inapp_unread", "CREATE INDEX idx_wf_inapp_unread ON workflow_in_app_notification(user_id, read_at)"),
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

@app.route("/api/notifications", methods=["GET", "POST", "HEAD"])
@login_required
def api_list_workflow_notifications():
    """当前用户站内通知列表（分页 + 关键词 + 类型 + 项目 + 未读）。

    同时接受 GET 与 POST：部分代理/客户端会把带查询的请求发成 POST，此前仅注册 GET 会导致 405。
    分页与筛选参数一律从 query string 读取（axios.post(url, null, { params }) 亦走 query）。"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 20, type=int), 100)
        q = (request.args.get("q") or "").strip()
        entity_type = (request.args.get("entity_type") or "").strip()
        project_id = request.args.get("project_id", type=int)
        unread_only = str(request.args.get("unread_only", "")).lower() in ("1", "true", "yes", "on")

        qry = WorkflowInAppNotification.query.filter(
            WorkflowInAppNotification.user_id == current_user.id
        )
        if project_id is not None and project_id > 0:
            qry = qry.filter(WorkflowInAppNotification.project_id == project_id)
        if entity_type:
            qry = qry.filter(WorkflowInAppNotification.entity_type == entity_type)
        if unread_only:
            qry = qry.filter(WorkflowInAppNotification.read_at.is_(None))
        if q:
            like = f"%{q}%"
            qry = qry.filter(
                or_(
                    WorkflowInAppNotification.title.like(like),
                    WorkflowInAppNotification.project_name.like(like),
                    WorkflowInAppNotification.search_blob.like(like),
                    WorkflowInAppNotification.event.like(like),
                    WorkflowInAppNotification.entity_type.like(like),
                )
            )

        qry = qry.order_by(WorkflowInAppNotification.created_at.desc())
        pagination = qry.paginate(page=page, per_page=per_page, error_out=False)
        items = []
        for row in pagination.items:
            items.append(
                {
                    "id": row.id,
                    "event": row.event,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "title": row.title,
                    "project_id": row.project_id,
                    "project_name": row.project_name,
                    "status": row.status,
                    "previous_status": row.previous_status,
                    "actor_id": row.actor_id,
                    "actor_name": row.actor_name,
                    "read_at": row.read_at.isoformat() if row.read_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return jsonify(
            {
                "success": True,
                "items": items,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "has_next": pagination.has_next,
                    "has_prev": pagination.has_prev,
                },
            }
        )
    except Exception as e:
        print(f"[notifications] list failed: {e}")
        return jsonify({"success": False, "error": "获取通知列表失败"}), 500


@app.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def api_mark_workflow_notification_read(nid):
    try:
        row = WorkflowInAppNotification.query.get(nid)
        if not row or row.user_id != current_user.id:
            return jsonify({"success": False, "error": "记录不存在"}), 404
        row.read_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"[notifications] mark read failed: {e}")
        return jsonify({"success": False, "error": "操作失败"}), 500


@app.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def api_mark_all_workflow_notifications_read():
    try:
        project_id = request.args.get("project_id", type=int)
        qry = WorkflowInAppNotification.query.filter(
            WorkflowInAppNotification.user_id == current_user.id,
            WorkflowInAppNotification.read_at.is_(None),
        )
        if project_id is not None and project_id > 0:
            qry = qry.filter(WorkflowInAppNotification.project_id == project_id)
        now = datetime.utcnow()
        qry.update({WorkflowInAppNotification.read_at: now}, synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"[notifications] mark all read failed: {e}")
        return jsonify({"success": False, "error": "操作失败"}), 500


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
        required_fields = ['name', 'start_date', 'end_date', 'project_id']
        for field in required_fields:
            if not data.get(field):
                print(f"缺少必填字段: {field}")
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
            
        # 检查项目权限
        print(f"检查项目权限: 用户ID={current_user.id}, 项目 ID={data['project_id']}")
        if not has_project_permission(current_user.id, data['project_id']):
            print("权限检查失败")
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        print("权限检查通过")
            
        # 检查父计划是否存在；子计划必须与父计划同一内容类型（BadCase / Bug / 测试用例）
        if data.get('parent_id'):
            parent_plan = Plan.query.get(data['parent_id'])
            if not parent_plan:
                return jsonify({'success': False, 'error': '父计划不存在'}), 404
            # 计划类型字段已移除：不再做“子计划类型必须与父计划一致”的校验

        # 验证日期格式
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else None
        except ValueError:
            return jsonify({'success': False, 'error': '日期格式错误，请使用 YYYY-MM-DD 格式'}), 400
            
        try:
            pid = int(data['project_id'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': '无效的 project_id'}), 400

        # 创建计划（Plan 表已移除 cycle / plan_count 等字段，勿再传入）
        plan = Plan(
            name=data['name'],
            description=data.get('description', ''),
            status=data.get('status', 'active'),
            priority=data.get('priority', 'medium'),
            start_date=start_date,
            end_date=end_date,
            scope_notification=data.get('scope_notification', False),
            parent_id=data.get('parent_id'),
            project_id=pid,
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id')
        )
            
        db.session.add(plan)
        db.session.commit()
            
        result = jsonify({
            'success': True,
            'message': '计划创建成功',
            'plan': {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'is_default': plan.is_default,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'scope_notification': plan.scope_notification,
                'parent_id': _json_snowflake_id(plan.parent_id),
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            }
        })
        _redis_cache_invalidate_project(plan.project_id)
        return result
            
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
        
        # 获取子计划（Plan 模型未定义 children 关系，这里用 parent_id 反查）
        child_rows = Plan.query.filter_by(parent_id=plan.id).all()
        children = [
            {
                'id': _json_snowflake_id(child.id),
                'name': child.name,
                'status': child.status,
                'progress': child.progress,
                'created_at': child.created_at.isoformat() if child.created_at else None,
            }
            for child in (child_rows or [])
        ]

        # 获取工作项列表（避免依赖 plan.badcases / plan.bugs 关系）
        items = []
        # 计划类型字段已移除：计划详情不再按类型回填 items（卡片/列表视图负责按 card_id/type 展示）
        
        return jsonify({
            'success': True,
            'plan': {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'parent_id': _json_snowflake_id(plan.parent_id),
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
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'is_default': plan.is_default,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'parent_id': _json_snowflake_id(plan.parent_id),
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            }
        })
        _redis_cache_invalidate_project(plan.project_id)
        
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
        
        # 检查是否为默认迭代
        if plan.is_default:
            return jsonify({'success': False, 'error': '默认迭代不能删除'}), 400
        
        # 检查是否有子计划（Plan 模型未定义 children 关系）
        if Plan.query.filter_by(parent_id=plan.id).first() is not None:
            return jsonify({'success': False, 'error': '无法删除包含子计划的计划'}), 400
        
        # 计划“类型”字段已移除：统一检查是否有关联工作项（任意类型都阻止删除）
        if BadCase.query.filter_by(plan_id=plan.id).first() is not None:
            return jsonify({'success': False, 'error': '无法删除包含BadCase的计划'}), 400
        if Bug.query.filter_by(plan_id=plan.id).first() is not None:
            return jsonify({'success': False, 'error': '无法删除包含Bug的计划'}), 400
        if TestCase.query.filter_by(plan_id=plan.id).first() is not None:
            return jsonify({'success': False, 'error': '无法删除包含测试用例的计划'}), 400
        
        db.session.delete(plan)
        db.session.commit()
        _redis_cache_invalidate_project(plan.project_id)
        
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


def _plan_api_status_and_type(plan_status):
    """计划列表 API：把库里任意 status 归一为前端侧边栏可用的 status + status_type。
    旧逻辑只有 status=='active' 才算进行中，MySQL/迁移后常见 draft、pending、空串等，会被标成 unplanned，
    导致「进行中计划」整组为空；归档类状态统一归为 archived。"""
    if plan_status is None:
        return 'active', 'in_progress'
    s = str(plan_status).strip()
    if not s:
        return 'active', 'in_progress'
    sl = s.lower()
    archived = frozenset(
        {'archived', 'completed', 'finished', 'done', 'closed', 'cancelled', 'canceled'}
    )
    if sl in archived:
        return s, 'archived'
    ongoing = frozenset(
        {
            'active',
            'in_progress',
            'running',
            'open',
            'doing',
            'draft',
            'pending',
            'new',
            'todo',
            'processing',
            'ongoing',
        }
    )
    if sl in ongoing:
        return s, 'in_progress'
    if s in ('进行中', '未归档'):
        return 'active', 'in_progress'
    # 未知字符串：默认归为进行中，避免侧边栏空白（可按需在后端数据修正）
    return s, 'in_progress'


@app.route('/api/projects/<int:project_id>/plans', methods=['GET'])
@login_required
def api_get_project_plans(project_id):
    """获取项目的计划树"""
    try:
        t_total0 = time.perf_counter()
        # 优先查 Redis 缓存（跨进程共享，10s TTL）
        redis_hit, redis_cached = _redis_cache_get(f'plans:{project_id}')
        if redis_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/plans redis_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(redis_cached)
        # 回退到内存缓存
        cache_hit, cached = _cache_get(('plans', project_id), ttl_s=2.0)
        if cache_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/plans cache_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(cached)

        # 检查项目权限
        t0 = time.perf_counter()
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        t_perm = (time.perf_counter() - t0) * 1000

        # 计划 + 两种 count 用 1 次查询拿齐（避免 plans + 2 次 group by）
        t0 = time.perf_counter()
        from sqlalchemy import func
        bc_sub = (
            db.session.query(BadCase.plan_id.label('plan_id'), func.count(BadCase.id).label('badcase_count'))
            .group_by(BadCase.plan_id)
            .subquery()
        )
        bug_sub = (
            db.session.query(Bug.plan_id.label('plan_id'), func.count(Bug.id).label('bug_count'))
            .group_by(Bug.plan_id)
            .subquery()
        )
        tc_sub = (
            db.session.query(TestCase.plan_id.label('plan_id'), func.count(TestCase.id).label('test_case_count'))
            .filter(TestCase.plan_id.isnot(None))
            .group_by(TestCase.plan_id)
            .subquery()
        )

        plan_rows = (
            db.session.query(
                Plan,
                func.coalesce(bc_sub.c.badcase_count, 0),
                func.coalesce(bug_sub.c.bug_count, 0),
                func.coalesce(tc_sub.c.test_case_count, 0),
            )
            .outerjoin(bc_sub, bc_sub.c.plan_id == Plan.id)
            .outerjoin(bug_sub, bug_sub.c.plan_id == Plan.id)
            .outerjoin(tc_sub, tc_sub.c.plan_id == Plan.id)
            .filter(Plan.project_id == project_id)
            .all()
        )
        t_sql = (time.perf_counter() - t0) * 1000

        if not plan_rows:
            payload = {'success': True, 'plans': []}
            _cache_set(('plans', project_id), payload)
            _redis_cache_set(f'plans:{project_id}', payload, ttl_s=10)
            print(
                f"[PERF] GET /api/projects/{project_id}/plans perm={t_perm:.1f}ms sql={t_sql:.1f}ms build=0.0ms total={(time.perf_counter()-t_total0)*1000:.1f}ms (empty)",
                flush=True,
            )
            return jsonify(payload)

        t0 = time.perf_counter()
        # 构建 parent_id -> [child_plan] 映射，顺便准备 count map
        children_map = {}
        count_map = {}
        for plan, badcase_cnt, bug_cnt, tc_cnt in plan_rows:
            children_map.setdefault(plan.parent_id, []).append(plan)
            count_map[plan.id] = (int(badcase_cnt or 0), int(bug_cnt or 0), int(tc_cnt or 0))

        # 测试用例数量：按 plan_id 统计（不限制 project_id，避免数据不一致导致漏数）
        plan_ids = list(count_map.keys())
        if plan_ids:
            tc_rows = (
                db.session.query(TestCase.plan_id, func.count(TestCase.id))
                .filter(TestCase.plan_id.in_(plan_ids))
                .group_by(TestCase.plan_id)
                .all()
            )
            tc_direct = {int(pid): int(cnt) for pid, cnt in tc_rows}
            for pid in count_map:
                a, b, _ = count_map[pid]
                count_map[pid] = (a, b, tc_direct.get(int(pid), 0))

        def _sort_key(p: Plan):
            # 置顶优先，其次创建时间倒序（与原接口保持一致）
            # Windows 下 datetime.timestamp() 对极端日期可能抛 OSError([Errno 22] Invalid argument)
            pinned = 1 if getattr(p, "is_pinned", False) else 0
            created = getattr(p, "created_at", None)
            ts = 0
            if created:
                try:
                    ts = int(created.timestamp())
                except Exception:
                    ts = 0
            return (-pinned, -ts)

        # 预查询所有 plan 的 test_case 数量，避免 N+1 问题
        tc_all = dict(
            db.session.query(TestCase.plan_id, func.count(TestCase.id))
            .filter(TestCase.plan_id.in_(plan_ids))
            .group_by(TestCase.plan_id)
            .all()
        )

        def build_plan_tree(plan: Plan):
            """递归构建计划树（children 从 children_map 取）；数量含自身+所有子计划"""
            children = [build_plan_tree(c) for c in sorted(children_map.get(plan.id, []), key=_sort_key)]
            bc = count_map.get(plan.id, (0, 0, 0))[0]
            bug = count_map.get(plan.id, (0, 0, 0))[1]
            # 使用预查询的数据
            tc = tc_all.get(plan.id, 0)
            for c in children:
                bc += c.get('badcase_count', 0)
                bug += c.get('bug_count', 0)
                tc += c.get('test_case_count', 0)
            st, st_type = _plan_api_status_and_type(plan.status)
            return {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': st,
                'status_type': st_type,
                'priority': plan.priority,
                'is_pinned': plan.is_pinned,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
                'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
                'children': children,
                'badcase_count': bc,
                'bug_count': bug,
                'test_case_count': tc,
            }

        # 顶级计划：parent_id=None
        root_plans = sorted(children_map.get(None, []), key=_sort_key)
        plans_tree = [build_plan_tree(p) for p in root_plans]
        t_build = (time.perf_counter() - t0) * 1000

        # 二次校验：用一次 GROUP BY 拿到所有 plan 的 test_case 数，再写回树，确保与 DB 一致
        def _collect_ids(nodes, out):
            for n in (nodes if isinstance(nodes, list) else [nodes]):
                pid = n.get('id')
                if pid is not None:
                    try:
                        out.append(int(str(pid)))
                    except (TypeError, ValueError):
                        pass
                if n.get('children'):
                    _collect_ids(n['children'], out)
        plan_ids_tree = []
        _collect_ids(plans_tree, plan_ids_tree)
        if plan_ids_tree:
            tc_patch = dict(
                db.session.query(TestCase.plan_id, func.count(TestCase.id))
                .filter(TestCase.plan_id.in_(plan_ids_tree))
                .group_by(TestCase.plan_id)
                .all()
            )
            def _patch(nodes):
                for n in (nodes if isinstance(nodes, list) else [nodes]):
                    pid = n.get('id')
                    if pid is not None:
                        try:
                            pk = int(str(pid))
                            n['test_case_count'] = int(tc_patch.get(pk, 0))
                        except (TypeError, ValueError):
                            n['test_case_count'] = 0
                    if n.get('children'):
                        _patch(n['children'])
            _patch(plans_tree)

        t0 = time.perf_counter()
        payload = {
            'success': True,
            'plans': plans_tree
        }
        _cache_set(('plans', project_id), payload)
        _redis_cache_set(f'plans:{project_id}', payload, ttl_s=10)
        t_payload = (time.perf_counter() - t0) * 1000
        print(
            f"[PERF] GET /api/projects/{project_id}/plans perm={t_perm:.1f}ms sql={t_sql:.1f}ms build={t_build:.1f}ms payload={t_payload:.1f}ms total={(time.perf_counter()-t_total0)*1000:.1f}ms rows={len(plan_rows)}",
            flush=True,
        )
        return jsonify(payload)
        
    except Exception as e:
        import traceback
        print(f"获取项目计划失败: {e}", flush=True)
        print(f"错误详情: {traceback.format_exc()}", flush=True)
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
        _redis_cache_invalidate_project(data['project_id'])
        
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
        _redis_cache_invalidate_project(team.project_id)
        
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
        t_total0 = time.perf_counter()
        # 优先查 Redis 缓存（跨进程共享，10s TTL）
        redis_hit, redis_cached = _redis_cache_get(f'members:{project_id}')
        if redis_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/members redis_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(redis_cached)
        # 回退到内存缓存
        cache_hit, cached = _cache_get(('members', project_id), ttl_s=0.5)
        if cache_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/members cache_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(cached)

        # 检查项目权限
        t0 = time.perf_counter()
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        t_perm = (time.perf_counter() - t0) * 1000
        
        # 直接权限 + 团队成员 都用 JOIN（总共 2 次查询）
        t0 = time.perf_counter()
        direct_rows = (
            db.session.query(User.id, User.name, User.email, ProjectPermission.role)
            .join(ProjectPermission, ProjectPermission.user_id == User.id)
            .filter(ProjectPermission.project_id == project_id)
            .all()
        )
        t_sql1 = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        direct_member_map = {}
        for uid, name, email, role in direct_rows:
            direct_member_map[uid] = {
                'id': uid,
                'name': name,
                'email': email,
                'role': role,
                'source': 'direct_permission',
            }
        t_build1 = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        team_rows = (
            db.session.query(User.id, User.name, User.email, TeamMember.role, Team.name)
            .join(TeamMember, TeamMember.user_id == User.id)
            .join(Team, Team.id == TeamMember.team_id)
            .filter(Team.project_id == project_id)
            .all()
        )
        t_sql2 = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        all_members = list(direct_member_map.values())
        seen = set(direct_member_map.keys())
        for uid, name, email, role, team_name in team_rows:
            if uid in seen:
                continue
            seen.add(uid)
            all_members.append({
                'id': uid,
                'name': name,
                'email': email,
                'role': role,
                'source': f'team_{team_name}',
            })
        t_build2 = (time.perf_counter() - t0) * 1000
        
        t0 = time.perf_counter()
        payload = {
            'success': True,
            'members': all_members
        }
        _cache_set(('members', project_id), payload)
        _redis_cache_set(f'members:{project_id}', payload, ttl_s=10)
        t_payload = (time.perf_counter() - t0) * 1000
        print(
            f"[PERF] GET /api/projects/{project_id}/members perm={t_perm:.1f}ms sql1={t_sql1:.1f}ms build1={t_build1:.1f}ms sql2={t_sql2:.1f}ms build2={t_build2:.1f}ms payload={t_payload:.1f}ms total={(time.perf_counter()-t_total0)*1000:.1f}ms direct={len(direct_rows)} team={len(team_rows)}",
            flush=True,
        )
        return jsonify(payload)
        
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

def _coerce_non_negative_int(v):
    """转为非负整数；无效返回 None。"""
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        i = int(float(v))
        return i if i >= 0 else None
    except (TypeError, ValueError):
        return None


def _coerce_positive_int_or_none(v):
    """转为正整数；无效或非正返回 None（用于 assignee_id）。"""
    if v is None:
        return None
    if isinstance(v, str) and not str(v).strip():
        return None
    try:
        i = int(float(v))
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _truncate_db_str(value, max_len, default=''):
    if value is None:
        return default
    s = str(value)
    return s[:max_len] if len(s) > max_len else s


def _normalize_bug_priority_for_db(raw):
    """Bug.priority 列为 VARCHAR(10)，create 工具可能产出中文「高/中/低」或过长英文。"""
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return 'p3'
    s = str(raw).strip()
    zh_map = {
        '高': 'p1', '中': 'p2', '低': 'p3',
        '紧急': 'p1', '一般': 'p2',
        '极高': 'p1',
    }
    if s in zh_map:
        return zh_map[s]
    low = s.lower()
    if low in ('p1', 'p2', 'p3'):
        return low
    if s in ('P1', 'P2', 'P3'):
        return s.lower()
    if s in ('1', '2', '3'):
        return 'p' + s
    # 未知值截断，避免超过 10 字符写库失败
    return _truncate_db_str(s, 10, 'p3') or 'p3'


def _attachments_to_text(raw):
    if raw is None:
        return ''
    if isinstance(raw, (dict, list)):
        try:
            return json.dumps(raw, ensure_ascii=False)
        except Exception:
            return str(raw)
    return str(raw)


# Bug相关API接口
@app.route('/api/bugs', methods=['POST'])
@login_required
def api_create_bug():
    """创建Bug"""
    try:
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({'success': False, 'error': '请求体必须是 JSON 对象'}), 400

        title = (data.get('title') or '').strip()
        title = ' '.join(title.split())  # 合并任意空白，与 create 工具一致
        title = _truncate_db_str(title, 200, '')
        project_raw = data.get('project_id')
        project_id_val = _coerce_non_negative_int(project_raw)
        if project_id_val is None or project_id_val <= 0:
            return jsonify({'success': False, 'error': '缺少或无效的 project_id'}), 400

        # 验证必填字段（plan_id 可选：未指定则归入「未计划的 Bug」）
        if not title:
            return jsonify({'success': False, 'error': '缺少必填字段: title 或 project_id'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id_val):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        raw_plan = data.get('plan_id')
        plan_id_val = None
        if raw_plan is not None and str(raw_plan).strip() != '':
            try:
                pi = int(raw_plan)
                if pi != 0:
                    plan_id_val = pi
            except (TypeError, ValueError):
                plan_id_val = None
        
        # 如果提供了 card_id，按卡片类型校验（卡片分类型，计划不分类型）
        raw_card = data.get('card_id')
        card_id_val = None
        if raw_card is not None and str(raw_card).strip() != '':
            try:
                ci = int(raw_card)
                if ci != 0:
                    card_id_val = ci
            except (TypeError, ValueError):
                card_id_val = None
        
        if card_id_val is not None:
            # 按卡片类型校验
            card = Card.query.get(card_id_val)
            if not card:
                return jsonify({'success': False, 'error': '卡片不存在'}), 404
            # 检查卡片类型是否为 bug
            card_type_value = card.type.value if hasattr(card.type, 'value') else str(card.type)
            if card_type_value != 'bug':
                return jsonify({'success': False, 'error': '只能在bug类型卡片中创建bug'}), 400
        elif plan_id_val is not None:
            # 兜底：按计划类型校验（向后兼容）
            plan = Plan.query.get(plan_id_val)
            if not plan:
                return jsonify({'success': False, 'error': '计划不存在'}), 404
            # 计划类型字段已移除：不再按计划类型限制创建 bug

        steps_raw = data.get('steps_to_reproduce')
        if steps_raw is None or (isinstance(steps_raw, str) and steps_raw.strip() == ''):
            steps_raw = data.get('reproduce_steps', '')
        steps_to_reproduce = '' if steps_raw is None else str(steps_raw)

        bug = Bug(
            title=title,
            description=_truncate_db_str(data.get('description', ''), 65535, ''),
            steps_to_reproduce=steps_to_reproduce,
            expected_result=_truncate_db_str(data.get('expected_result', ''), 65535, ''),
            actual_result=_truncate_db_str(data.get('actual_result', ''), 65535, ''),
            severity=_truncate_db_str(data.get('severity', 'medium'), 20, 'medium'),
            priority=_normalize_bug_priority_for_db(data.get('priority')),
            status=_truncate_db_str(data.get('status', 'new'), 20, 'new'),
            bug_type=_truncate_db_str(data.get('bug_type', ''), 50, ''),
            environment=_truncate_db_str(data.get('environment', ''), 100, ''),
            browser=_truncate_db_str(data.get('browser', ''), 50, ''),
            os=_truncate_db_str(data.get('os', ''), 50, ''),
            plan_id=plan_id_val,
            card_id=card_id_val,
            project_id=project_id_val,
            creator_id=current_user.id,
            assignee_id=_coerce_positive_int_or_none(data.get('assignee_id')),
            attachments=_attachments_to_text(data.get('attachments', ''))
        )
        
        db.session.add(bug)
        db.session.commit()
        db.session.refresh(bug)

        # 与 agents CreateTool 一致：迭代看板按 Card 展示；仅插入 Bug 而无 Card 时左侧列表不可见
        if bug.card_id is None:
            try:
                _card = Card(
                    title=bug.title or "",
                    type=CardType.BUG,
                    priority=bug.priority or "p3",
                    assignee_id=bug.assignee_id,
                    project_id=project_id_val,
                    creator_id=bug.creator_id,
                    plan_id=bug.plan_id,
                    description=bug.description,
                    source_type="bug",
                    source_id=int(bug.id),
                )
                db.session.add(_card)
                db.session.commit()
                db.session.refresh(_card)
                bug.card_id = int(_card.id)
                db.session.commit()
                db.session.refresh(bug)
            except Exception as _card_ex:
                db.session.rollback()
                print(f"[api_create_bug] 同步创建 Card 失败: {_card_ex}")

        try:
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_bug(bug), bug.creator_id
            )
            _schedule_workflow_notify(
                "created",
                "bug",
                bug.id,
                bug.title or "",
                bug.project_id,
                _workflow_project_name(bug.project_id),
                bug.status,
                None,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] Bug 创建通知失败: {_e}")
        
        return jsonify({
            'success': True,
            'message': 'Bug创建成功',
            'bug': {
                'id': _json_snowflake_id(bug.id),
                'title': bug.title,
                'description': bug.description,
                'severity': bug.severity,
                'priority': bug.priority,
                'status': bug.status,
                'bug_type': bug.bug_type,
                'plan_id': _json_snowflake_id(bug.plan_id),
                'card_id': _json_snowflake_id(bug.card_id),
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
        import traceback
        traceback.print_exc()
        err_msg = str(e) if e else 'unknown'
        return jsonify({'success': False, 'error': f'创建Bug失败: {err_msg}'}), 500

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
        plan_id = _parse_query_int_optional('plan_id')
        
        # 获取卡片ID参数（优先使用card_id过滤，因为卡片分类型）
        card_id = _parse_query_optional_int64('card_id')
        
        # 获取状态类型参数
        status_type = request.args.get('status_type')
        
        # 构建查询条件
        query = Bug.query.filter_by(project_id=project_id)
        
        # 处理card_id过滤（优先，因为卡片分类型，计划不分类型）
        if card_id is not None:
            query = query.filter_by(card_id=card_id)
            print(f"按卡片ID过滤Bug: card_id={card_id}")
        elif status_type == 'unplanned':
            # 未计划的Bug：没有关联计划的Bug
            query = query.filter(Bug.plan_id.is_(None))
            print(f"过滤未计划的Bug (status_type=unplanned)")
        elif plan_id is not None:
            query = query.filter_by(plan_id=plan_id)
            # 迭代计划下列表：默认只返回已挂卡片的 Bug，避免出现「计划根下直接挂 Bug」的孤儿行（与看板 Card 层对齐）。
            # 数据修复/排查需包含无卡记录时：GET ...&include_cardless_bugs=1
            _inc_cardless = (request.args.get('include_cardless_bugs') or '').strip().lower() in (
                '1',
                'true',
                'yes',
                'on',
            )
            if not _inc_cardless:
                query = query.filter(Bug.card_id.isnot(None))
                print(f"按 plan_id={plan_id} 过滤 Bug，且排除 card_id 为空的记录（include_cardless_bugs 未开启）")
            else:
                print(f"按 plan_id={plan_id} 过滤 Bug，包含无卡片关联记录（include_cardless_bugs=1）")
        
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
                'id': _json_snowflake_id(bug.id),
                'title': bug.title,
                'description': bug.description,
                'bug_type': bug.bug_type,
                'priority': bug.priority,
                'status': bug.status,
                'assignee': assignee_name,
                'plan_id': _json_snowflake_id(bug.plan_id),
                'card_id': _json_snowflake_id(bug.card_id),
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

@app.route('/api/bugs/<int:bug_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_bug_detail(bug_id):
    """Bug详情接口：GET查询，PUT更新"""
    if request.method == 'GET':
        try:
            bug, access_err = _model_for_user_collaborator_access(Bug, bug_id, current_user.id)
            if access_err == 'not_found':
                return jsonify({'success': False, 'error': 'Bug不存在'}), 404
            if access_err == 'forbidden':
                return jsonify({'success': False, 'error': '没有项目权限'}), 403

            # 评论 + 用户名一次 JOIN，避免 bug_comment 与 user 各查一遍
            comment_rows = (
                db.session.query(BugComment, User.name)
                .outerjoin(User, User.id == BugComment.user_id)
                .filter(BugComment.bug_id == bug_id)
                .order_by(BugComment.created_at.asc())
                .all()
            )
            comments = []
            for comment, uname in comment_rows:
                comments.append({
                    'id': comment.id,
                    'content': comment.content,
                    'user_id': comment.user_id,
                    'user_name': uname or '未知',
                    'source_message_id': comment.source_message_id,
                    'created_at': comment.created_at.isoformat()
                })
            
            cid = getattr(bug, 'card_id', None)
            navigation_plan_id = bug.plan_id
            if cid:
                cp = db.session.query(Card.plan_id).filter(Card.id == int(cid)).scalar()
                if cp is not None and int(cp or 0) > 0:
                    navigation_plan_id = cp

            return jsonify({
                'success': True,
                'bug': {
                    'id': _json_snowflake_id(bug.id),
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
                    'plan_id': _json_snowflake_id(bug.plan_id),
                    'navigation_plan_id': _json_snowflake_id(navigation_plan_id),
                    'card_id': _json_snowflake_id(cid),
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
            old_bug_status = bug.status
            
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
                # 处理plan_id为None的情况，确保不会设置为NULL
                plan_id_value = data['plan_id']
                if plan_id_value is not None and plan_id_value != '':
                    try:
                        bug.plan_id = int(plan_id_value)
                    except (TypeError, ValueError):
                        # 如果无法转换为整数，保持原有值
                        pass
                else:
                    # 如果plan_id为空，保持原有值
                    pass
            if 'assignee_id' in data:
                bug.assignee_id = data['assignee_id']
            if 'attachments' in data:
                bug.attachments = data['attachments']
            
            bug.updated_at = datetime.now()
            db.session.commit()
            try:
                _rec = _workflow_merge_creator_if_empty(
                    _workflow_recipients_bug(bug), bug.creator_id
                )
                _ns = bug.status
                _ev = (
                    "status_changed"
                    if "status" in data and old_bug_status != _ns
                    else "updated"
                )
                _prev = (
                    old_bug_status
                    if ("status" in data and old_bug_status != _ns)
                    else None
                )
                _schedule_workflow_notify(
                    _ev,
                    "bug",
                    bug.id,
                    bug.title or "",
                    bug.project_id,
                    _workflow_project_name(bug.project_id),
                    _ns,
                    _prev,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] Bug 更新通知失败: {_e}")
            
            return jsonify({
                'success': True,
                'message': 'Bug更新成功',
                'bug': {
                    'id': _json_snowflake_id(bug.id),
                    'title': bug.title,
                    'status': bug.status,
                    'updated_at': bug.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"更新Bug失败: {e}")
            return jsonify({'success': False, 'error': '更新Bug失败'}), 500
    elif request.method == 'DELETE':
        try:
            bug = Bug.query.get_or_404(bug_id)

            if not has_project_permission(current_user.id, bug.project_id):
                return jsonify({'success': False, 'error': '无权删除此Bug'}), 403

            _pid = bug.project_id
            _title = bug.title or ""
            _st = bug.status
            _pn = _workflow_project_name(_pid)
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_bug(bug), bug.creator_id
            )
            # 先清依赖行，避免 MySQL 外键 / 孤儿约束导致 delete bug 500
            try:
                BugComment.query.filter(BugComment.bug_id == int(bug_id)).delete(
                    synchronize_session=False
                )
            except Exception as _e:
                print(f"[DELETE-BUG] 清理 bug_comment 失败（继续）: {_e}")
            try:
                nt_bug = _normalize_diff_target("bug")
                for _dr in DiffReviewState.query.filter(
                    DiffReviewState.project_id == _pid,
                    DiffReviewState.target == nt_bug,
                    DiffReviewState.target_id == int(bug_id),
                ).all():
                    db.session.delete(_dr)
            except Exception as _e:
                print(f"[DELETE-BUG] 清理 diff_review_state 失败（继续）: {_e}")
            _cid = getattr(bug, "card_id", None)
            if _cid:
                try:
                    bug.card_id = None
                    db.session.flush()
                except Exception as _e:
                    print(f"[DELETE-BUG] 解除 bug.card_id 失败（继续）: {_e}")
                try:
                    CardPlanRelation.query.filter(
                        CardPlanRelation.card_id == int(_cid)
                    ).delete(synchronize_session=False)
                except Exception as _e:
                    print(f"[DELETE-BUG] 清理 card_plan_relation 失败（继续）: {_e}")
                try:
                    _card = Card.query.get(int(_cid))
                    if _card is not None:
                        db.session.delete(_card)
                except Exception as _e:
                    print(f"[DELETE-BUG] 删除关联 Card id={_cid} 失败（继续）: {_e}")

            db.session.delete(bug)
            db.session.commit()
            _cache_invalidate_plans(_pid)
            try:
                _schedule_workflow_notify(
                    "deleted",
                    "bug",
                    bug_id,
                    _title,
                    _pid,
                    _pn,
                    _st,
                    None,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] Bug 删除通知失败: {_e}")

            return jsonify({'success': True, 'message': 'Bug删除成功'})
        except Exception as e:
            db.session.rollback()
            print(f"删除Bug失败: {e}")
            return jsonify({'success': False, 'error': '删除Bug失败'}), 500

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
        
        comment = _append_bug_comment_row(
            bug,
            data['content'],
            current_user.id,
            source_message_id=data.get('message_id'),
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'message': '评论添加成功',
            'comment': comment,
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
    print('[TESTCASE-CREATE] 请求进入 (新代码已加载)')
    try:
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('title'):
            print('[TESTCASE] 400: 缺少 title, data=', {k: v for k, v in (data or {}).items() if k in ('title', 'project_id')})
            return jsonify({'success': False, 'error': '缺少必填字段: title'}), 400
        if not data.get('project_id'):
            print('[TESTCASE] 400: 缺少 project_id, data=', {k: v for k, v in (data or {}).items() if k in ('title', 'project_id')})
            return jsonify({'success': False, 'error': '缺少必填字段: project_id'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, data['project_id']):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 如果提供了 card_id，按卡片类型校验（卡片分类型，计划不分类型）
        card_id_val = _coerce_optional_bigint_json(data.get('card_id'))
        
        if card_id_val is not None:
            # 按卡片类型校验
            card = Card.query.get(card_id_val)
            if not card:
                return jsonify({'success': False, 'error': '卡片不存在'}), 404
            # 检查卡片类型是否为 testcase
            card_type_value = card.type.value if hasattr(card.type, 'value') else str(card.type)
            if card_type_value != 'testcase':
                return jsonify({'success': False, 'error': '只能在testcase类型卡片中创建测试用例'}), 400
        
        # plan_id：若存在则使用（不再校验计划类型）
        plan_id = _coerce_optional_bigint_json(data.get('plan_id'))
        if plan_id:
            plan = Plan.query.get(plan_id)
            if not plan:
                plan_id = None
        # 未显式传 plan_id 时，继承卡片所属迭代
        if plan_id is None and card_id_val is not None:
            card_for_plan = Card.query.get(card_id_val)
            if card_for_plan and card_for_plan.plan_id:
                plan_id = int(card_for_plan.plan_id)
        
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
            plan_id=plan_id,
            project_id=data['project_id'],
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id'),
            card_id=card_id_val,
        )
        
        db.session.add(testcase)
        db.session.commit()
        _cache_invalidate_plans(data['project_id'])
        try:
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_testcase(testcase), testcase.creator_id
            )
            _schedule_workflow_notify(
                "created",
                "testcase",
                testcase.id,
                testcase.title or "",
                testcase.project_id,
                _workflow_project_name(testcase.project_id),
                _testcase_status_str(testcase),
                None,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] TestCase 创建通知失败: {_e}")
        
        # 确保枚举/日期等可 JSON 序列化
        _s = testcase.status
        _st = getattr(_s, 'value', None) or str(_s) if _s else 'draft'
        _ct = testcase.created_at.isoformat() if testcase.created_at else None
        return jsonify({
            'success': True,
            'message': '测试用例创建成功',
            'testcase': {
                'id': _json_snowflake_id(testcase.id),
                'title': str(testcase.title),
                'status': _st,
                'priority': str(testcase.priority) if testcase.priority else 'P3',
                'created_at': _ct
            }
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        err_msg = str(e)
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'创建TestCase失败: {err_msg}'}), 500

@app.route('/api/testcases/<int:testcase_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_testcase_detail(testcase_id):
    """测试用例详情接口：GET查询，PUT更新，DELETE删除"""
    if request.method == 'GET':
        try:
            testcase, access_err = _model_for_user_collaborator_access(TestCase, testcase_id, current_user.id)
            if access_err == 'not_found':
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            if access_err == 'forbidden':
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            _status = testcase.status
            if hasattr(_status, 'value'):
                _status = _status.value
            _exec = testcase.execution_result
            if _exec is not None and hasattr(_exec, 'value'):
                _exec = _exec.value
            return jsonify({
                'success': True,
                'testcase': {
                    'id': _json_snowflake_id(testcase.id),
                    'title': testcase.title,
                    'status': _status,
                    'case_type': testcase.case_type,
                    'priority': testcase.priority,
                    'test_type': testcase.test_type,
                    'preconditions': testcase.preconditions,
                    'steps': testcase.steps,
                    'remark': testcase.remark,
                    'requirement_id': testcase.requirement_id,
                    'related_defects': _testcase_related_defects_detail_payload(testcase),
                    'baseline': testcase.baseline,
                    'estimated_time': testcase.estimated_time,
                    'actual_time': testcase.actual_time,
                    'remaining_time': testcase.remaining_time,
                    'last_executed': testcase.last_executed.isoformat() if testcase.last_executed else None,
                    'executed_by': testcase.executed_by,
                    'execution_result': _exec,
                    'version': testcase.version,
                    'plan_id': _json_snowflake_id(testcase.plan_id),
                    'project_id': testcase.project_id,
                    'creator_id': testcase.creator_id,
                    'assignee_id': testcase.assignee_id,
                    'card_id': _json_snowflake_id(getattr(testcase, 'card_id', None)),
                    'created_at': testcase.created_at.isoformat(),
                    'updated_at': testcase.updated_at.isoformat(),
                    'comments': _testcase_comments_detail_payload(testcase.id),
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
            old_tc_status = _testcase_status_str(testcase)
            
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
                er = data['execution_result']
                if er is None or (isinstance(er, str) and er.strip() == ''):
                    testcase.execution_result = None
                else:
                    try:
                        testcase.execution_result = ExecutionResult(er) if isinstance(er, str) else er
                    except (ValueError, TypeError):
                        testcase.execution_result = None
            if 'version' in data:
                testcase.version = data['version']
            if 'plan_id' in data:
                testcase.plan_id = data['plan_id']
            if 'assignee_id' in data:
                testcase.assignee_id = data['assignee_id']
            
            testcase.updated_at = datetime.now()
            db.session.commit()
            _cache_invalidate_plans(testcase.project_id)
            try:
                _rec = _workflow_merge_creator_if_empty(
                    _workflow_recipients_testcase(testcase), testcase.creator_id
                )
                _ns = _testcase_status_str(testcase)
                _ev = (
                    "status_changed"
                    if "status" in data and old_tc_status != _ns
                    else "updated"
                )
                _prev = (
                    old_tc_status
                    if ("status" in data and old_tc_status != _ns)
                    else None
                )
                _schedule_workflow_notify(
                    _ev,
                    "testcase",
                    testcase.id,
                    testcase.title or "",
                    testcase.project_id,
                    _workflow_project_name(testcase.project_id),
                    _ns,
                    _prev,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] TestCase 更新通知失败: {_e}")
            
            # 处理 status 枚举值
            status_val = testcase.status
            if hasattr(status_val, 'value'):
                status_val = status_val.value
            
            return jsonify({
                'success': True,
                'message': '测试用例更新成功',
                'testcase': {
                    'id': _json_snowflake_id(testcase.id),
                    'title': testcase.title,
                    'status': status_val,
                    'updated_at': testcase.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            print(f"更新TestCase失败: {e}")
            return jsonify({'success': False, 'error': f'更新TestCase失败: {err_msg}'}), 500
    
    elif request.method == 'DELETE':
        try:
            testcase = TestCase.query.get(testcase_id)
            if not testcase:
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, testcase.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            pid = testcase.project_id
            _title = testcase.title or ""
            _st = _testcase_status_str(testcase)
            _pn = _workflow_project_name(pid)
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_testcase(testcase), testcase.creator_id
            )
            try:
                TestCaseComment.query.filter_by(test_case_id=int(testcase_id)).delete(
                    synchronize_session=False
                )
            except Exception as _ce:
                print(f"[DELETE-TESTCASE] 清理 test_case_comment 失败（继续）: {_ce}")
            db.session.delete(testcase)
            db.session.commit()
            _cache_invalidate_plans(pid)
            try:
                _schedule_workflow_notify(
                    "deleted",
                    "testcase",
                    testcase_id,
                    _title,
                    pid,
                    _pn,
                    _st,
                    None,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] TestCase 删除通知失败: {_e}")
            
            return jsonify({
                'success': True,
                'message': '测试用例删除成功'
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"删除TestCase失败: {e}")
            return jsonify({'success': False, 'error': '删除TestCase失败'}), 500


@app.route('/api/testcases/<int:testcase_id>/comment', methods=['POST'])
@login_required
def api_add_testcase_comment(testcase_id):
    """测例评论：仅追加，不可修改历史评论。"""
    testcase, access_err = _model_for_user_collaborator_access(
        TestCase, testcase_id, current_user.id
    )
    if access_err == 'not_found':
        return jsonify({'success': False, 'error': '测试用例不存在'}), 404
    if access_err == 'forbidden':
        return jsonify({'success': False, 'error': '没有项目权限'}), 403

    data = request.get_json() or {}
    content = data.get('content')
    if not content or not str(content).strip():
        return jsonify({'success': False, 'error': '评论内容不能为空'}), 400

    try:
        comment = _append_testcase_comment_row(
            testcase,
            content,
            current_user.id,
            source_message_id=data.get('message_id'),
        )
        db.session.commit()
        return jsonify({'success': True, 'comment': comment})
    except Exception as e:
        db.session.rollback()
        print(f"[API] 追加测例评论失败: {e}", flush=True)
        return jsonify({'success': False, 'error': '追加评论失败'}), 500


@app.route('/api/plans/<int:plan_id>/testcases', methods=['GET'])
@login_required
def api_get_plan_testcases(plan_id):
    """获取计划下的所有测试用例（支持 count_only=1 仅返回数量）"""
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 仅返回数量，避免 405 等路由问题
        count_only = request.args.get('count_only')
        if count_only in ('1', 1) or str(count_only) == '1':
            try:
                n = TestCase.query.filter_by(plan_id=plan_id).count()
                return jsonify({'success': True, 'count': n})
            except Exception as ce:
                print(f"获取计划{plan_id}测试用例数量失败: {ce}")
                return jsonify({'success': False, 'error': str(ce)}), 500
        
        testcases = TestCase.query.filter_by(plan_id=plan_id).all()
        
        testcase_list = []
        for tc in testcases:
            testcase_list.append({
                'id': _json_snowflake_id(tc.id),
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
        import traceback
        print(f"获取计划TestCase列表失败: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


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
                'id': _json_snowflake_id(bug.id),
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
        t_total0 = time.perf_counter()
        session = ChatSession.query.get(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404
        
        # 检查权限
        if session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '没有权限访问此会话'}), 403
        
        limit = request.args.get('limit', type=int)
        before_id = request.args.get('before_id', type=int)
        lite = request.args.get('lite') in ('1', 'true', 'yes')
        lim = min(max(int(limit or 0), 0), 200)

        # tail 模式：只取需要的列，避免 ORM 实体构造 + 不必要字段加载
        t0 = time.perf_counter()
        if lite:
            q = db.session.query(
                ChatMessage.id,
                ChatMessage.is_user,
                ChatMessage.content,
                ChatMessage.final_response,
                ChatMessage.llm_model,
                ChatMessage.images,
                ChatMessage.created_at,
            ).filter(ChatMessage.session_id == session_id)
        else:
            q = db.session.query(
                ChatMessage.id,
                ChatMessage.is_user,
                ChatMessage.content,
                ChatMessage.understanding,
                ChatMessage.reasoning,
                ChatMessage.steps,
                ChatMessage.execution_results,
                ChatMessage.agent_result,
                ChatMessage.evidences,
                ChatMessage.navigation,
                ChatMessage.modify_navigation,
                ChatMessage.modify_groups,
                ChatMessage.delete_navigation,
                ChatMessage.final_response,
                ChatMessage.llm_model,
                ChatMessage.images,
                ChatMessage.created_at,
            ).filter(ChatMessage.session_id == session_id)
        if before_id:
            q = q.filter(ChatMessage.id < before_id)
        q = q.order_by(ChatMessage.id.desc())
        if lim:
            q = q.limit(lim)
        msg_rows_desc = q.all()
        t_sql = (time.perf_counter() - t0) * 1000
        msg_rows = list(reversed(msg_rows_desc))
        include_memory = request.args.get('include_memory') in ('1', 'true', 'yes')
        t0 = time.perf_counter()
        messages = []
        if lite:
            # lite：只返回渲染“最新一屏”所需字段，避免无意义的 null 键占用 payload
            for (mid, is_user, content, final_response, llm_model, images, created_at) in msg_rows:
                messages.append({
                    'id': mid,
                    'is_user': is_user,
                    'content': content,
                    'final_response': final_response,
                    'llm_model': llm_model,
                    'images': images,
                    'created_at': created_at.isoformat() if created_at else None
                })
        else:
            for (
                mid,
                is_user,
                content,
                understanding,
                reasoning,
                steps,
                execution_results,
                agent_result,
                evidences,
                navigation,
                modify_navigation,
                modify_groups,
                delete_navigation,
                final_response,
                llm_model,
                images,
                created_at,
            ) in msg_rows:
                messages.append({
                    'id': mid,
                    'is_user': is_user,
                    'content': content,
                    'understanding': understanding,
                    'reasoning': reasoning,
                    'steps': steps,
                    'execution_results': execution_results,
                    'agent_result': agent_result,
                    'evidences': evidences,
                    'navigation': navigation,
                    'modify_navigation': modify_navigation,
                    'modify_groups': modify_groups,  # 添加 modify_groups
                    'delete_navigation': delete_navigation,
                    'final_response': final_response,
                    'llm_model': llm_model,
                    'images': images,
                    'created_at': created_at.isoformat() if created_at else None
                })
        t_build = (time.perf_counter() - t0) * 1000
        
        has_more = False
        next_before_id = None
        if lim and msg_rows_desc:
            # 若本次取到了 limit 条，认为可能还有更早数据（前端滚动到顶再请求验证）
            has_more = len(msg_rows_desc) >= lim
            # msg_rows 已反转为正序；第一个就是“当前最早”
            next_before_id = int(messages[0]['id']) if messages else int(msg_rows_desc[-1][0])

        try:
            print(
                f"[PERF] GET /api/chat-sessions/{session_id} sql={t_sql:.1f}ms build={t_build:.1f}ms total={(time.perf_counter()-t_total0)*1000:.1f}ms rows={len(messages)} lim={lim} before_id={before_id} lite={1 if lite else 0}",
                flush=True,
            )
        except Exception:
            pass

        return jsonify({
            'success': True,
            'session': {
                'id': session.id,
                'title': session.title,
                'is_active': session.is_active,
                'memory_enabled': session.memory_enabled,
                # 默认不返回大块 memory_data，减轻 JSON 体积与前端 parse 耗时；需要时 GET ?include_memory=1
                'memory_data': (session.memory_data if include_memory else None),
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'messages': messages,
                'has_more': has_more,
                'next_before_id': next_before_id
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
        
        # 调用 LLM 生成简短标题（使用 get_llm；chat 多为 async，须 await）
        import asyncio
        import inspect
        from llm.factory import get_llm

        llm = get_llm("qwen")

        prompt = f"""请根据以下用户消息生成一个简短的会话标题（不超过15个字），直接输出标题，不要加引号或其他符号：

用户消息：{user_message[:200]}

标题："""

        chat_fn = getattr(llm, "chat", None)
        if not callable(chat_fn):
            return jsonify({'success': False, 'error': 'LLM 未实现 chat'}), 500

        if inspect.iscoroutinefunction(chat_fn):
            title = asyncio.run(chat_fn(prompt))
        else:
            title = chat_fn(prompt)
            if inspect.isawaitable(title):
                title = asyncio.run(title)

        if title is None:
            title = ""
        title = str(title).strip().strip('"').strip("'")
        if title.startswith("Error:") or not title:
            return jsonify({'success': False, 'error': '模型未返回有效标题'}), 500
        
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
        _raw_imgs = data.get('images')
        _images_store = None
        if _raw_imgs is not None:
            if isinstance(_raw_imgs, str):
                _s = _raw_imgs.strip()
                _images_store = _s if _s else None
            else:
                try:
                    _images_store = json.dumps(_raw_imgs, ensure_ascii=False)
                except Exception:
                    _images_store = None
            
        message = ChatMessage(
            session_id=session_id,
            user_id=current_user.id if data.get('is_user') else None,
            is_user=data.get('is_user', True),
            content=data.get('content'),
            understanding=data.get('understanding'),
            reasoning=data.get('reasoning'),
            steps=data.get('steps'),
            execution_results=data.get('execution_results'),
            agent_result=data.get('agent_result'),
            evidences=data.get('evidences'),
            navigation=data.get('navigation'),
            modify_navigation=data.get('modify_navigation'),
            modify_groups=data.get('modify_groups'),  # 添加 modify_groups
            delete_navigation=data.get('delete_navigation'),
            final_response=data.get('final_response'),
            llm_model=data.get('llm_model'),
            images=_images_store,
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


@app.route('/api/chat-messages/<int:message_id>/clear-delete-navigation', methods=['POST'])
@login_required
def api_clear_chat_message_delete_navigation(message_id):
    """列表取消删除时清空 delete_navigation；采纳时保留快照并标记已确认（confirmation_required=false），刷新后仍可核对。"""
    try:
        mid = _normalize_chat_message_id(message_id)
        if mid is None:
            return jsonify({'success': False, 'error': '无效的消息 id'}), 400
        msg = db.session.get(ChatMessage, mid)
        if not msg:
            return jsonify({'success': False, 'error': '消息不存在'}), 404
        session = db.session.get(ChatSession, msg.session_id)
        if not session or session.user_id != current_user.id:
            return jsonify({'success': False, 'error': '无权访问'}), 403
        payload = request.get_json(silent=True) or {}
        cancel = payload.get('cancel') is True
        if cancel:
            msg.delete_navigation = None
        elif msg.delete_navigation:
            try:
                nav = json.loads(msg.delete_navigation)
                if not isinstance(nav, dict):
                    nav = {}
            except Exception:
                nav = {}
            nav['confirmation_required'] = False
            nav['success'] = True
            msg.delete_navigation = json.dumps(nav, ensure_ascii=False)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"[CHAT] clear-delete-navigation 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/projects/<int:project_id>/testcases', methods=['GET'])
@login_required
def api_get_project_testcases(project_id):
    """获取项目的TestCase列表（分页）"""
    try:
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取计划ID参数
        plan_id = _parse_query_int_optional('plan_id')
        card_id = _parse_query_optional_int64('card_id')
        
        # 获取状态类型参数
        status_type = request.args.get('status_type')
        
        # 构建查询条件
        query = TestCase.query.filter_by(project_id=project_id)
        
        if card_id is not None:
            query = query.filter(TestCase.card_id == card_id)
            print(f"按卡片ID过滤TestCase: card_id={card_id}", flush=True)
        # 处理status_type参数
        elif status_type == 'unplanned':
            # 未计划的测试用例：没有关联计划的测试用例
            query = query.filter(TestCase.plan_id.is_(None))
            print(f"过滤未计划的TestCase (status_type=unplanned)")
        elif plan_id is not None:
            query = query.filter_by(plan_id=plan_id)
        
        # 分页查询TestCase
        pagination = query.order_by(TestCase.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        testcases = []
        for tc in pagination.items:
            # 获取负责人姓名
            assignee_name = '未指派'
            if tc.assignee_id:
                user = User.query.get(tc.assignee_id)
                if user:
                    assignee_name = user.name
            
            testcases.append({
                'id': _json_snowflake_id(tc.id),
                'title': tc.title,
                'status': tc.status.value if hasattr(tc.status, 'value') else str(tc.status),
                'case_type': tc.case_type,
                'priority': tc.priority,
                'assignee': assignee_name,
                'plan_id': _json_snowflake_id(tc.plan_id),
                'card_id': _json_snowflake_id(getattr(tc, 'card_id', None)),
                'created_at': tc.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'badcases': testcases,  # 为了兼容前端 filteredBadcases，这里使用 badcases 键名
            'total': pagination.total,
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
        print(f"获取项目TestCase列表失败: {e}")
        return jsonify({'success': False, 'error': '获取TestCase列表失败'}), 500

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

    # 开发热重载：默认开启（修改 .py 后自动重启子进程）。
    # 但在 PERF_LOG=1 性能定位场景下强制关闭，避免 reloader 分裂出父/子多进程抢占端口导致请求落到“旧进程”。
    # 关闭：FLASK_DEBUG=0 或 FLASK_ENV=production
    _fd = os.getenv("FLASK_DEBUG", "1").strip().lower()
    _use_reload = _fd not in ("0", "false", "no", "off", "")
    if os.getenv("FLASK_ENV", "").strip().lower() == "production":
        _use_reload = False
    if os.getenv("PERF_LOG", "").strip() == "1":
        _use_reload = False
    try:
        _port = int(os.getenv("PORT", "5000") or "5000")
    except ValueError:
        _port = 5000
    _host = (os.getenv("FLASK_HOST", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    if _use_reload:
        print("🔁 热重载已开启：保存 Python 源码后会自动重启（关闭请设置 FLASK_DEBUG=0）")
    else:
        print("ℹ️ 热重载已关闭（FLASK_DEBUG=0 或 FLASK_ENV=production）")

    app.run(
        debug=_use_reload,
        use_reloader=_use_reload,
        host=_host,
        port=_port,
    )