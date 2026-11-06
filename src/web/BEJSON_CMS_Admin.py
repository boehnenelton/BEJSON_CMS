"""
Library:         BEJSON_CMS_Admin
Family:          BEJSON_CMS
Description:     Main admin app entry point. Registers the four BEJSON_CMS
                 blueprints (System, Content, Media, Interface) and starts
                 the Flask dev server. Route logic itself lives in the
                 blueprint files, not here.
Version:         18.24
Library_Version: 58
Date:            2026-10-25
RELATIONAL_ID:   e4c72a19-8b3d-4f62-9e10-5d8a1c3f7b92
"""

VERSION = 1824

import os
import logging
from flask import Flask

from BEJSON_CMS_Shared import (
    R, get_breadcrumbs, MFDB_DIR, ASSETS_DIR, PUBLISH_DIR,
    _USING_DEFAULT_PASSWORD, register_auth_guard, warn_about_legacy_files,
    ADMIN_PORT,
)
from BEJSON_CMS_System import system_cube
from BEJSON_CMS_Content import content_cube
from BEJSON_CMS_Media import media_cube
from BEJSON_CMS_Interface import interface_cube

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('CMS_SECRET_KEY') or os.urandom(24).hex()  # Set CMS_SECRET_KEY env var in production
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

app.register_blueprint(system_cube)
app.register_blueprint(content_cube)
app.register_blueprint(media_cube)
app.register_blueprint(interface_cube)

register_auth_guard(app)


@app.errorhandler(404)
def not_found(e):
    html = '''<div class="empty-state"><h1 style="font-size:4rem;color:var(--accent);">404</h1><h3>Page not found</h3><p>The page you\'re looking for doesn\'t exist.</p><br><a href="/" class="btn btn-primary">Go Home</a></div>'''
    return R(html, breadcrumbs=[{'label': '404', 'href': None}], active_section=''), 404


if __name__ == '__main__':
    warn_about_legacy_files()
    logging.info(f'''
    ============================================
    BEJSON Web Manager
    ============================================
    Data Directory: {MFDB_DIR}
    Assets Directory: {ASSETS_DIR}
    Publish Directory: {PUBLISH_DIR}

    Starting server on http://localhost:{ADMIN_PORT}
    Press CTRL+C to stop
    ============================================
    ''')
    if _USING_DEFAULT_PASSWORD:
        logging.warning('''
    !! WARNING: CMS_PASSWORD is not set - running with the default
    !! password ("changeme"). Anyone on your network can log in.
    !! Set the CMS_PASSWORD environment variable before exposing
    !! this beyond localhost.
        ''')
    # Port resolved via BEJSON_CMS_Shared: env var CMS_ADMIN_PORT > config.json
    # (admin_port) > 5001 default. See config.json / lib_bejson_CMS_cms_ports.py.
    app.run(host='127.0.0.1', port=ADMIN_PORT, debug=os.getenv('FLASK_DEBUG','0')=='1', threaded=True, use_reloader=False)

