import os

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request

from .config import get_config
from .csrf import check_csrf, generate_csrf
from .db import set_db_config, init_engine
from .extensions import limiter
from .session import clear_expired_sessions, load_session

load_dotenv()


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())

    limiter.init_app(app)
    app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    app.config["RATELIMIT_DEFAULT"] = "200/hour"

    with app.app_context():
        set_db_config(
            host=app.config["DB_HOST"],
            port=app.config["DB_PORT"],
            user=app.config["DB_USER"],
            password=app.config["DB_PASSWORD"],
            database=app.config["DB_NAME"],
        )
        init_engine(app.config["DB_TYPE"])
        ensure_auth_schema()

    from .blueprints.pages import bp as pages_bp
    from .blueprints.db_check import bp as db_check_bp
    from .blueprints.users import bp as users_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.chat import bp as chat_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(db_check_bp)
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(chat_bp)

    @app.before_request
    def _load_session():
        load_session()

    @app.before_request
    def _check_csrf():
        check_csrf()

    @app.before_request
    def _maybe_cleanup_sessions():
        import random
        if random.random() < 0.01:
            clear_expired_sessions()

    @app.context_processor
    def inject_user():
        return {"current_user": g.get("user")}

    @app.context_processor
    def inject_csrf():
        return {"csrf_token": generate_csrf}

    @app.context_processor
    def inject_chat_sessions():
        from flask import request
        from .db import get_engine, get_conn, make_cursor
        if not g.get("user") or not request.path.startswith("/chat"):
            return {"chat_sessions": []}
        db = get_engine()
        with get_conn() as conn, make_cursor(conn) as cur:
            cur.execute(
                f"""SELECT id, title, messages, pinned, updated_at
                   FROM chat_sessions
                   WHERE user_id = %s AND {db.json_array_length('messages')} > 0
                   ORDER BY pinned DESC, updated_at DESC LIMIT 30""",
                (g.user["id"],),
            )
            sessions = cur.fetchall()
        return {"chat_sessions": sessions}

    @app.errorhandler(400)
    def bad_request(e):
        msg = str(e.description) if hasattr(e, "description") else "请求无效"
        if request.path.startswith("/api/") or "application/json" in request.headers.get(
            "Accept", ""
        ):
            return jsonify({"error": msg}), 400
        return render_template("400.html", message=msg), 400

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/") or "application/json" in request.headers.get(
            "Accept", ""
        ):
            return jsonify({"error": "not found", "path": request.path}), 404
        return render_template("404.html", path=request.path), 404

    @app.errorhandler(429)
    def rate_limited(e):
        if request.path.startswith("/api/") or "application/json" in request.headers.get(
            "Accept", ""
        ):
            return jsonify({"error": "rate limit exceeded", "detail": str(e.description)}), 429
        return render_template("429.html"), 429

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith("/api/") or "application/json" in request.headers.get(
            "Accept", ""
        ):
            return jsonify({"error": "internal server error"}), 500
        return render_template("500.html"), 500

    return app


def ensure_auth_schema():
    """幂等地确保 schema 完整（MySQL/PostgreSQL 双兼容）。"""
    from .db import get_engine, get_conn, make_cursor
    db = get_engine()

    with get_conn() as conn, make_cursor(conn) as cur:
        # ===== users =====
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {db.auto_pk()},
                name VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255),
                role {db.role_ddl()},
                created_at TIMESTAMP NOT NULL DEFAULT {db.default_now()}
            ) {db.engine_clause()}""")

        # ===== chat_sessions =====
        from .db.postgres import PostgresEngine
        is_pg = isinstance(db, PostgresEngine)
        cur.execute(
            f"SELECT COUNT(*) AS n FROM information_schema.tables "
            f"WHERE table_schema = {db.schema_name_query()} AND table_name = 'chat_sessions'"
        )
        if cur.fetchone()["n"] == 0:
            if is_pg:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        title VARCHAR(200),
                        messages JSONB NOT NULL DEFAULT {db.json_default_empty()},
                        pinned BOOLEAN NOT NULL DEFAULT FALSE,
                        model VARCHAR(100),
                        created_at TIMESTAMP NOT NULL DEFAULT {db.default_now()},
                        updated_at TIMESTAMP NOT NULL DEFAULT {db.default_now()}
                    )""")
                cur.execute(
                    "CREATE OR REPLACE FUNCTION update_updated_at() "
                    "RETURNS TRIGGER AS $BODY$ "
                    "BEGIN NEW.updated_at = NOW(); RETURN NEW; END; "
                    "$BODY$ LANGUAGE plpgsql"
                )
                cur.execute("DROP TRIGGER IF EXISTS chat_sessions_updated_at ON chat_sessions")
                cur.execute(
                    "CREATE TRIGGER chat_sessions_updated_at "
                    "BEFORE UPDATE ON chat_sessions "
                    "FOR EACH ROW EXECUTE FUNCTION update_updated_at()"
                )
            else:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id INT NOT NULL,
                        title VARCHAR(200),
                        messages JSON NOT NULL,
                        pinned TINYINT(1) NOT NULL DEFAULT 0,
                        model VARCHAR(100),
                        created_at DATETIME NOT NULL DEFAULT {db.default_now()},
                        updated_at DATETIME NOT NULL DEFAULT {db.default_now()}
                                     ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_sessions_user_pinned (user_id, pinned DESC, updated_at DESC),
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) {db.engine_clause()}""")

        # ===== chat_sessions.model 列迁移 =====
        if is_pg:
            cur.execute(
                "SELECT COUNT(*) AS n FROM information_schema.columns "
                "WHERE table_catalog = current_database() AND table_name = 'chat_sessions' AND column_name = 'model'"
            )
        else:
            cur.execute(
                f"SELECT COUNT(*) AS n FROM information_schema.columns "
                f"WHERE table_schema = {db.schema_name_query()} AND table_name = 'chat_sessions' AND column_name = 'model'"
            )
        if cur.fetchone()["n"] == 0:
            cur.execute("ALTER TABLE chat_sessions ADD COLUMN model VARCHAR(100)")

        # ===== login_sessions =====
        cur.execute(
            f"SELECT COUNT(*) AS n FROM information_schema.tables "
            f"WHERE table_schema = {db.schema_name_query()} AND table_name = 'login_sessions'"
        )
        if cur.fetchone()["n"] == 0:
            if is_pg:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS login_sessions (
                        sid VARCHAR(64) PRIMARY KEY,
                        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMP NOT NULL
                    )""")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ls_user ON login_sessions(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ls_expires ON login_sessions(expires_at)")
            else:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS login_sessions (
                        sid VARCHAR(64) PRIMARY KEY,
                        user_id INT NOT NULL,
                        created_at DATETIME NOT NULL DEFAULT {db.default_now()},
                        expires_at DATETIME NOT NULL,
                        INDEX idx_ls_user (user_id),
                        INDEX idx_ls_expires (expires_at)
                    ) {db.engine_clause()}""")

        conn.commit()


