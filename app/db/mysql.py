"""MySQL 引擎（pymysql）。"""
import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import IntegrityError

from .base import DatabaseEngine


class MySQLEngine(DatabaseEngine):

    def get_connection(self, config: dict):
        cfg = {**config, "charset": "utf8mb4"}
        return pymysql.connect(**cfg)

    def make_cursor(self, conn):
        return conn.cursor(DictCursor)

    # ── SQL 片段生成 ──
    def json_array_length(self, col: str) -> str:
        return f"JSON_LENGTH({col})"

    def now_utc(self) -> str:
        return "UTC_TIMESTAMP()"

    def default_now(self) -> str:
        return "CURRENT_TIMESTAMP"

    def json_default_empty(self) -> str:
        return "JSON_ARRAY()"

    def json_cast_param(self) -> str:
        return ""

    def role_ddl(self) -> str:
        return "ENUM('root','admin','user') NOT NULL DEFAULT 'user'"

    def last_active_ddl(self) -> str:
        return "DATETIME"

    def auto_pk(self) -> str:
        return "INT AUTO_INCREMENT PRIMARY KEY"

    def big_text(self) -> str:
        return "MEDIUMTEXT"

    def engine_clause(self) -> str:
        return "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

    def schema_name_query(self) -> str:
        return "DATABASE()"

    def bool_toggle(self, col: str) -> str:
        return f"1 - {col}"

    # ── 错误类 ──
    @property
    def integrity_error(self):
        return IntegrityError

    # ── INSERT helpers ──
    def insert_with_id(self, cur, table: str, columns: list, values: list,
                       returning_col: str = "id"):
        cols = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        cur.execute(sql, values)
        return cur.lastrowid