import json
import time
import uuid
from datetime import datetime, timezone

from agno.agent import Agent, RunEvent
from agno.models.openai.like import OpenAILike
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from ..db import get_conn, make_cursor, get_engine
from .chat_tools import get_current_time

bp = Blueprint("chat", __name__)


def _login_required(f):
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("pages.login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_session(session_id: str, user_id: int):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            """SELECT id, user_id, title, messages, pinned, model, created_at, updated_at
               FROM chat_sessions WHERE id=%s AND user_id=%s""",
            (session_id, user_id),
        )
        sess = cur.fetchone()
    if sess and isinstance(sess.get("messages"), str):
        try:
            sess["messages"] = json.loads(sess["messages"])
        except (json.JSONDecodeError, TypeError):
            sess["messages"] = []
    return sess


def _touch_session(session_id: str):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
            (session_id,),
        )
        conn.commit()


def _update_session_title(session_id: str, title: str):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            "UPDATE chat_sessions SET title = %s WHERE id = %s",
            (title, session_id),
        )
        conn.commit()


def _update_session_messages(session_id: str, messages: list):
    db = get_engine()
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            f"UPDATE chat_sessions SET messages = %s{db.json_cast_param()} WHERE id = %s",
            (json.dumps(messages, ensure_ascii=False), session_id),
        )
        conn.commit()


def _update_session_model(session_id: str, model: str):
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            "UPDATE chat_sessions SET model = %s WHERE id = %s",
            (model, session_id),
        )
        conn.commit()


def _build_agent(cfg):
    return Agent(
        model=OpenAILike(
            id=cfg["model"],
            api_key=cfg["api_key"],
            base_url=cfg["api_base"],
        ),
        tools=[get_current_time],
        markdown=False,
    )


def _mock_stream(prompt: str):
    msg = (
        "[Mock 模式] 尚未配置 LLM_API_KEY，请在 .env 设置后重启。\n"
        f"你刚才说：{prompt[:200]}"
    )
    for word in msg.split(" "):
        time.sleep(0.04)
        yield f"data: {json.dumps({'delta': word + ' '}, ensure_ascii=False)}\n\n"


@bp.route("/chat")
@_login_required
def chat_index():
    db = get_engine()
    new_id = str(uuid.uuid4())
    return redirect(url_for("chat.chat_session", session_id=new_id))


@bp.route("/chat/new", methods=["POST"])
@_login_required
def new_session():
    db = get_engine()
    new_id = str(uuid.uuid4())
    return redirect(url_for("chat.chat_session", session_id=new_id))


@bp.route("/chat/<session_id>", methods=["GET"])
@_login_required
def chat_session(session_id):
    db = get_engine()
    sess = _load_session(session_id, g.user["id"])
    if not sess:
        # 虚拟新会话（尚未写入 DB，首次发消息时才写入）
        return render_template(
            "chat.html",
            messages=[],
            session_id=session_id,
            session_title="新会话",
            pinned=False,
            model=current_app.config["LLM_MODEL"],
            api_configured=bool(current_app.config["LLM_API_KEY"]),
            current_session_id=session_id,
        )
    messages = sess.get("messages") or []
    return render_template(
        "chat.html",
        messages=messages,
        session_id=session_id,
        session_title=sess.get("title") or "新会话",
        pinned=bool(sess.get("pinned")),
        model=sess.get("model") or current_app.config["LLM_MODEL"],
        api_configured=bool(current_app.config["LLM_API_KEY"]),
        current_session_id=session_id,
    )


@bp.route("/chat/<session_id>/stream", methods=["POST"])
@_login_required
def chat_stream(session_id):
    db = get_engine()
    sess = _load_session(session_id, g.user["id"])
    current_model = current_app.config["LLM_MODEL"]
    if not sess:
        # 首次发消息：创建「草稿」session
        user_id = g.user["id"]
        with get_conn() as conn, make_cursor(conn) as cur:
            cur.execute(
                f"INSERT INTO chat_sessions (id, user_id, title, messages, model) VALUES (%s, %s, '新会话', {db.json_default_empty()}, %s)",
                (session_id, user_id, current_model),
            )
            conn.commit()
        sess = _load_session(session_id, user_id)
    else:
        _update_session_model(session_id, current_model)

    data = request.get_json(silent=True) or request.form.to_dict()
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        abort(400, description="empty prompt")

    user_id = g.user["id"]

    messages = list(sess.get("messages") or [])
    messages.append({"role": "user", "content": prompt, "ts": _now_iso()})

    is_first_turn = len(messages) == 1
    if is_first_turn or not sess.get("title") or sess["title"] == "新会话":
        new_title = prompt[:30] + ("..." if len(prompt) > 30 else "")
        _update_session_title(session_id, new_title)

    agno_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    cfg = {
        "api_key": current_app.config["LLM_API_KEY"],
        "api_base": current_app.config["LLM_API_BASE"],
        "model": current_model,
    }

    def generate():
        if not cfg["api_key"]:
            full = ""
            try:
                for chunk in _mock_stream(prompt):
                    try:
                        obj = json.loads(chunk[len("data: "):].strip().split("\n")[0])
                        full += obj.get("delta", "")
                    except Exception:
                        pass
                    yield chunk
                else:
                    yield "data: [DONE]\n\n"
            finally:
                if full.strip():
                    messages.append({"role": "assistant", "content": full.strip(), "ts": _now_iso()})
                    _update_session_messages(session_id, messages)
                _touch_session(session_id)
            return

        agent = _build_agent(cfg)
        full_response = ""
        full_thinking = ""
        try:
            stream = agent.run(
                input=agno_messages,
                stream=True,
                stream_events=True,
                user_id=str(user_id),
                session_id=session_id,
            )
            for event in stream:
                if event.event == RunEvent.run_content and getattr(event, "content", None):
                    delta = event.content
                    full_response += delta
                    yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                elif event.event == RunEvent.tool_call_started:
                    tool_name = getattr(getattr(event, "tool", None), "tool_name", "tool")
                    yield f"data: {json.dumps({'tool': tool_name, 'status': 'started'}, ensure_ascii=False)}\n\n"
                elif event.event == RunEvent.tool_call_completed:
                    tool_name = getattr(getattr(event, "tool", None), "tool_name", "tool")
                    yield f"data: {json.dumps({'tool': tool_name, 'status': 'done'}, ensure_ascii=False)}\n\n"
                elif event.event == RunEvent.run_error:
                    err = getattr(event, "content", str(event))
                    yield f"data: {json.dumps({'error': str(err)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        else:
            yield "data: [DONE]\n\n"
        finally:
            import re as _re
            if full_response:
                # 把 `` 块从主内容里剥出来
                thinking = _re.findall(r"<think>(.*?)</think>", full_response, _re.DOTALL)
                answer = _re.sub(r"<think>.*?</think>", "", full_response, flags=_re.DOTALL).strip()
                if thinking:
                    full_thinking = "\n\n".join(thinking).strip() or full_thinking
                messages.append({"role": "assistant", "content": answer, "thinking": full_thinking, "ts": _now_iso()})
                _update_session_messages(session_id, messages)
            _touch_session(session_id)

    return Response(generate(), mimetype="text/event-stream")


@bp.route("/chat/<session_id>/delete", methods=["POST"])
@_login_required
def delete_session(session_id):
    db = get_engine()
    sess = _load_session(session_id, g.user["id"])
    if not sess:
        abort(404)
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
        conn.commit()
    return redirect(url_for("chat.chat_index"))


@bp.route("/chat/<session_id>/rename", methods=["POST"])
@_login_required
def rename_session(session_id):
    db = get_engine()
    sess = _load_session(session_id, g.user["id"])
    if not sess:
        abort(404)
    new_title = (request.form.get("title") or "").strip()[:200]
    if not new_title:
        abort(400, description="empty title")
    _update_session_title(session_id, new_title)
    return redirect(url_for("chat.chat_session", session_id=session_id))


@bp.route("/chat/<session_id>/pin", methods=["POST"])
@_login_required
def pin_session(session_id):
    db = get_engine()
    sess = _load_session(session_id, g.user["id"])
    if not sess:
        abort(404)
    db = get_engine()
    with get_conn() as conn, make_cursor(conn) as cur:
        cur.execute(
            f"UPDATE chat_sessions SET pinned = {db.bool_toggle('pinned')} WHERE id = %s",
            (session_id,),
        )
        conn.commit()
    return redirect(url_for("chat.chat_session", session_id=session_id))