from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_conn, make_cursor, get_engine
from ..extensions import limiter
from ..session import (
    SESSION_COOKIE,
    SESSION_LIFETIME_DAYS,
    create_session,
    destroy_session,
)

bp = Blueprint("pages", __name__)

VALID_ROLES = ("root", "admin", "user")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("pages.login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not g.get("user"):
                return redirect(url_for("pages.login", next=request.path))
            if g.user.get("role") not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def verify_credentials(name: str, password: str):
    if not name or not password:
        return None
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            "SELECT id, name, role, password_hash FROM users WHERE name = %s",
            (name,),
        )
        row = cur.fetchone()
    if not row or not row["password_hash"]:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return {"id": row["id"], "name": row["name"], "role": row["role"]}


def change_password(user_id: int, old_pwd: str, new_pwd: str, keep_sid: str | None = None):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row or not row["password_hash"]:
            return False, "用户不存在或未设置密码"
        if not check_password_hash(row["password_hash"], old_pwd):
            return False, "原密码错误"
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_pwd), user_id),
        )
        if keep_sid:
            cur.execute(
                "DELETE FROM login_sessions WHERE user_id = %s AND sid != %s",
                (user_id, keep_sid),
            )
        else:
            cur.execute(
                "DELETE FROM login_sessions WHERE user_id = %s",
                (user_id,),
            )
        conn.commit()
    return True, None


def load_user(user_id: int):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("SELECT id, name, role FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def count_roots() -> int:
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE role='root'")
        return cur.fetchone()["n"]


def _can_manage(target_user, me) -> tuple:
    """viewer (me) 能否管理 target_user (edit/delete).
    返回 (ok: bool, reason: str|None)
    """
    if me["role"] == "user":
        return False, "无权管理用户"
    if target_user["role"] == "root" and target_user["id"] != me["id"]:
        return False, "不能管理其他 root 用户"
    if me["role"] == "admin" and target_user["role"] in ("admin", "root") and target_user["id"] != me["id"]:
        return False, "admin 只能管理 user 角色"
    return True, None


def _can_create_role(target_role: str, me) -> bool:
    if target_role not in ("root", "admin", "user"):
        return False
    if me["role"] == "admin" and target_role == "root":
        return False
    return True


def _can_change_role(target_user, me, new_role: str = None) -> tuple:
    """viewer 能否改 target 的 role 字段（含 new_role 校验）"""
    if me["role"] == "root":
        if target_user["role"] == "root" and new_role != "root" and count_roots() <= 1:
            return (False, "至少保留一个 root")
        if new_role == "root" and target_user["role"] != "root" and count_roots() >= 10:
            return (False, "root 用户过多")
        return (True, None)
    if me["role"] == "admin":
        if new_role == "root":
            return (False, "admin 不能把任何人设为 root")
        if target_user["id"] == me["id"] and new_role == "user":
            return (True, None)
        if target_user["id"] != me["id"] and new_role in ("admin", "user"):
            return (True, None)
        return (True, None)
    return (False, "无权修改 role")


def _set_session_cookie(resp, sid: str):
    resp.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=SESSION_LIFETIME_DAYS * 86400,
        httponly=True,
        samesite="Lax",
    )


@bp.route("/")
def home():
    return render_template("home.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5/minute", methods=["POST"])
def login():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        user = verify_credentials(name, password)
        if not user:
            error = "用户名或密码错误"
        else:
            sid, _ = create_session(user["id"])
            nxt = request.args.get("next") or request.form.get("next") or url_for(
                "pages.home"
            )
            resp = redirect(nxt)
            _set_session_cookie(resp, sid)
            flash(f"欢迎回来，{user['name']}", "success")
            return resp
    return render_template(
        "login.html",
        error=error,
        next=request.args.get("next", ""),
    )


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("3/hour", methods=["POST"])
def register():
    """公开注册：只能创建 'user' 角色。"""
    db = get_engine()
    error = None
    form = {"name": ""}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        form = {"name": name}
        if not name or not password:
            error = "用户名和密码必填"
        elif len(password) < 4:
            error = "密码至少 4 位"
        if not error:
            try:
                with get_conn() as conn, make_cursor(conn) as cur:
                    new_id = db.insert_with_id(cur, "users",
                                               ["name", "password_hash", "role"],
                                               [name, generate_password_hash(password), "user"])
                    conn.commit()
            except db.integrity_error:
                error = "用户名已存在"
            except Exception as e:
                error = f"数据库错误：{e}"
        if not error:
            sid, _ = create_session(new_id)
            resp = redirect(url_for("pages.home"))
            _set_session_cookie(resp, sid)
            flash("注册成功！", "success")
            return resp
    return render_template("register.html", error=error, form=form)


def _humanize_time(dt):
    """把 datetime 转成人类可读的相对时间。"""
    if not dt:
        return "从未"
    delta = datetime.utcnow() - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "刚刚"
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


def _kick_perm(target_user, me) -> bool:
    """me 能否踢 target_user 下线。"""
    if target_user["id"] == me["id"]:
        return False
    if me["role"] == "admin" and target_user["role"] != "user":
        return False
    return True


@bp.route("/users", methods=["GET"])
@role_required("admin", "root")
def users_list():
    db = get_engine()
    refreshed = request.args.get("refresh") == "1"
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(f"""
            SELECT u.id, u.name, u.role,
                   MAX(s.last_active_at) AS last_active,
                   EXISTS(
                     SELECT 1 FROM login_sessions s2
                       WHERE s2.user_id = u.id
                         AND s2.expires_at > {db.now_utc()}
                         AND s2.last_active_at > {db.now_utc()} - INTERVAL '5 minute'
                   ) AS is_online
              FROM users u
              LEFT JOIN login_sessions s ON s.user_id = u.id
             GROUP BY u.id, u.name, u.role
             ORDER BY u.id
        """)
        users = cur.fetchall()
    me_id = g.user["id"]
    manage_perms = {}
    delete_perms = {}
    kick_perms = {}
    for u in users:
        u["last_active_human"] = _humanize_time(u["last_active"])
        can_m, _ = _can_manage(u, g.user)
        manage_perms[u["id"]] = can_m
        can_del = can_m and u["id"] != me_id and not (u["role"] == "root" and count_roots() <= 1)
        delete_perms[u["id"]] = can_del
        kick_perms[u["id"]] = _kick_perm(u, g.user)
    return render_template(
        "users/list.html",
        users=users,
        me_id=me_id,
        manage_perms=manage_perms,
        delete_perms=delete_perms,
        kick_perms=kick_perms,
        refreshed=refreshed,
    )


@bp.route("/users/<int:user_id>/kick", methods=["POST"])
@role_required("admin", "root")
def users_kick(user_id):
    me = g.user
    target = load_user(user_id)
    if not target:
        abort(404)
    if target["id"] == me["id"]:
        flash("不能踢自己下线", "error")
        return redirect(url_for("pages.users_list"))
    if me["role"] == "admin" and target["role"] != "user":
        flash("admin 只能踢 user 角色", "error")
        return redirect(url_for("pages.users_list"))
    if target["role"] == "root" and count_roots() <= 1:
        flash("至少保留一个 root", "error")
        return redirect(url_for("pages.users_list"))
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("DELETE FROM login_sessions WHERE user_id = %s", (user_id,))
        conn.commit()
    flash(f"已踢 {target['name']} 下线", "success")
    return redirect(url_for("pages.users_list"))


@bp.route("/users/new", methods=["GET", "POST"], strict_slashes=False)
@role_required("admin", "root")
def users_new():
    db = get_engine()
    me = g.user
    available_roles = ("admin", "user") if me["role"] == "admin" else VALID_ROLES
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "user")
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        if role not in VALID_ROLES:
            error = "无效的角色"
        elif not _can_create_role(role, me):
            error = "无权创建该角色"
        elif not name:
            error = "用户名必填"
        elif not password:
            error = "密码必填"
        elif len(password) < 4:
            error = "密码至少 4 位"
        elif password != password_confirm:
            error = "两次密码输入不一致"
        else:
            try:
                with get_conn() as conn, make_cursor(conn) as cur:
                    cur.execute(
                        """INSERT INTO users (name, password_hash, role)
                           VALUES (%s, %s, %s)""",
                        (name, generate_password_hash(password), role),
                    )
                    conn.commit()
            except db.integrity_error:
                error = "用户名已存在"
            except Exception as e:
                error = f"数据库错误：{e}"
        if not error:
            flash("已创建用户", "success")
            return redirect(url_for("pages.users_list"))
    return render_template(
        "users/new.html",
        error=error,
        available_roles=available_roles,
    )


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"], strict_slashes=False)
@login_required
def users_edit(user_id):
    db = get_engine()
    me = g.user
    target = load_user(user_id)
    if not target:
        abort(404)
    can, reason = _can_manage(target, me)
    if not can:
        abort(403, description=reason)
    is_self = me["id"] == user_id
    if me["role"] == "admin":
        available_roles = ("admin", "user") if is_self else ("user",)
    else:
        available_roles = VALID_ROLES

    error = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", target["role"])
        # 内联权限检查
        role_allowed = True
        role_reason = None
        if me["role"] == "root":
            if target["role"] == "root" and role != "root" and count_roots() <= 1:
                role_allowed = False
                role_reason = "至少保留一个 root"
        elif me["role"] == "admin":
            if role == "root":
                role_allowed = False
                role_reason = "admin 不能把任何人设为 root"
        else:
            role_allowed = False
            role_reason = "无权修改 role"

        if not name:
            error = "用户名必填"
        elif role not in VALID_ROLES:
            error = "无效的角色"
        elif not _can_create_role(role, me):
            error = "无权创建该角色"
        elif not role_allowed:
            error = role_reason or "无权修改该用户的 role"
        elif (
            target["role"] == "root"
            and role != "root"
            and count_roots() <= 1
        ):
            error = "至少保留一个 root"
        else:
            try:
                with get_conn() as conn, make_cursor(conn) as cur:
                    # user 自己改只能改 name（不能改 role）
                    if me["role"] == "user":
                        cur.execute(
                            "UPDATE users SET name=%s WHERE id=%s",
                            (name, user_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE users SET name=%s, role=%s WHERE id=%s",
                            (name, role, user_id),
                        )
                    if cur.rowcount == 0:
                        conn.rollback()
                        abort(404)
                    conn.commit()
            except db.integrity_error:
                error = "用户名已存在"
            except Exception as e:
                error = f"数据库错误：{e}"
        if not error:
            flash("已更新", "success")
            return redirect(url_for("pages.users_list"))

    return render_template(
        "users/edit.html",
        user=target,
        error=error,
        available_roles=available_roles,
        is_self=is_self,
    )


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin", "root")
def users_delete(user_id):
    me = g.user
    if user_id == me["id"]:
        abort(400, description="不能删除自己")
    target = load_user(user_id)
    if not target:
        abort(404)
    can, reason = _can_manage(target, me)
    if not can:
        abort(403, description=reason)
    if target["role"] == "root" and count_roots() <= 1:
        abort(400, description="至少保留一个 root")
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if cur.rowcount == 0:
            conn.rollback()
            abort(404)
        conn.commit()
    flash("已删除", "success")
    return redirect(url_for("pages.users_list"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_engine()
    user = g.user
    error = None
    pwd_error = None
    if request.method == "POST":
        action = request.form.get("action", "update")
        if action == "update":
            name = request.form.get("name", "").strip()
            if not name:
                error = "用户名必填"
            else:
                try:
                    with get_conn() as conn, make_cursor(conn) as cur:
                        cur.execute(
                            "UPDATE users SET name=%s WHERE id=%s",
                            (name, user["id"]),
                        )
                        conn.commit()
                        cur.execute(
                            "SELECT id, name, role FROM users WHERE id = %s",
                            (user["id"],),
                        )
                        new = cur.fetchone()
                    g.user = new
                    user = new
                    flash("资料已更新", "success")
                    return redirect(url_for("pages.profile"))
                except db.integrity_error:
                    error = "用户名已存在"
                except Exception as e:
                    error = f"数据库错误：{e}"
        elif action == "change_password":
            old_pwd = request.form.get("old_password", "")
            new_pwd = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not old_pwd or not new_pwd:
                pwd_error = "请填写完整"
            elif new_pwd != confirm:
                pwd_error = "两次新密码不一致"
            elif len(new_pwd) < 4:
                pwd_error = "新密码至少 4 位"
            else:
                ok, msg = change_password(user["id"], old_pwd, new_pwd, keep_sid=g.get("sid"))
                if ok:
                    flash("密码已修改", "success")
                    return redirect(url_for("pages.profile"))
                pwd_error = msg
    return render_template(
        "profile.html",
        user=user,
        error=error,
        pwd_error=pwd_error,
    )


@bp.route("/logout", methods=["POST"])
def logout():
    sid = g.get("sid")
    destroy_session(sid)
    resp = redirect(url_for("pages.home"))
    resp.delete_cookie(SESSION_COOKIE)
    flash("已退出登录", "success")
    return resp