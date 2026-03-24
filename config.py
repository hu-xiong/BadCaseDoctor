import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
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
    # 全项目 Qwen 文本对话统一走 OpenAI 兼容 HTTP：.../compatible-mode/v1/chat/completions
    DASHSCOPE_COMPAT_BASE_URL = os.getenv(
        'DASHSCOPE_COMPAT_BASE_URL',
        'https://dashscope.aliyuncs.com/compatible-mode/v1',
    )
    
    # Qwen 可选模型列表（compatible-mode 下 model 字段，与控制台一致）：
    # - qwen-turbo / qwen-plus / qwen-max / qwen3.5-plus 等
    # 千问 Max 思考：模型 id qwen3-max-2026-01-23，enable_thinking 开启思考
    QWEN3_MAX_THINKING_MODEL = os.getenv('QWEN3_MAX_THINKING_MODEL', 'qwen3-max-2026-01-23')
    
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
    DEFAULT_LLM = os.getenv('DEFAULT_LLM', 'qianfan')  # 默认文心；千问需配置 DASHSCOPE_API_KEY
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    
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
