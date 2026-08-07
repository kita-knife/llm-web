import os

from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production")
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "appuser")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "web_test1")
    DB_TYPE = os.getenv("DB_TYPE", "mysql").lower()
    DEBUG = False
    JSON_AS_ASCII = False
    MINIMAX_API_BASE = os.getenv("MINIMAX_API_BASE", "https://api.minimax.chat/v1")
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3")
    CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "20"))
    CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "60"))


class DevConfig(BaseConfig):
    DEBUG = True


class ProdConfig(BaseConfig):
    DEBUG = False


def get_config():
    env = os.getenv("APP_ENV", "dev").lower()
    if env in ("prod", "production"):
        return ProdConfig
    return DevConfig