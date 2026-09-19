import pytest
from flask import Flask
from flask_app.models.database import db, User
from flask_app.services.admin_bootstrap import ensure_deployment_admin

@pytest.fixture
def context(monkeypatch):
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    for key, value in {"ENABLED":"true", "USERNAME":"deployadmin", "EMAIL":"admin@example.org", "PASSWORD":"initial-secret-123"}.items():
        monkeypatch.setenv("BOOTSTRAP_ADMIN_" + key, value)
    with app.app_context():
        db.create_all()
        yield
        db.session.remove(); db.drop_all()

def test_create_and_redeploy_preserve_credentials(context, monkeypatch):
    ensure_deployment_admin()
    user = User.query.one()
    assert user.role == "admin" and user.check_password("initial-secret-123")
    assert user.password_hash != "initial-secret-123"
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "replacement-secret-456")
    ensure_deployment_admin()
    assert User.query.count() == 1
    assert user.check_password("initial-secret-123")
    assert not user.check_password("replacement-secret-456")

def test_conflict_never_promotes_existing_user(context):
    user = User(username="deployadmin", email="admin@example.org", role="user")
    user.set_password("existing-password")
    db.session.add(user); db.session.commit()
    with pytest.raises(RuntimeError, match="其他账号"):
        ensure_deployment_admin()
    assert user.role == "user" and user.check_password("existing-password")

def test_disabled_and_invalid_configuration(context, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_ENABLED", "false")
    ensure_deployment_admin()
    assert User.query.count() == 0
    monkeypatch.setenv("BOOTSTRAP_ADMIN_ENABLED", "true")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
    with pytest.raises(RuntimeError, match="6–128"):
        ensure_deployment_admin()
    assert User.query.count() == 0


def test_six_character_admin_password(context, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "abc123")
    ensure_deployment_admin()
    assert User.query.one().check_password("abc123")
