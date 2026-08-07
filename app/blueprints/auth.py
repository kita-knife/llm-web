from flask import Blueprint, g, jsonify, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_conn, make_cursor, get_engine
from ..extensions import limiter
from ..session import SESSION_COOKIE, SESSION_LIFETIME_DAYS, create_session, destroy_session

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["POST"])
@limiter.limit("5/hour")
def register():
    """API 注册：只能创建 'user' 角色。"""
    db = get_engine()
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        name = data["name"]
        password = data["password"]
    except (KeyError, TypeError):
        return jsonify({"error": "required fields: name, password"}), 400
    if len(password) < 4:
        return jsonify({"error": "password too short (>=4 chars)"}), 400
    pwd_hash = generate_password_hash(password)
    try:
        with get_conn() as conn, make_cursor(conn) as cur:
            new_id = db.insert_with_id(cur, "users",
                                       ["name", "password_hash", "role"],
                                       [name, pwd_hash, "user"])
            conn.commit()
    except db.integrity_error:
        return jsonify({"error": "name already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return (
        jsonify({"id": new_id, "name": name, "role": "user"}),
        201,
    )


@bp.route("/login", methods=["POST"])
@limiter.limit("10/minute")
def login():
    data = request.get_json(silent=True) or request.form.to_dict()
    name = data.get("name")
    password = data.get("password")
    if not name or not password:
        return jsonify({"error": "name and password required"}), 400
    try:
        with get_conn() as conn, make_cursor(conn) as cur:
            cur.execute(
                """SELECT id, name, role, password_hash
                   FROM users WHERE name = %s""",
                (name,),
            )
            row = cur.fetchone()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if (
        not row
        or not row["password_hash"]
        or not check_password_hash(row["password_hash"], password)
    ):
        return jsonify({"error": "invalid name or password"}), 401
    sid, _expires_at = create_session(row["id"])
    resp = make_response(
        jsonify(
            {
                "ok": True,
                "user": {
                    "id": row["id"],
                    "name": row["name"],
                    "role": row["role"],
                },
            }
        )
    )
    resp.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=SESSION_LIFETIME_DAYS * 86400,
        httponly=True,
        samesite="Lax",
    )
    return resp


@bp.route("/logout", methods=["POST"])
def logout():
    sid = g.get("sid")
    destroy_session(sid)
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@bp.route("/me", methods=["GET"])
def me():
    if not g.user:
        return jsonify({"error": "not logged in"}), 401
    return jsonify(g.user)