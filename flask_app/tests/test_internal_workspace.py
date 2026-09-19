"""Internal access must share existing projects without exposing host paths."""
import pytest
from flask import Flask
from flask_app.app import create_app
from flask_app.config import InternalConfig, ProductionConfig
from flask_app.models.database import db, User, Project
from flask_app.services.internal_workspace import internal_redirect
from flask_app.services.path_access_service import PathAccessService
from flask_app.exceptions import ValidationError


def test_internal_config_does_not_weaken_production(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'x' * 32)
    app = Flask(__name__)
    app.config.from_object(InternalConfig)
    InternalConfig.init_app(app)
    assert not app.config['REQUIRE_LOGIN']
    assert not app.config['AUTH_REGISTER_ENABLED']
    with pytest.raises(RuntimeError, match='REQUIRE_LOGIN'):
        ProductionConfig.init_app(app)


@pytest.mark.parametrize('target', ['https://example.com', '//example.com', '/%2fexample.com', '/\\example.com', '/login', '/auth/register'])
def test_redirect_stays_in_workspace(target):
    assert internal_redirect(target) == '/management'


def test_internal_session_does_not_filter_existing_owners(tmp_path):
    app = create_app('testing')
    app.config.update(INTERNAL_MODE=True, REQUIRE_LOGIN=False, ALLOWED_BASE_PATHS=[str(tmp_path)])
    with app.app_context():
        a = User(username='one', email='one@example.test')
        b = User(username='two', email='two@example.test')
        a.set_password('test-password')
        b.set_password('test-password')
        db.session.add_all([a, b]); db.session.flush()
        db.session.add_all([Project(id='one', name='项目一', user_id=a.id), Project(id='two', name='项目二', user_id=b.id)])
        db.session.commit()
        owner_id = a.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(owner_id)
        session['_fresh'] = True
    assert client.get('/api/auth/me').json['auth_mode'] == 'internal'
    with app.test_request_context('/api/projects'):
        app.preprocess_request()
        from flask_app.services.user_scope import scope_query, current_user_id
        assert current_user_id() is None
        assert scope_query(Project.query, Project).count() == 2
        PathAccessService.validate_write_path(tmp_path / 'result.csv')
        with pytest.raises(ValidationError):
            PathAccessService.validate_read_path('/app/flask_app/config.py')
    response = client.get('/auth/register')
    assert response.status_code == 302 and response.location == '/management'
    response = client.get('/auth/login?next=/analysis/center')
    assert response.location == '/analysis/center'
    with app.app_context():
        assert db.session.get(Project, 'one').user_id == owner_id
        db.session.remove(); db.drop_all()
