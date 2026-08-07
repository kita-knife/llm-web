"""数据库引擎单例——create_app 启动时初始化一次，全局可用。"""
from .base import DatabaseEngine
from .mysql import MySQLEngine
from .postgres import PostgresEngine

_engine: DatabaseEngine | None = None

_ENGINE_CLASSES = {
    "mysql": MySQLEngine,
    "postgres": PostgresEngine,
    "postgresql": PostgresEngine,
}


def init_engine(db_type: str):
    global _engine
    cls = _ENGINE_CLASSES.get(db_type.lower())
    if cls is None:
        raise ValueError(f"Unknown DB_TYPE: {db_type}")
    _engine = cls()


def get_engine() -> DatabaseEngine:
    if _engine is None:
        raise RuntimeError("engine not initialized — call init_engine first")
    return _engine


def get_conn():
    return get_engine().get_connection(_DB_CONFIG or {})


def make_cursor(conn):
    return get_engine().make_cursor(conn)


# ── 内部 config（由 create_app 注入）──
_DB_CONFIG: dict = {}


def set_db_config(**cfg):
    global _DB_CONFIG
    _DB_CONFIG = cfg