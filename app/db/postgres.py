"""PostgreSQL 引擎（psycopg2）。"""
import psycopg2
from psycopg2.errors import UniqueViolation
from psycopg2.extras import RealDictCursor

from .base import DatabaseEngine


class PostgresEngine(DatabaseEngine):

    def get_connection(self, config: dict):
        return psycopg2.connect(**config)

    def make_cursor(self, conn):
        return conn.cursor(cursor_factory=RealDictCursor)

    # ── SQL 片段生成 ──
    def json_array_length(self, col: str) -> str:
        return f"jsonb_array_length({col})"

    def now_utc(self) -> str:
        return "NOW() AT TIME ZONE 'UTC'"

    def default_now(self) -> str:
        return "NOW()"

    def json_default_empty(self) -> str:
        return "'[]'::jsonb"

    def json_cast_param(self) -> str:
        return "::jsonb"

    def role_ddl(self) -> str:
        return ("VARCHAR(16) NOT NULL DEFAULT 'user' "
                "CHECK (role IN ('root','admin','user'))")

    def auto_pk(self) -> str:
        return "SERIAL PRIMARY KEY"

    def big_text(self) -> str:
        return "TEXT"

    def engine_clause(self) -> str:
        return ""

    def schema_name_query(self) -> str:
        return "current_database()"

    # ── 错误类 ──
    @property
    def integrity_error(self):
        return UniqueViolation

    # ── INSERT helpers ──
    def insert_with_id(self, cur, table: str, columns: list, values: list,
                       returning_col: str = "id"):
        cols = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = (f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
               f"RETURNING {returning_col}")
        cur.execute(sql, values)
        return cur.fetchone()[returning_col]