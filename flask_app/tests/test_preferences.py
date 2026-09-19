import io
import struct
from unittest.mock import patch
from flask import Flask
from flask_app.models.database import db
from flask_app.routes.api.config_params import bp
from flask_app.services.config_service import init_config_service
from flask_app.services.figure_export import save_analysis_figure


def test_preferences_roundtrip_and_account_isolation():
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    app.register_blueprint(bp, url_prefix='/api')
    with app.app_context():
        init_config_service(app)
        client = app.test_client()
        with patch('flask_app.routes.api.config_params.current_user_id', return_value=1):
            saved = client.post('/api/config', json={'config_id':'analysis','config':{'default_dpi':150,'default_figure_size':[6,4]}})
            assert saved.status_code == 200
            assert client.get('/api/config?config_id=analysis').json['config']['default_dpi'] == 150
            from flask_app.services.config_service import ConfigService
            assert ConfigService().validate_config({'default_figure_size':[0,999]})
            # This minimal fixture has no application error handler; validate service directly below.
        with patch('flask_app.routes.api.config_params.current_user_id', return_value=2):
            assert client.get('/api/config?config_id=analysis').json['config']['default_dpi'] == 300
        db.session.remove(); db.drop_all()


def test_export_uses_requested_size_dpi_and_font():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([1,2], [3,4])
    buf = io.BytesIO()
    try:
        save_analysis_figure(fig, buf, {'chart_config':{'figsize':[5,4],'dpi':100,'font_size':18}})
        assert list(fig.get_size_inches()) == [5,4]
        assert ax.xaxis.get_ticklabels()[0].get_fontsize() > 12
        width,height = struct.unpack('>II',buf.getvalue()[16:24])
        assert 350 < width < 600 and 300 < height < 500
    finally:
        plt.close(fig)
