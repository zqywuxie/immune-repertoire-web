"""Session authentication for the React application."""
import re
import secrets
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from flask_app.models.database import User, db

api_auth_bp = Blueprint("api_auth", __name__, url_prefix="/api/auth")


def principal(user):
    return {"user_id": user.id, "username": user.username, "email": user.email,
            "role": user.role, "auth_mode": "session"}


@api_auth_bp.before_request
def protect_auth_mutations():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = session.get("auth_csrf", "")
    if not expected or not secrets.compare_digest(supplied, expected):
        return jsonify(success=False, message="页面会话已失效，请刷新后重试。"), 403
    if not request.is_json:
        return jsonify(success=False, message="请求必须使用有效的表单数据。"), 415


@api_auth_bp.get("/options")
def options():
    if "auth_csrf" not in session:
        session["auth_csrf"] = secrets.token_urlsafe(32)
    response = jsonify(csrf_token=session["auth_csrf"],
                       registration_enabled=bool(current_app.config.get("AUTH_REGISTER_ENABLED", True)))
    response.headers["Cache-Control"] = "no-store"
    return response


def establish_session(user):
    session.clear()
    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    return jsonify(success=True, user=principal(user))


@api_auth_bp.post("/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, message="登录信息格式错误。"), 400
    identifier = str(data.get("username") or "").strip()
    password = data.get("password")
    user = User.query.filter((User.username == identifier) | (User.email == identifier.lower())).first()
    if not isinstance(password, str) or not user or not user.is_active or not user.check_password(password):
        return jsonify(success=False, message="用户名、邮箱或密码不正确。"), 401
    return establish_session(user)


@api_auth_bp.post("/register")
def register():
    if not current_app.config.get("AUTH_REGISTER_ENABLED", True):
        return jsonify(success=False, message="当前未开放注册，请联系管理员。"), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, message="注册信息格式错误。"), 400
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff-]{2,79}", username):
        return jsonify(success=False, message="用户名需为 3–80 位中文、字母、数字、下划线或短横线。"), 400
    if len(email) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(success=False, message="请输入有效邮箱。"), 400
    if not isinstance(password, str) or not 6 <= len(password) <= 128:
        return jsonify(success=False, message="密码长度需为 6–128 位。"), 400
    if password != data.get("confirm_password"):
        return jsonify(success=False, message="两次输入的密码不一致。"), 400
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify(success=False, message="用户名或邮箱已存在。"), 409
    user = User(username=username, email=email, role="user", allowed_paths=[])
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=False, message="用户名或邮箱已存在。"), 409
    return establish_session(user)


@api_auth_bp.post("/logout")
def logout():
    logout_user()
    session.clear()
    return jsonify(success=True)
