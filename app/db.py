from flask import current_app
from pymysql import connect
from pymysql.cursors import DictCursor

_DB_CONFIG: dict = {}


def init_db_pool():
    global _DB_CONFIG
    _DB_CONFIG = {
        "host": current_app.config["DB_HOST"],
        "port": current_app.config["DB_PORT"],
        "user": current_app.config["DB_USER"],
        "password": current_app.config["DB_PASSWORD"],
        "database": current_app.config["DB_NAME"],
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
    }


def get_conn():
    return connect(**_DB_CONFIG)