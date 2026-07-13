"""MinIO / 图片上传与缓存。"""
from __future__ import annotations

import io
import mimetypes
import os
import time
from urllib.parse import quote, unquote

import boto3
from botocore.exceptions import ClientError
from PIL import Image
from werkzeug.utils import secure_filename

from config import Config

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

@app.route('/api/ping', methods=['GET'])
def api_ping():
    """无鉴权探活 + 预热 DB/Redis，供前端进项目页时先打一遍，避免首条业务接口冷连远端库 4s+"""
    t0 = time.perf_counter()
    db_ok = False
    try:
        db.session.execute(db.text('SELECT 1'))
        db_ok = True
    except Exception as ex:
        print(f"[ping] db failed: {ex}", flush=True)
    finally:
        db.session.remove()
    db_ms = (time.perf_counter() - t0) * 1000
    redis_ok = False
    t1 = time.perf_counter()
    try:
        rc = get_redis_client()
        if rc is not None:
            rc.ping()
            redis_ok = True
    except Exception:
        pass
    redis_ms = (time.perf_counter() - t1) * 1000
    total_ms = (time.perf_counter() - t0) * 1000
    if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
        print(f"[PERF] GET /api/ping total={total_ms:.1f}ms db={db_ms:.1f}ms redis={redis_ms:.1f}ms", flush=True)
    return jsonify({'ok': db_ok, 'db_ms': round(db_ms, 1), 'redis_ok': redis_ok, 'redis_ms': round(redis_ms, 1)})


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
