"""
Library:         BEJSON_CMS_Interface
Family:          BEJSON_CMS
Description:     Interface Cube: Dashboard, Navigation manager, Social Links, Ad Unit manager, Publish trigger UI. NAV_SECTIONS/base template/R() live in BEJSON_CMS_Shared (not here) since Content/Media/System routes render through them too.
Version:         18.23
Library_Version: 57
Date:            2026-08-05
RELATIONAL_ID:   0eb4cd90-6e13-4e0e-a8ad-a75238989e4f
"""

import os
import uuid
from flask import Blueprint, request, redirect, flash

from BEJSON_CMS_Shared import (
    db, R, get_breadcrumbs, get_image_assets, require_auth,
    ASSETS_DIR, PUBLISH_DIR, _USING_DEFAULT_PASSWORD, PUBLISHER_PORT,
)

interface_cube = Blueprint('interface', __name__)

@interface_cube.route('/')
@require_auth
def dashboard():
    db.mount()
    stats = {
        'pages': len([r for r in db.get_records("PageRecord") if r.get('page_type') != 'external_link']),
        'apps': len(db.get_records("StandaloneApp")),
        'categories': len(db.get_records("Category")),
        'ads': len(db.get_records("AdUnit")),
        'assets': len(db.get_records("MediaAsset")),
    }
    pages = db.get_records("PageRecord")
    pages.sort(key=lambda x: x.get('page_created_at', ''), reverse=True)
    recent = [{'title': p.get('page_title'), 'type': p.get('page_type', 'page'), 'date': p.get('page_created_at', 'N/A'), 'uuid': p.get('page_uuid')} for p in pages[:5]]
    

    security_banner = ''
    if _USING_DEFAULT_PASSWORD:
        security_banner = '''
        <div class="alert alert-error" style="margin-bottom:20px;">
            <strong>Security warning:</strong> CMS_PASSWORD is not set — this app is running with the
            default password ("changeme"). Anyone who can reach this server can log in. Set the
            CMS_PASSWORD environment variable before exposing this beyond localhost.
        </div>'''

    html = '''
    ''' + security_banner + '''
    <div class="page-header"><h1>Dashboard</h1><p>BEJSON Content Management System</p></div>
    <div class="grid grid-4 grid-stat" style="margin-bottom: 24px;">
        <div class="stat-card"><div class="stat-icon">&#128196;</div><div><div class="stat-value">{{ stats.pages }}</div><div class="stat-label">Pages</div></div></div>
        <div class="stat-card"><div class="stat-icon">&#128640;</div><div><div class="stat-value">{{ stats.apps }}</div><div class="stat-label">Applications</div></div></div>
        <div class="stat-card"><div class="stat-icon">&#128193;</div><div><div class="stat-value">{{ stats.categories }}</div><div class="stat-label">Categories</div></div></div>
        <div class="stat-card"><div class="stat-icon">&#128444;</div><div><div class="stat-value">{{ stats.assets }}</div><div class="stat-label">Assets</div></div></div>
    </div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Recent Content</span><a href="/pages" class="btn btn-secondary btn-sm">View All</a></div>
            {% if recent %}<div class="table-container"><table><thead><tr><th>Title</th><th>Type</th><th>Date</th><th>Actions</th></tr></thead><tbody>{% for item in recent %}<tr><td>{{ item.title }}</td><td><span class="badge badge-{{ item.type }}">{{ item.type }}</span></td><td>{{ item.date }}</td><td><a href="/edit/{{ item.uuid }}" class="btn btn-primary btn-sm">Edit</a></td></tr>{% endfor %}</tbody></table></div>
            {% else %}<div class="empty-state"><h3>No content yet</h3><p>Create your first page to get started</p><br><a href="/pages/new" class="btn btn-primary">Create Page</a></div>{% endif %}
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Quick Actions</span></div>
            <div class="quick-actions">
                <a href="/pages/new" class="quick-action-btn"><span class="icon">&#10133;</span><span class="label">New Page</span></a>
                <a href="/apps/new" class="quick-action-btn"><span class="icon">&#128230;</span><span class="label">Import App</span></a>
                <a href="/assets" class="quick-action-btn"><span class="icon">&#128228;</span><span class="label">Upload Asset</span></a>
                <a href="/site/ads" class="quick-action-btn"><span class="icon">&#128226;</span><span class="label">Manage Ads</span></a>
                <a href="{{ publisher_url }}" target="_blank" rel="noopener noreferrer" class="quick-action-btn"><span class="icon">&#127760;</span><span class="label">Open Publisher</span></a>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title">System Status</span></div>
        <div class="system-status-grid" style="color: var(--text-secondary); display: grid; grid-template-columns: repeat(auto-fit, minmax(min(250px,100%), 1fr)); gap: 12px;">
            <p><strong>Database:</strong> &#9989; Connected</p>
            <p><strong>Assets Dir:</strong> <code style="background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; word-break: break-all; font-size: 0.8rem;">{{ assets_dir }}</code></p>
            <p><strong>Publish Dir:</strong> <code style="background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; word-break: break-all; font-size: 0.8rem;">{{ publish_dir }}</code></p>
            <p><strong>Active Ads:</strong> {{ stats.ads }}</p>
        </div>
    </div>'''
    return R(html, stats=stats, recent=recent, assets_dir=ASSETS_DIR, publish_dir=PUBLISH_DIR,
             publisher_url=f"http://localhost:{PUBLISHER_PORT}/",
             breadcrumbs=get_breadcrumbs(request.path), active_section='dashboard')


# =============================================================================
# ROUTES — CONTENT
# =============================================================================


@interface_cube.route('/site/nav', methods=['GET', 'POST'])
def site_nav():
    db.mount()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            label = request.form.get('nav_display_label', '').strip()
            Submitted_Nav_Link_Url = request.form.get('nav_target_url', '').strip()
            if label and Submitted_Nav_Link_Url:
                db.add_record("NavLink", {"nav_display_label": label, "nav_target_url": Submitted_Nav_Link_Url})
        elif action == 'delete':
            label = request.form.get('nav_display_label', '')
            db.delete_record("NavLink", "nav_display_label", label)
        db.commit()
        
        flash('Navigation updated.', 'success')
        return redirect('/site/nav')

    nav_links = db.get_records("NavLink")
    

    html = '''
    <div class="page-header"><h1>Navigation Links</h1><p>Manage your site navigation menu</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Add Nav Link</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Label</label><input type="text" name="nav_display_label" class="form-control" required></div>
                <div class="form-group"><label class="form-label">URL</label><input type="text" name="nav_target_url" class="form-control" required placeholder="/page or https://..."></div>
                <button type="submit" class="btn btn-primary">Add Link</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Current Nav Links</span></div>
            {% for nav in nav_links %}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:var(--bg-secondary);margin-bottom:5px;border-radius:4px;">
                <span>{{ nav.nav_display_label }} &rarr; {{ nav.nav_target_url }}</span>
                <form method="POST" style="display:inline;">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="nav_display_label" value="{{ nav.nav_display_label }}">
                    <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Remove?\')">Remove</button>
                </form>
            </div>
            {% else %}<p style="color:var(--text-secondary);">No nav links yet.</p>{% endfor %}
        </div>
    </div>'''
    return R(html, nav_links=nav_links, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


@interface_cube.route('/site/social', methods=['GET', 'POST'])
def site_social():
    db.mount()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            platform = request.form.get('social_platform_name', '').strip()
            Submitted_Social_Link_Url = request.form.get('social_target_url', '').strip()
            if platform and Submitted_Social_Link_Url:
                db.add_record("SocialLink", {"social_platform_name": platform, "social_target_url": Submitted_Social_Link_Url})
        elif action == 'delete':
            platform = request.form.get('social_platform_name', '')
            db.delete_record("SocialLink", "social_platform_name", platform)
        db.commit()
        
        flash('Social links updated.', 'success')
        return redirect('/site/social')

    social_links = db.get_records("SocialLink")
    

    html = '''
    <div class="page-header"><h1>Social Media Links</h1><p>Manage your social media profiles</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Add Social Link</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Platform (e.g. Twitter, YouTube)</label><input type="text" name="social_platform_name" class="form-control" required></div>
                <div class="form-group"><label class="form-label">URL</label><input type="url" name="social_target_url" class="form-control" required placeholder="https://"></div>
                <button type="submit" class="btn btn-primary">Add</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Current Social Links</span></div>
            {% for soc in social_links %}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:var(--bg-secondary);margin-bottom:5px;border-radius:4px;">
                <span>{{ soc.social_platform_name }} &rarr; {{ soc.social_target_url }}</span>
                <form method="POST" style="display:inline;">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="social_platform_name" value="{{ soc.social_platform_name }}">
                    <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Remove?\')">Remove</button>
                </form>
            </div>
            {% else %}<p style="color:var(--text-secondary);">No social links yet.</p>{% endfor %}
        </div>
    </div>'''
    return R(html, social_links=social_links, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


@interface_cube.route('/site/ads', methods=['GET', 'POST'])
def manage_ads():
    db.mount()

    if request.method == 'POST':
        action = request.form.get('action', 'add')

        if action == 'add':
            name = request.form.get('ad_name', '').strip()
            Submitted_Ad_Link = request.form.get('ad_target_url', '').strip()
            image = request.form.get('ad_banner_url', '')
            zone = request.form.get('ad_zone', 'header')
            active = request.form.get('ad_active') == 'on'
            if name and image:
                ad_uid = str(uuid.uuid4())
                db.add_record("AdUnit", {
                    "ad_uuid": ad_uid,
                    "ad_name": name,
                    "ad_banner_url": image,
                    "ad_target_url": Submitted_Ad_Link,
                    "ad_zone": zone,
                    "ad_active": active
                })
                db.commit()
                flash(f'Ad "{name}" saved.', 'success')
            else:
                flash('Ad name and image are required.', 'error')

        elif action == 'toggle':
            ad_uid = request.form.get('ad_uuid', '')
            ads = db.get_records("AdUnit")
            ad = next((a for a in ads if a.get('ad_uuid') == ad_uid), None)
            if ad:
                db.update_record("AdUnit", "ad_uuid", ad_uid, {"ad_active": not ad.get('ad_active', True)})
            flash('Ad status toggled.', 'success')

        elif action == 'delete':
            ad_uid = request.form.get('ad_uuid', '')
            db.delete_record("AdUnit", "ad_uuid", ad_uid)
            flash('Ad deleted.', 'success')

        
        return redirect('/site/ads')

    ads = db.get_records("AdUnit")
    assets = get_image_assets()
    

    html = '''
    <div class="page-header"><h1>Ad Manager</h1><p>Manage advertising units for your site</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Create Ad Unit</span></div>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group"><label class="form-label">Internal Name *</label><input type="text" name="ad_name" class="form-control" required></div>
                <div class="form-group"><label class="form-label">Target URL</label><input type="url" name="ad_target_url" class="form-control" placeholder="https://advertiser.com"></div>
                <div class="form-group"><label class="form-label">Image Asset *</label><select name="ad_banner_url" class="form-control" required><option value="">-- Select image --</option>{% for a in assets %}<option value="{{ a }}">{{ a }}</option>{% endfor %}</select></div>
                <div class="form-group"><label class="form-label">Zone</label><select name="ad_zone" class="form-control"><option value="header">Header</option><option value="footer">Footer</option><option value="sidebar">Sidebar</option></select></div>
                <div class="form-group" style="display:flex;align-items:center;gap:10px;"><input type="checkbox" name="ad_active" id="ad_active" checked style="width:auto;"><label for="ad_active" style="margin:0;cursor:pointer;">Active</label></div>
                <button type="submit" class="btn btn-primary">Save Ad Unit</button>
            </form>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Ad Units ({{ ads|length }})</span></div>
            {% if ads %}
            <div class="table-container"><table><thead><tr><th>Name</th><th>Zone</th><th>Status</th><th>Actions</th></tr></thead><tbody>
            {% for ad in ads %}
            <tr>
                <td>
                    {% if ad.ad_banner_url %}<img src="/assets/{{ ad.ad_banner_url }}" style="width:40px;height:30px;object-fit:cover;border-radius:4px;margin-right:8px;vertical-align:middle;">{% endif %}
                    {{ ad.ad_name }}
                </td>
                <td><span class="badge" style="background:var(--bg-secondary);color:var(--text-primary);">{{ ad.ad_zone }}</span></td>
                <td>
                    {% if ad.ad_active %}<span class="badge badge-active">Active</span>{% else %}<span class="badge badge-inactive">Inactive</span>{% endif %}
                </td>
                <td style="display:flex;gap:6px;flex-wrap:wrap;">
                    <form method="POST" style="display:inline;">
                        <input type="hidden" name="action" value="toggle">
                        <input type="hidden" name="ad_uuid" value="{{ ad.ad_uuid }}">
                        <button type="submit" class="btn btn-secondary btn-sm">Toggle</button>
                    </form>
                    <form method="POST" style="display:inline;">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="ad_uuid" value="{{ ad.ad_uuid }}">
                        <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm(\'Delete ad?\')">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
            </tbody></table></div>
            {% else %}<div class="empty-state"><h3>No ad units yet</h3><p>Create your first ad unit using the form.</p></div>{% endif %}
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title">Ad Zones Summary</span></div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;">
            {% set zones = [\'header\', \'footer\', \'sidebar\'] %}
            {% for zone in zones %}
            {% set zone_ads = ads | selectattr(\'ad_zone\', \'equalto\', zone) | list %}
            {% set active_count = zone_ads | selectattr(\'ad_active\') | list | length %}
            <div style="padding:15px;background:var(--bg-secondary);border-radius:8px;text-align:center;">
                <div style="font-weight:700;text-transform:capitalize;margin-bottom:5px;">{{ zone }}</div>
                <div style="font-size:1.5rem;font-weight:800;color:var(--accent);">{{ zone_ads|length }}</div>
                <div style="font-size:0.8rem;color:var(--text-secondary);">{{ active_count }} active</div>
            </div>
            {% endfor %}
        </div>
    </div>'''
    return R(html, ads=ads, assets=assets, breadcrumbs=get_breadcrumbs(request.path), active_section='site')


# =============================================================================
# ROUTES — PUBLISH
# =============================================================================


@interface_cube.route('/publish')
def publish_interface():
    built = os.path.exists(PUBLISH_DIR) and len(os.listdir(PUBLISH_DIR)) > 0
    publisher_url = f"http://localhost:{PUBLISHER_PORT}/"
    html = '''
    <div class="page-header"><h1>Publish</h1><p>Build and publish your site with the standalone Publisher app</p></div>
    <div class="grid grid-2">
        <div class="card">
            <div class="card-header"><span class="card-title">Publisher App</span></div>
            <p style="color:var(--text-secondary);margin-bottom:20px;">
                Opens the standalone Publisher service (its own process, port {{ publisher_port }}) where
                you actually trigger a build, preview it, and push to Cloudflare Pages. If it's not
                currently running, this link will fail to load -- start it from the launcher first.
            </p>
            <a href="{{ publisher_url }}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">&#127760; Open Publisher &#8599;</a>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Export Data</span></div>
            <p style="color:var(--text-secondary);margin-bottom:20px;">Download your BEJSON database and assets for use with the external web publisher.</p>
            <div style="display:flex;flex-direction:column;gap:10px;">
                <a href="/export/db" class="btn btn-primary">&#128190; Download Database</a>
                <a href="/export/assets" class="btn btn-secondary">&#128444; Download Assets ZIP</a>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-header"><span class="card-title">Publish Directory</span></div>
        <p style="color:var(--text-secondary);margin-bottom:10px;">Your web publisher writes output here:</p>
        <code style="display:block;padding:15px;background:var(--bg-secondary);border-radius:6px;word-break:break-all;">{{ publish_dir }}</code>
        {% if built %}<p style="margin-top:10px;color:var(--success);">&#9989; Published site detected</p>{% else %}<p style="margin-top:10px;color:var(--text-secondary);">No published site yet — open the Publisher app above and run a build</p>{% endif %}
    </div>'''
    return R(html, built=built, publish_dir=PUBLISH_DIR, publisher_url=publisher_url, publisher_port=PUBLISHER_PORT,
             breadcrumbs=get_breadcrumbs(request.path), active_section='publish')

