"""抽象数据库引擎——所有具体引擎必须实现此接口。"""
from abc import ABC, abstractmethod


class DatabaseEngine(ABC):
    """数据库引擎抽象基类。实现后可通过 `app/db/__init__.py:init_engine` 注册。"""

    # ── 连接层 ──
    @abstractmethod
    def get_connection(self, config: dict):
        """返回原生连接对象（含 dialect-specific 设置）。"""

    @abstractmethod
    def make_cursor(self, conn):
        """返回 dict-like cursor（支持 row["col"] 访问）。"""

    # ── SQL 片段生成 ──
    @abstractmethod
    def json_array_length(self, col: str) -> str:
        """JSON 数组长度 SQL 表达式（用于 f-string）。"""

    @abstractmethod
    def now_utc(self) -> str:
        """当前 UTC 时间 SQL 表达式。"""

    @abstractmethod
    def default_now(self) -> str:
        """DDL DEFAULT 当前时间。"""

    @abstractmethod
    def json_default_empty(self) -> str:
        """DDL DEFAULT 空 JSON 数组。"""

    @abstractmethod
    def json_cast_param(self) -> str:
        """INSERT/UPDATE JSON 参数转型后缀（PostgreSQL ::jsonb；MySQL 空字符串）。"""

    @abstractmethod
    def role_ddl(self) -> str:
        """users.role 列 DDL。"""

    @abstractmethod
    def auto_pk(self) -> str:
        """自增主键列类型。"""

    @abstractmethod
    def big_text(self) -> str:
        """长文本类型。"""

    @abstractmethod
    def engine_clause(self) -> str:
        """CREATE TABLE 末尾的 ENGINE=… 等方言子句。"""

    @abstractmethod
    def schema_name_query(self) -> str:
        """查询当前 database / schema 名的 SQL 表达式。"""

    @abstractmethod
    def bool_toggle(self, col: str) -> str:
        """布尔列取反 SQL 表达式。"""

    # ── 错误类 ──
    @property
    @abstractmethod
    def integrity_error(self):
        """UNIQUE 约束违反异常类。"""

    # ── INSERT helpers ──
    def insert_with_id(self, cur, table: str, columns: list, values: list,
                       returning_col: str = "id"):
        """插入一行并返回自增 id。"""
        raise NotImplementedError