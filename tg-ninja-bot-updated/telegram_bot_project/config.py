import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    
    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///telegram_bot.db')
    
    # Redis Configuration
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # Flask Configuration
    FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    
    # Telegram API Configuration
    API_ID = os.getenv('API_ID')
    API_HASH = os.getenv('API_HASH')
    
    # Security
    ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))
    
    # Application Settings
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    
    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', 30))
    MAX_INVITES_PER_HOUR = int(os.getenv('MAX_INVITES_PER_HOUR', 50))
    
    # Auto-posting intervals (in seconds)
    MIN_AUTO_POST_INTERVAL = int(os.getenv('MIN_AUTO_POST_INTERVAL', 3600))  # 1 hour
    MAX_AUTO_POST_INTERVAL = int(os.getenv('MAX_AUTO_POST_INTERVAL', 86400))  # 24 hours

