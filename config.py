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
    QWEN_API_KEY = os.getenv('QWEN_API_KEY', "sk-063e4252653c4d629c2355a90dd186b1")
    QWEN_API_URL = os.getenv('QWEN_API_URL', None)
    QWEN_API_MODEL = os.getenv('QWEN_API_MODEL', 'qwen-plus')
    QWEN_API_TEMPERATURE = float(os.getenv('QWEN_API_TEMPERATURE', 0.7))
    
    # 百度千帆大模型配置
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
    QIANFAN_MODEL = os.getenv('QIANFAN_MODEL', 'ernie-4.5-turbo-128k')
    QIANFAN_TEMPERATURE = float(os.getenv('QIANFAN_TEMPERATURE', '0.7'))
    QIANFAN_TOP_P = float(os.getenv('QIANFAN_TOP_P', '0.8'))
    QIANFAN_MAX_RETRIES = int(os.getenv('QIANFAN_MAX_RETRIES', '3'))
    
    # 默认 LLM 配置
    DEFAULT_LLM = os.getenv('DEFAULT_LLM', 'qianfan')  # agent文本推理用文心4.5turbo
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    
    REDIS_DATABASE=int(os.getenv('REDIS_DATABASE', 0))
    REDIS_USERNAME=os.getenv('REDIS_USERNAME', None)

    # Stripe 支付配置
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_xxx')  # 替换为真实密钥
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_xxx')  # Webhook 签名密钥

    # 智谱GLM配置
    ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY', 'b6185f3bac97489da843602537da8cec.cFBNLM2wRxb8lBwJ')
    ZHIPU_MODEL = os.getenv('ZHIPU_MODEL', 'glm-4-flash')  # 文本对话用 glm-4-flash
    ZHIPU_MODEL_REASONING = os.getenv('ZHIPU_MODEL_REASONING', 'glm-5')  # 复杂推理用 glm-5
    ZHIPU_MAX_TOKENS = int(os.getenv('ZHIPU_MAX_TOKENS', '65536'))
    ZHIPU_TEMPERATURE = float(os.getenv('ZHIPU_TEMPERATURE', '0.7'))
    ZHIPU_ENABLE_THINKING = os.getenv('ZHIPU_ENABLE_THINKING', 'true').lower() == 'true'
