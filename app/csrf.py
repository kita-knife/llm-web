import re
import secrets

from flask import abort, request, session


def generate_csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    if request.path.startswith("/api/") or request.path == "/chat/stream":
        return
    if re.match(r"^/chat/[^/]+/stream$", request.path):
        return
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf"):
        abort(400, description="CSRF token缺失或无效")