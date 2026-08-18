"""
Library:         BEJSON_CMS_Admin
Family:          BEJSON_CMS
Description:     Main admin app entry point. Registers the four BEJSON_CMS
                 blueprints (System, Content, Media, Interface) and starts
                 the Flask dev server. Route logic itself lives in the
                 blueprint files, not here.
Version:         18.23
Library_Version: 57
Date:            2026-08-05
RELATIONAL_ID:   92a355a8-4e01-4931-b359-275920b91a2c
"""

import os
from flask import Flask, request

from BEJSON_CMS_Shared import (
    R, get_breadcrumbs, MFDB_DIR, ASSETS_DIR, PUBLISH_DIR,
    _USING_DEFAULT_PASSWORD, _check_auth, _unauthorized, warn_about_legacy_files,
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


@app.before_request
def _enforce_auth_everywhere():
    # SECURITY FIX: @require_auth was only ever applied to 2 routes total
    # (the dashboard "/" and one API endpoint) out of roughly 50 across the
    # 4 blueprints -- an incomplete carryover from before the Blueprint
    # split, which left page create/edit/delete, media upload/delete/
    # bulk-delete, database export, site config, and factory reset all
    # completely open to unauthenticated requests. This enforces the exact
    # same check on every single request, once, in one place, so no future
    # route can accidentally ship without it. The per-route @require_auth
    # decorators that already existed are now redundant but harmless.
    Request_Basic_Auth_Header = request.authorization
    if not Request_Basic_Auth_Header or not _check_auth(Request_Basic_Auth_Header.username, Request_Basic_Auth_Header.password):
        return _unauthorized()


@app.errorhandler(404)
def not_found(e):
    html = '''<div class="empty-state"><h1 style="font-size:4rem;color:var(--accent);">404</h1><h3>Page not found</h3><p>The page you\'re looking for doesn\'t exist.</p><br><a href="/" class="btn btn-primary">Go Home</a></div>'''
    return R(html, breadcrumbs=[{'label': '404', 'href': None}], active_section=''), 404


if __name__ == '__main__':
    warn_about_legacy_files()
    print(f'''
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
        print('''
    !! WARNING: CMS_PASSWORD is not set - running with the default
    !! password ("changeme"). Anyone on your network can log in.
    !! Set the CMS_PASSWORD environment variable before exposing
    !! this beyond localhost.
        ''')
    # Port resolved via BEJSON_CMS_Shared: env var CMS_ADMIN_PORT > config.json
    # (admin_port) > 5001 default. See config.json / lib_bejson_CMS_cms_ports.py.
    app.run(host='127.0.0.1', port=ADMIN_PORT, debug=os.getenv('FLASK_DEBUG','0')=='1', threaded=True, use_reloader=False)
