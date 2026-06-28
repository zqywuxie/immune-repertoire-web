"""Authentication routes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from flask_app.models.database import User, db


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _next_url() -> str:
    target = request.args.get("next") or request.form.get("next") or url_for("pages.analysis_page")
    if not str(target).startswith("/"):
        return url_for("pages.analysis_page")
    return target


def _default_home_path(username: str) -> str:
    root = Path(current_app.config.get("USER_DATA_ROOT"))
    path = root / username
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_next_url())

    if request.method == "POST":
        identifier = str(request.form.get("identifier") or "").strip()
        password = str(request.form.get("password") or "")
        user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
        if not user or not user.check_password(password) or not user.is_active:
            flash("用户名、邮箱或密码不正确。", "danger")
            return render_template("auth/login.html", next_url=_next_url()), 401

        user.last_login_at = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=str(request.form.get("remember") or "").lower() in {"1", "on", "true"})
        return redirect(_next_url())

    return render_template("auth/login.html", next_url=_next_url())


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config.get("AUTH_REGISTER_ENABLED", True):
        flash("当前环境未开放注册，请联系管理员创建账号。", "warning")
        return redirect(url_for("auth.login"))
    if current_user.is_authenticated:
        return redirect(url_for("pages.analysis_page"))

    if request.method == "POST":
        username = str(request.form.get("username") or "").strip()
        email = str(request.form.get("email") or "").strip().lower()
        password = str(request.form.get("password") or "")
        confirm = str(request.form.get("confirm_password") or "")

        if not username or not email or not password:
            flash("请填写用户名、邮箱和密码。", "danger")
            return render_template("auth/register.html"), 400
        if password != confirm:
            flash("两次输入的密码不一致。", "danger")
            return render_template("auth/register.html"), 400
        if len(password) < 8:
            flash("密码长度至少 8 位。", "danger")
            return render_template("auth/register.html"), 400
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("用户名或邮箱已存在。", "danger")
            return render_template("auth/register.html"), 409

        role = "user"
        if current_app.config.get("AUTH_FIRST_USER_ADMIN", True) and User.query.count() == 0:
            role = "admin"

        user = User(
            username=username,
            email=email,
            role=role,
            home_path=_default_home_path(username),
            allowed_paths=current_app.config.get("DEFAULT_USER_ALLOWED_PATHS", []),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("pages.analysis_page"))

    return render_template("auth/register.html")


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
