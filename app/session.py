import secrets
from datetime import datetime, timedelta

from flask import g, request

from .db import get_conn, make_cursor, get_engine

SESSION_COOKIE = "webtest1_sid"
SESSION_LIFETIME_DAYS = 7


def create_session(user_id: int):
    sid = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=SESSION_LIFETIME_DAYS)
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            "INSERT INTO login_sessions (sid, user_id, expires_at) VALUES (%s, %s, %s)",
            (sid, user_id, expires_at),
        )
        conn.commit()
    return sid, expires_at


def load_session():
    from .db import get_engine; db = get_engine()
    g.user = None
    g.sid = None
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            f"""
            SELECT s.sid AS sid,
                   s.expires_at AS expires_at,
                   u.id AS id, u.name AS name, u.role AS role
            FROM login_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.sid = %s AND s.expires_at > {db.now_utc()}
            """,
            (sid,),
        )
        row = cur.fetchone()
    if row:
        g.sid = row["sid"]
        g.user = {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
        }


def destroy_session(sid: str):
    if not sid:
        return
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("DELETE FROM login_sessions WHERE sid = %s", (sid,))
        conn.commit()


def clear_expired_sessions():
    from .db import get_engine; db = get_engine()
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(f"DELETE FROM login_sessions WHERE expires_at <= {db.now_utc()}")
        conn.commit()