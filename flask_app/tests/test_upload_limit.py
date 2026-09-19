import os
import subprocess
import sys

from flask import request
from flask_app.tests.test_profile_workflow import profile_app


def test_configurable_limit():
    result = subprocess.run([sys.executable, '-c',
        'from flask_app.config import Config; assert Config.MAX_CONTENT_LENGTH == 7 * 1024 * 1024'],
        env={**os.environ, 'UPLOAD_MAX_MB': '7'}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_upload_rejection_is_chinese_and_uses_active_limit(profile_app):
    from flask_app.app import register_error_handlers
    register_error_handlers(profile_app)
    profile_app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
    @profile_app.post('/test-upload-limit')
    def upload():
        return str(len(request.get_data()))
    client = profile_app.test_client()
    assert client.post('/test-upload-limit', data=b'x').status_code == 200
    response = client.post('/test-upload-limit', data=b'x' * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json['error_code'] == 'FILE_TOO_LARGE'
    assert '1 兆字节' in response.json['message']
