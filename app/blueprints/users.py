from functools import wraps

from flask import Blueprint, g, jsonify, request

from ..db import get_conn, make_cursor, get_engine
from .pages import VALID_ROLES, _can_change_role, _can_create_role, _can_manage, count_roots

bp = Blueprint("users", __name__)


def _role_required(*allowed):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not g.get("user"):
                return jsonify({"error": "not logged in"}), 401
            if g.user.get("role") not in allowed:
                return jsonify({"error": "需要 admin 或 root 权限"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _load_user(user_id: int):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("SELECT id, name, role FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


@bp.route("/", methods=["GET"], strict_slashes=False)
@_role_required("admin", "root")
def list_users():
    try:
        with get_conn() as conn, make_cursor(conn) as cur:
            cur.execute("SELECT id, name, role FROM users ORDER BY id")
            rows = cur.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/", methods=["POST"], strict_slashes=False)
@_role_required("admin", "root")
def create_user():
    """API 创建用户：密码请走 /users/new 页面。"""
    return jsonify({
        "error": "API 创建用户请用 /users/new 页面（含密码字段）"
    }), 400


@bp.route("/<int:user_id>", methods=["GET"])
@_role_required("admin", "root")
def get_user(user_id):
    try:
        row = _load_user(user_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if row is None:
        return jsonify({"error": "user not found", "id": user_id}), 404
    return jsonify(row)


@bp.route("/<int:user_id>", methods=["PUT"])
@_role_required("admin", "root")
def update_user(user_id):
    db = get_engine()
    me = g.user
    target = _load_user(user_id)
    if target is None:
        return jsonify({"error": "user not found", "id": user_id}), 404
    can, reason = _can_manage(target, me)
    if not can:
        return jsonify({"error": reason}), 403

    data = request.get_json(silent=True) or {}
    fields, values = [], []

    if "name" in data:
        if not data["name"].strip():
            return jsonify({"error": "name 不能为空"}), 400
        fields.append("name = %s")
        values.append(data["name"].strip())

    if "role" in data:
        if data["role"] not in VALID_ROLES:
            return jsonify({"error": "invalid role"}), 400
        if not _can_create_role(data["role"], me):
            return jsonify({"error": "无权创建该角色"}), 403
        can_change, cc_reason = _can_change_role(target, me, data["role"])
        if not can_change:
            return jsonify({"error": cc_reason or "无权修改 role"}), 403
        if target["role"] == "root" and data["role"] != "root" and count_roots() <= 1:
            return jsonify({"error": "至少保留一个 root"}), 400
        fields.append("role = %s")
        values.append(data["role"])

    if not fields:
        return jsonify({"error": "no updatable field provided"}), 400

    values.append(user_id)
    try:
        with get_conn() as conn, make_cursor(conn) as cur:
            cur.execute(
                f"UPDATE users SET {', '.join(fields)} WHERE id = %s", values
            )
            if cur.rowcount == 0:
                conn.rollback()
                return jsonify({"error": "user not found", "id": user_id}), 404
            conn.commit()
            cur.execute(
                "SELECT id, name, role FROM users WHERE id = %s", (user_id,)
            )
            row = cur.fetchone()
        return jsonify(row)
    except db.integrity_error:
        return jsonify({"error": "name already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<int:user_id>", methods=["DELETE"])
@_role_required("admin", "root")
def delete_user(user_id):
    me = g.user
    if user_id == me["id"]:
        return jsonify({"error": "不能删除自己"}), 400
    target = _load_user(user_id)
    if target is None:
        return jsonify({"error": "user not found", "id": user_id}), 404
    can, reason = _can_manage(target, me)
    if not can:
        return jsonify({"error": reason}), 403
    if target["role"] == "root" and count_roots() <= 1:
        return jsonify({"error": "至少保留一个 root"}), 400
    try:
        with get_conn() as conn, make_cursor(conn) as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            if cur.rowcount == 0:
                conn.rollback()
                return jsonify({"error": "user not found", "id": user_id}), 404
            conn.commit()
        return "", 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500