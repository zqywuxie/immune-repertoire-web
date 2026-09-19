"""Container startup and readiness must work with authentication enabled."""
import os
os.environ.setdefault('FLASK_CONFIG', 'testing')

from flask_app.app import create_app
from flask_app.config import ContainerConfig, ProductionConfig
from flask import Flask
import pytest

def test_health_remains_public_while_data_requires_login():
    app = create_app('testing')
    app.config['REQUIRE_LOGIN'] = True
    client = app.test_client()
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/files').status_code == 401

@pytest.mark.parametrize('configuration,secure', [(ContainerConfig, False), (ProductionConfig, True)])
def test_container_and_production_require_login_and_strong_secret(monkeypatch, configuration, secure):
    monkeypatch.setenv('SECRET_KEY', 'x' * 32)
    app = Flask(__name__)
    app.config['REQUIRE_LOGIN'] = True
    configuration.init_app(app)
    assert app.config['SESSION_COOKIE_SECURE'] is secure
    app.config['REQUIRE_LOGIN'] = False
    with pytest.raises(RuntimeError, match='REQUIRE_LOGIN'):
        configuration.init_app(app)
    app.config['REQUIRE_LOGIN'] = True
    monkeypatch.setenv('SECRET_KEY', 'short')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        configuration.init_app(app)
