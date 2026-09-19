"""Idempotent deployment administrator creation; never reset existing credentials."""
import os
import re
from flask import current_app
from sqlalchemy.exc import IntegrityError
from flask_app.models.database import User, db

def ensure_deployment_admin():
    if os.environ.get("BOOTSTRAP_ADMIN_ENABLED", "false").lower() not in {"true", "1", "yes"}:
        return
    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff-]{2,79}", username):
        raise RuntimeError("管理员初始化失败：BOOTSTRAP_ADMIN_USERNAME 格式不正确")
    if len(email) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise RuntimeError("管理员初始化失败：BOOTSTRAP_ADMIN_EMAIL 格式不正确")
    def existing_admin():
        existing = User.query.filter((User.username == username) | (User.email == email)).all()
        if not existing: return False
        if len(existing) != 1 or existing[0].username != username or existing[0].email != email or existing[0].role != "admin":
            raise RuntimeError("管理员初始化失败：用户名或邮箱已被其他账号使用，请修改初始化配置")
        return True
    if existing_admin(): return
    if not 6 <= len(password) <= 128:
        raise RuntimeError("管理员初始化失败：BOOTSTRAP_ADMIN_PASSWORD 需为 6–128 位")
    user = User(username=username, email=email, role="admin", allowed_paths=[])
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not existing_admin(): raise
    current_app.logger.info("部署管理员初始化完成")
