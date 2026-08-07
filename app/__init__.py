import os

from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request

from .config import get_config
from .csrf import check_csrf, generate_csrf
from .db import init_db_pool
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
        init_db_pool()
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
        from .db import get_conn
        if not g.get("user") or not request.path.startswith("/chat"):
            return {"chat_sessions": []}
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, messages, pinned, updated_at
                   FROM chat_sessions
                   WHERE user_id = %s AND JSON_LENGTH(messages) > 0
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
    from .db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'users'
              AND column_name = 'password_hash'
            """
        )
        if cur.fetchone()["n"] == 0:
            cur.execute(
                "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL AFTER city"
            )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS login_sessions (
                sid VARCHAR(64) PRIMARY KEY,
                user_id INT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                INDEX idx_login_sessions_user (user_id),
                INDEX idx_login_sessions_expires (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(200),
                messages JSON NOT NULL,
                pinned TINYINT(1) NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,
                CONSTRAINT fk_session_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_sessions_user_pinned_updated (user_id, pinned DESC, updated_at DESC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'chat_sessions'
              AND column_name = 'messages'
            """
        )
        if cur.fetchone()["n"] == 0:
            cur.execute("DROP TABLE IF EXISTS chat_messages")
            cur.execute("DROP TABLE chat_sessions")
            cur.execute(
                """
                CREATE TABLE chat_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id INT NOT NULL,
                    title VARCHAR(200),
                    messages JSON NOT NULL,
                    pinned TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_session_user FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_sessions_user_pinned_updated (user_id, pinned DESC, updated_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

        cur.execute(
            """
            SELECT name, COUNT(*) AS c FROM users
            GROUP BY name HAVING c > 1
            """
        )
        dups = cur.fetchall()
        if dups:
            names = ", ".join(f"{r['name']}(×{r['c']})" for r in dups)
            raise RuntimeError(
                f"users 表存在重名，无法添加 UNIQUE 约束：{names}。"
                "请手动去重后再启动。"
            )

        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = 'users'
              AND index_name = 'name'
            """
        )
        if cur.fetchone()["n"] == 0:
            cur.execute("ALTER TABLE users ADD UNIQUE (name)")

        # role 列：三级权限
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'users'
              AND column_name = 'role'
            """
        )
        if cur.fetchone()["n"] == 0:
            cur.execute(
                "ALTER TABLE users ADD COLUMN role ENUM('root','admin','user') NOT NULL DEFAULT 'user' AFTER password_hash"
            )

        # drop age / city
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'users'
              AND column_name = 'age'
            """
        )
        if cur.fetchone()["n"] > 0:
            cur.execute("ALTER TABLE users DROP COLUMN age")
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'users'
              AND column_name = 'city'
            """
        )
        if cur.fetchone()["n"] > 0:
            cur.execute("ALTER TABLE users DROP COLUMN city")

        # bootstrap：如果还没有 root，把第一个有密码的用户提升为 root
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE role='root'")
        if cur.fetchone()["n"] == 0:
            cur.execute(
                """
                UPDATE users SET role='root'
                WHERE id = (
                    SELECT id FROM (
                        SELECT id FROM users
                        WHERE password_hash IS NOT NULL
                        ORDER BY id LIMIT 1
                    ) t
                )
                """
            )

        conn.commit()