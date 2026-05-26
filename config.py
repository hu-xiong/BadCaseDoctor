import os
from pathlib import Path

from dotenv import load_dotenv

# 固定从项目根目录加载 .env（与 config.py 同目录），避免从别的 cwd 启动时读不到密钥
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()  # 仍尝试当前工作目录，兼容旧习惯

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    # 主业务库：必须为 MySQL（app 启动时会校验 URI）。在 .env 中设置 DATABASE_URL；迁移/工具脚本如需 SQLite 见 scripts/migrate_sqlite_to_mysql.py
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql+pymysql://root:hx123456@117.72.33.38:33106/bad_case')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 邮件配置
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.qq.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', 'your-email@qq.com')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', 'your-email-password')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'your-email@qq.com')
    REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
    # ==================== Qwen (阿里云/通义千问) ====================
    # API Key 配置
    QWEN_API_KEY = os.getenv('QWEN_API_KEY', "sk-ae78f45927654500ab070de1addb4156")
    QWEN_API_URL = os.getenv('QWEN_API_URL', None)
    
    # 默认模型配置
    QWEN_API_MODEL = os.getenv('QWEN_API_MODEL', 'qwen-plus')
    QWEN_API_TEMPERATURE = float(os.getenv('QWEN_API_TEMPERATURE', 0.7))
    
    # DashScope 专用配置（步骤推理 ReAct / 对话 Agent）
    # 复用 QWEN_API_KEY，可指定不同模型
    DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY', QWEN_API_KEY)
    DASHSCOPE_MODEL = os.getenv('DASHSCOPE_MODEL', 'qwen3.5-plus')
    VISION_MODEL = (os.getenv('VISION_MODEL') or 'qwen3.6-plus').strip()
    # 全项目 Qwen 文本对话统一走 OpenAI 兼容 HTTP：.../compatible-mode/v1/chat/completions
    DASHSCOPE_COMPAT_BASE_URL = os.getenv(
        'DASHSCOPE_COMPAT_BASE_URL',
        'https://dashscope.aliyuncs.com/compatible-mode/v1',
    )
    
    # Qwen 可选模型列表（compatible-mode 下 model 字段，与控制台一致）：
    # - qwen-turbo / qwen-plus / qwen-max / qwen3.5-plus 等
    # 千问 Max 思考：模型 id qwen3-max-2026-01-23，enable_thinking 开启思考
    QWEN3_MAX_THINKING_MODEL = os.getenv('QWEN3_MAX_THINKING_MODEL', 'qwen3-max-2026-01-23')
    # 逗号分隔 model id：不对这些模型请求 enable_thinking（减少冗长 reasoning）；默认含 qwen3.5-plus；置空则谁都不禁用
    QWEN_THINKING_DISABLE_MODELS = os.getenv('QWEN_THINKING_DISABLE_MODELS', 'qwen3.5-plus').strip()
    # 百炼部分模型即使不传也可能默认思考链；未开启思考时对请求显式 extra_body enable_thinking=false（默认开）
    _qedb = (os.getenv('QWEN_EXPLICIT_DISABLE_THINKING_BODY') or '1').strip().lower()
    QWEN_EXPLICIT_DISABLE_THINKING_BODY = _qedb not in ('0', 'false', 'no', 'off', '')
    
    # ==================== Qianfan (百度/文心一言) ====================
    QIANFAN_API_KEY = os.getenv(
        'QIANFAN_API_KEY',
        'bce-v3/ALTAK-o11nAoKmuL7qDdZL3CQMD/62c7691269aa3fb33674cdb022f17a6f03280078'
    )
    QIANFAN_SECRET_KEY = os.getenv(
        'QIANFAN_SECRET_KEY',
        'ALTAKxhlfvE2A08OyAYx2xKieC'
    )
    QIANFAN_USE_BEARER_TOKEN = os.getenv('QIANFAN_USE_BEARER_TOKEN', 'True').lower() == 'true'
    
    # 千帆模型配置
    # 可选模型列表：
    # - ernie-4.5-turbo-128k: 长上下文（128K）
    # - ernie-x1-turbo-32k: 强推理模型（默认，32K 上下文）
    # - ernie-4.0: 旗舰版
    QIANFAN_MODEL = os.getenv('QIANFAN_MODEL', 'ernie-x1-turbo-32k')
    QIANFAN_TEMPERATURE = float(os.getenv('QIANFAN_TEMPERATURE', '0.7'))
    QIANFAN_TOP_P = float(os.getenv('QIANFAN_TOP_P', '0.8'))
    QIANFAN_MAX_RETRIES = int(os.getenv('QIANFAN_MAX_RETRIES', '3'))
    
    # 默认 LLM 配置（步骤推理 ReAct / 对话 Agent）
    # 默认千问：与前端下拉默认 qwen3.5-plus 对齐；需百度文心时请设环境变量 DEFAULT_LLM=qianfan 并配置千帆密钥
    DEFAULT_LLM = os.getenv('DEFAULT_LLM', 'qwen')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

    # ==================== DeepSeek（官方 OpenAI 兼容 API）====================
    # 环境变量 DEEPSEEK_API_KEY 优先；未设置时用下方默认（与 Qwen/千帆 同项目习惯，提交 Git 前请改回空或仅放 .env）
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', 'sk-fb38f3d033be4f2bb949bd6765d64157').strip()
    DEEPSEEK_API_BASE_URL = os.getenv('DEEPSEEK_API_BASE_URL', 'https://api.deepseek.com').strip().rstrip('/')
    # 默认 deepseek-v4-pro；可用 DEEPSEEK_V4_MODEL 覆盖
    DEEPSEEK_V4_MODEL = os.getenv('DEEPSEEK_V4_MODEL', 'deepseek-v4-pro').strip()
    # 思考模式强度：high / max（见 https://api-docs.deepseek.com/zh-cn/guides/thinking_mode ）
    DEEPSEEK_REASONING_EFFORT = os.getenv('DEEPSEEK_REASONING_EFFORT', 'high').strip().lower()
    DEEPSEEK_TEMPERATURE = float(os.getenv('DEEPSEEK_TEMPERATURE', '0.7'))
    # 可选：同一账号内 KV/前缀缓存隔离键（官方 request.user_id）；固定为产品实例 id 可提高同前缀命中稳定性
    DEEPSEEK_KV_USER_ID = os.getenv('DEEPSEEK_KV_USER_ID', '').strip()
    # deepseek-v4-pro：调用方未传 max_tokens 时的默认 completion 上限（思考+正文共用），减轻冗长重复；0=不限制
    try:
        _dsmpt = (os.getenv('DEEPSEEK_V4_PRO_MAX_TOKENS') or '2048').strip()
        DEEPSEEK_V4_PRO_MAX_TOKENS = int(_dsmpt) if _dsmpt else 0
    except ValueError:
        DEEPSEEK_V4_PRO_MAX_TOKENS = 2048

    # ==================== modify 歧义意图（轻量 LLM）====================
    # 默认开；设 MODIFY_INTENT_LLM=0 / false / off 关闭。无 DEEPSEEK_API_KEY 时不会请求。
    MODIFY_INTENT_LLM = (os.getenv("MODIFY_INTENT_LLM") or "1").strip()
    MODIFY_INTENT_LLM_MODEL = (os.getenv("MODIFY_INTENT_LLM_MODEL") or "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    try:
        _milt = (os.getenv("MODIFY_INTENT_LLM_TIMEOUT") or "4").strip()
        MODIFY_INTENT_LLM_TIMEOUT = float(_milt) if _milt else 4.0
    except ValueError:
        MODIFY_INTENT_LLM_TIMEOUT = 4.0
    # modify 沙箱预览：默认 mysql_temp（原库 TEMPORARY TABLE 试写，与生产同引擎校验 UPDATE）；显式设 skip_update 可仅 diff 无试写
    MODIFY_SANDBOX_PREVIEW_MODE = (os.getenv("MODIFY_SANDBOX_PREVIEW_MODE") or "mysql_temp").strip().lower()
    
    REDIS_DATABASE=int(os.getenv('REDIS_DATABASE', 0))
    REDIS_USERNAME=os.getenv('REDIS_USERNAME', None)

    # Stripe 支付配置
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_xxx')  # 替换为真实密钥
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_xxx')  # Webhook 签名密钥

    # ==================== GLM (智谱 AI/智谱清言) ====================
    ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY', 'b6185f3bac97489da843602537da8cec.cFBNLM2wRxb8lBwJ')
        
    # 可选模型列表：
    # - glm-4-flash: 快速响应（文本对话，默认）
    # - glm-5: 强推理模型（复杂推理、Text2SQL）
    ZHIPU_MODEL = os.getenv('ZHIPU_MODEL', 'glm-4-flash')  # 文本对话用 glm-4-flash
    ZHIPU_MODEL_REASONING = os.getenv('ZHIPU_MODEL_REASONING', 'glm-5')  # 复杂推理用 glm-5
    ZHIPU_MAX_TOKENS = int(os.getenv('ZHIPU_MAX_TOKENS', '65536'))
    ZHIPU_TEMPERATURE = float(os.getenv('ZHIPU_TEMPERATURE', '0.7'))
    ZHIPU_ENABLE_THINKING = os.getenv('ZHIPU_ENABLE_THINKING', 'true').lower() == 'true'

    # ==================== Long-term Memory (ES Vector) ====================
    # 总开关：默认关闭；开启后会在 ReAct 上下文中注入 long_memory，并开放 /api/memory/* 接口
    LONG_MEMORY_ENABLED = os.getenv("LONG_MEMORY_ENABLED", "false").lower() == "true"

    # Elasticsearch 连接（向量检索 / 文档索引）
    # 支持 ES_URL=http(s)://host:port 或 ES_HOST/ES_PORT；鉴权可用 ES_API_KEY 或 ES_USERNAME/ES_PASSWORD
    ES_URL = os.getenv("ES_URL", "").strip()
    ES_HOST = os.getenv("ES_HOST", "117.72.33.38").strip()
    ES_PORT = int(os.getenv("ES_PORT", "19200"))
    ES_USERNAME = os.getenv("ES_USERNAME", "").strip()
    ES_PASSWORD = os.getenv("ES_PASSWORD", "").strip()
    ES_API_KEY = os.getenv("ES_API_KEY", "").strip()
    ES_VERIFY_CERTS = os.getenv("ES_VERIFY_CERTS", "true").lower() == "true"

    # --- ES 索引命名（本项目自拟）：{命名空间}_{环境}_ + 逻辑后缀，共集群时与其它系统隔离 ---
    # ES_INDEX_NAMESPACE：产品简称 bdc = BadCaseDoctor；ES_INDEX_ENV：dev/stg/prod（仅小写字母数字）
    # 物理索引名一律：f"{ES_INDEX_PREFIX}{逻辑后缀}"；可直接设 ES_INDEX_PREFIX 覆盖整套规则
    _es_ns = os.getenv("ES_INDEX_NAMESPACE", "bdc").strip().lower() or "bdc"
    _es_env = os.getenv("ES_INDEX_ENV", "dev").strip().lower() or "dev"
    _es_env_safe = "".join(c for c in _es_env if c.isalnum()) or "dev"
    _es_prefix_computed = f"{_es_ns}_{_es_env_safe}_"
    ES_INDEX_NAMESPACE = _es_ns
    ES_INDEX_ENV = _es_env_safe
    ES_INDEX_PREFIX = os.getenv("ES_INDEX_PREFIX", "").strip() or _es_prefix_computed

    # 逻辑后缀（不含命名空间；拼接后示例见注释）
    ES_INDEX_DOCUMENT_META = os.getenv("ES_INDEX_DOCUMENT_META", "doc_meta").strip() or "doc_meta"
    # 用户/系统文档：值为「再前缀」，典型物理名 = ES_INDEX_PREFIX + 下列值 + 业务 id
    ES_INDEX_USER_DOC_PREFIX = os.getenv("ES_INDEX_USER_DOC_PREFIX", "udoc_").strip() or "udoc_"
    ES_INDEX_SYSTEM_DOC_PREFIX = os.getenv("ES_INDEX_SYSTEM_DOC_PREFIX", "sdoc_").strip() or "sdoc_"

    # 长期记忆向量索引（默认 bdc_dev_long_memory；勿在后缀里重复 bdc）
    _es_lm = os.getenv("ES_LONG_MEMORY_INDEX", "").strip()
    ES_LONG_MEMORY_INDEX = _es_lm or f"{ES_INDEX_PREFIX}long_memory"

    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "").strip() or DASHSCOPE_COMPAT_BASE_URL
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "").strip() or OPENAI_API_KEY or DASHSCOPE_API_KEY or QWEN_API_KEY
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "tongyi-embedding-vision-plus-2026-03-06").strip()
    # 多模态向量模型可选维度（如 tongyi-embedding-vision-plus 默认 1152）；空则使用模型默认
    _emb_dim_raw = os.getenv("EMBEDDING_DIMENSION", "").strip()
    EMBEDDING_DIMENSION = int(_emb_dim_raw) if _emb_dim_raw.isdigit() else None
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "remote").strip().lower()  # remote | local
    EMBEDDING_LOCAL_MODEL = os.getenv("EMBEDDING_LOCAL_MODEL", "BAAI/bge-small-zh-v1.5").strip()

    # Grep 检索专用向量 / rerank（默认千帆 BGE，比 DashScope 多模态+VL-rerank 快）
    GREP_EMBEDDING_BACKEND = os.getenv("GREP_EMBEDDING_BACKEND", "qianfan").strip().lower()
    GREP_EMBEDDING_MODEL = os.getenv("GREP_EMBEDDING_MODEL", "bge-large-zh").strip()
    GREP_EMBEDDING_BASE_URL = os.getenv(
        "GREP_EMBEDDING_BASE_URL", "https://qianfan.baidubce.com/v2"
    ).strip()
    GREP_EMBEDDING_API_KEY = (
        os.getenv("GREP_EMBEDDING_API_KEY", "").strip() or QIANFAN_API_KEY
    )
    _grep_emb_dim = os.getenv("GREP_EMBEDDING_DIMENSION", "").strip()
    GREP_EMBEDDING_DIMENSION = int(_grep_emb_dim) if _grep_emb_dim.isdigit() else None
    GREP_EMBEDDING_LOCAL_MODEL = os.getenv(
        "GREP_EMBEDDING_LOCAL_MODEL", "BAAI/bge-small-zh-v1.5"
    ).strip()

    # Grep 向量检索（Work Item ES 索引）
    GREP_VECTOR_ENABLED = os.getenv("GREP_VECTOR_ENABLED", "true").lower() == "true"
    GREP_WORK_ITEM_ALIAS = os.getenv("GREP_WORK_ITEM_ALIAS", "").strip() or f"{ES_INDEX_PREFIX}work_item"
    _grep_wi = os.getenv("GREP_WORK_ITEM_INDEX", "").strip()
    GREP_WORK_ITEM_INDEX = _grep_wi  # 空则运行时按 model+dims 生成物理索引名
    GREP_VECTOR_TOP_K = int(os.getenv("GREP_VECTOR_TOP_K", "8"))
    # auto：短关键词仅 BM25（不调 embedding）；长句(>=GREP_QUERY_EMBED_MIN_CHARS)才 KNN
    GREP_QUERY_EMBED_MODE = os.getenv("GREP_QUERY_EMBED_MODE", "auto").strip().lower()
    GREP_QUERY_EMBED_MIN_CHARS = int(os.getenv("GREP_QUERY_EMBED_MIN_CHARS", "80"))
    # 有关键词时是否仍加载整棵计划材料树（极慢）；默认关，检索走 ES
    GREP_PLAN_RECORDS_ON_KEYWORD = os.getenv("GREP_PLAN_RECORDS_ON_KEYWORD", "false").lower() == "true"
    GREP_VECTOR_MIN_SCORE = float(os.getenv("GREP_VECTOR_MIN_SCORE", "0.0"))
    GREP_HYBRID_RRF_K = int(os.getenv("GREP_HYBRID_RRF_K", "60"))
    GREP_INDEX_ASYNC = os.getenv("GREP_INDEX_ASYNC", "true").lower() == "true"
    GREP_EMBED_BATCH_SIZE = int(os.getenv("GREP_EMBED_BATCH_SIZE", "16"))
    GREP_EMBED_BATCH_FLUSH_MS = int(os.getenv("GREP_EMBED_BATCH_FLUSH_MS", "300"))
    GREP_SEARCH_LOG_ENABLED = os.getenv("GREP_SEARCH_LOG_ENABLED", "true").lower() == "true"
    GREP_ASSIGNEE_FUZZY_PREFIX = os.getenv("GREP_ASSIGNEE_FUZZY_PREFIX", "true").lower() == "true"
    GREP_RECENT_CREATED_FALLBACK = os.getenv("GREP_RECENT_CREATED_FALLBACK", "true").lower() == "true"
    GREP_RECENT_CREATED_MAX = int(os.getenv("GREP_RECENT_CREATED_MAX", "30"))
    GREP_RECENT_CREATED_TTL_S = int(os.getenv("GREP_RECENT_CREATED_TTL_S", "900"))
    GREP_ES_LLM_JUDGE = os.getenv("GREP_ES_LLM_JUDGE", "false").lower() == "true"
    # rerank 已成功时跳过 LLM 二审（默认开，可省 ~1s+）
    GREP_SKIP_LLM_JUDGE_IF_RERANKED = os.getenv("GREP_SKIP_LLM_JUDGE_IF_RERANKED", "true").lower() == "true"
    GREP_RERANK_QUERY_MAX_CHARS = int(os.getenv("GREP_RERANK_QUERY_MAX_CHARS", "400"))
    GREP_ES_LLM_JUDGE_MODEL = os.getenv("GREP_ES_LLM_JUDGE_MODEL", "").strip()
    GREP_ES_LLM_JUDGE_TIMEOUT = float(os.getenv("GREP_ES_LLM_JUDGE_TIMEOUT", "12"))
    GREP_ES_LLM_JUDGE_MAX_CANDIDATES = int(os.getenv("GREP_ES_LLM_JUDGE_MAX_CANDIDATES", "30"))
    GREP_ES_LLM_JUDGE_MAX_TOKENS = int(os.getenv("GREP_ES_LLM_JUDGE_MAX_TOKENS", "512"))
    GREP_RERANK_ENABLED = os.getenv("GREP_RERANK_ENABLED", "true").lower() == "true"
    GREP_RERANK_BACKEND = os.getenv("GREP_RERANK_BACKEND", "qianfan").strip().lower()
    GREP_RERANK_MODEL = os.getenv("GREP_RERANK_MODEL", "bce-reranker-base").strip()
    GREP_RERANK_BASE_URL = os.getenv(
        "GREP_RERANK_BASE_URL", "https://qianfan.baidubce.com/v2"
    ).strip()
    # rerank 是 grep 的可选精排，不应长时间阻塞主检索；超时后保留 ES 原序。
    GREP_RERANK_HTTP_TIMEOUT = float(os.getenv("GREP_RERANK_HTTP_TIMEOUT", "2.5"))
    GREP_RERANK_MIN_SCORE = float(os.getenv("GREP_RERANK_MIN_SCORE", "0.48"))
    GREP_RERANK_TOP_N = int(os.getenv("GREP_RERANK_TOP_N", "5"))
    GREP_RERANK_FALLBACK_MIN_SCORE = float(os.getenv("GREP_RERANK_FALLBACK_MIN_SCORE", "0.35"))
    # 项目创建即建 work_item 索引，grep 默认不再打 indices.exists
    GREP_ES_SKIP_ALIAS_EXISTS = os.getenv("GREP_ES_SKIP_ALIAS_EXISTS", "true").lower() == "true"
    GREP_ES_ALIAS_CACHE_OK_TTL_S = float(os.getenv("GREP_ES_ALIAS_CACHE_OK_TTL_S", "86400"))
    GREP_ES_ALIAS_CACHE_MISS_TTL_S = float(os.getenv("GREP_ES_ALIAS_CACHE_MISS_TTL_S", "120"))
    # 命中 ES 后直接用 _source 字段组装列表，默认不再打 MySQL IN 查询
    GREP_ES_HYDRATE_FROM_SOURCE = os.getenv("GREP_ES_HYDRATE_FROM_SOURCE", "true").lower() == "true"
    GREP_CARD_SKIP_SQL_IF_ES = os.getenv("GREP_CARD_SKIP_SQL_IF_ES", "true").lower() == "true"
    # ES 召回条数 <= 该值时跳过远端 rerank（省 ~1s+ API）
    GREP_RERANK_SKIP_IF_LE = int(os.getenv("GREP_RERANK_SKIP_IF_LE", "8"))
    GREP_RERANK_MAX_DOCS = int(os.getenv("GREP_RERANK_MAX_DOCS", "12"))
    # 首条标题已覆盖全部关键词时跳过 rerank，改本地按标题/token 排序
    GREP_RERANK_SKIP_IF_ES_CONFIDENT = os.getenv(
        "GREP_RERANK_SKIP_IF_ES_CONFIDENT", "true"
    ).lower() == "true"
    # 短关键词 BM25 只查 title（比扫 search_text 快）
    GREP_ES_BM25_TITLE_ONLY_MAX_CHARS = int(os.getenv("GREP_ES_BM25_TITLE_ONLY_MAX_CHARS", "64"))
    GREP_ES_SEARCH_TIMEOUT_S = float(os.getenv("GREP_ES_SEARCH_TIMEOUT_S", "2"))
    # 有关键词且走 ES 时跳过全项目 plan_tree 查询（省 ~100ms+ MySQL）
    GREP_SKIP_PLAN_TREE_ON_KEYWORD = os.getenv(
        "GREP_SKIP_PLAN_TREE_ON_KEYWORD", "true"
    ).lower() == "true"
    GREP_HYBRID_CACHE_TTL_S = float(os.getenv("GREP_HYBRID_CACHE_TTL_S", "45"))
    # 勿在首次 grep 同步 warmup（会阻塞 ~3s）；需要时可 app 启动后后台预热
    GREP_ES_WARMUP = os.getenv("GREP_ES_WARMUP", "false").lower() == "true"
    # 未走远端 rerank（skipped_small_set 等）时跳过 LLM 二审
    GREP_SKIP_LLM_JUDGE_IF_NO_RERANK_API = os.getenv(
        "GREP_SKIP_LLM_JUDGE_IF_NO_RERANK_API", "true"
    ).lower() == "true"
    GREP_RERANK_API_KEY = os.getenv("GREP_RERANK_API_KEY", "").strip() or QIANFAN_API_KEY
    GREP_RERANK_INSTRUCT = os.getenv(
        "GREP_RERANK_INSTRUCT",
        "Given a web search query, retrieve relevant passages that answer the query.",
    ).strip()

    # 检索策略
    LONG_MEMORY_TOP_K = int(os.getenv("LONG_MEMORY_TOP_K", "10"))
    LONG_MEMORY_USE_N = int(os.getenv("LONG_MEMORY_USE_N", "4"))
    LONG_MEMORY_MIN_SCORE = float(os.getenv("LONG_MEMORY_MIN_SCORE", "0.0"))

    # 调试：是否在控制台打印发往 LLM 的完整请求（messages 等）。.env 写 LLM_LOG_PROMPTS=1 后须重启 python
    _llp_raw = (
        os.getenv("LLM_LOG_PROMPTS")
        or os.getenv("LLM_DEBUG_PROMPTS")
        or os.getenv("LLM_PROMPT_DEBUG")
        or ""
    ).strip().lower()
    LLM_LOG_PROMPTS = _llp_raw in ("1", "true", "yes", "on")

    # 嵌入式终端：AI 生成命令白名单（仅约束 /api/terminal/ai_suggest 返回值，不拦截用户手动键入）
    TERMINAL_AI_WHITELIST_ENABLED = os.getenv("TERMINAL_AI_WHITELIST_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    # 逗号分隔的可执行名（与首 token 精确匹配，忽略前导 sudo 等）；为空则使用内置默认列表
    TERMINAL_AI_WHITELIST = os.getenv("TERMINAL_AI_WHITELIST", "").strip()

    # ==================== MinIO（通用文件上传：/upload、富文本附件、头像等）====================
    # 后续若换独立文件服务，可改环境变量或只替换上传逻辑，仍建议保留此处为单一配置源。
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://117.72.33.38:9901").strip().rstrip("/")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "hxReligi12.")
    MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "apaas-root")
    _minio_prefix = os.getenv("MINIO_SAAS_FILE_PATH", "saas_qa_file").strip().strip("/")
    MINIO_SAAS_FILE_PATH = f"{_minio_prefix}/" if _minio_prefix else ""
    MINIO_MAX_FILE_SIZE = int(os.getenv("MINIO_MAX_FILE_SIZE", str(524288000)))  # 默认 500MB，与历史 app 一致
    MINIO_MAX_SUM_FILE_SIZE = int(os.getenv("MINIO_MAX_SUM_FILE_SIZE", str(MINIO_MAX_FILE_SIZE)))
