from flask import Blueprint, jsonify

from ..db import get_conn

bp = Blueprint("db_check", __name__)


@bp.route("/api/db-check")
def db_check():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS v, NOW() AS t")
            row = cur.fetchone()
        return jsonify(
            {
                "ok": True,
                "mysql_version": row["v"],
                "server_time": str(row["t"]),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500