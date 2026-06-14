class HTML3_App_Layout:
    """
    Standard layout engine for HTML3 Applications.
    Features: Hamburger Sidebar, Sticky Header, Responsive Container.
    """
    
    @staticmethod
    def get_template():
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="css/becss-core.css">
    <link rel="stylesheet" href="css/becss-components.css">
    <style>
        :root {{ --accent: #DE2626; --bg: #050505; --surface: #0a0a0a; --border: #222; }}
        body {{ background: var(--bg); color: #fff; font-family: 'Inter', sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}
        
        header {{ 
            height: 60px; background: var(--surface); border-bottom: 1px solid var(--border); 
            display: flex; align-items: center; padding: 0 24px; gap: 20px; flex-shrink: 0;
            z-index: 100;
        }}
        .hamburger {{ cursor: pointer; display: flex; flex-direction: column; gap: 5px; width: 24px; }}
        .hamburger span {{ display: block; height: 2px; background: #fff; width: 100%; transition: 0.3s; }}
        .header-logo {{ font-weight: 800; letter-spacing: 2px; color: var(--accent); text-transform: uppercase; font-size: 1rem; }}

        .app-shell {{ display: flex; flex: 1; overflow: hidden; position: relative; }}
        
        /* Sidebar */
        .app-sidebar {{ 
            width: 280px; background: var(--surface); border-right: 1px solid var(--border); 
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex; flex-direction: column; z-index: 90;
        }}
        .app-sidebar.collapsed {{ transform: translateX(-280px); margin-right: -280px; }}
        
        /* Mobile Overlay */
        .sidebar-overlay {{ 
            display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 80; 
        }}
        .sidebar-overlay.active {{ display: block; }}

        /* Main Content */
        .app-main {{ flex: 1; overflow-y: auto; padding: 2rem; position: relative; scrollbar-width: thin; scrollbar-color: var(--accent) #111; }}
        
        @media (max-width: 768px) {{
            .app-sidebar {{ position: fixed; height: calc(100% - 60px); top: 60px; transform: translateX(-100%); }}
            .app-sidebar.active {{ transform: translateX(0); }}
            .app-sidebar.collapsed {{ margin-right: 0; }}
        }}

        .breadcrumb-strip {{ font-size: 0.7rem; color: #555; text-transform: uppercase; margin-bottom: 1.5rem; letter-spacing: 1px; }}
        .breadcrumb-strip span {{ color: var(--accent); }}
    </style>
</head>
<body>
    <header>
        <div class="hamburger" id="navToggle"><span></span><span></span><span></span></div>
        <div class="header-logo">BEJSON ECOSYSTEM</div>
        <div style="flex:1"></div>
        <div style="font-size:0.6rem; color:#444; font-family:monospace;">MFDB v1.31 | HTML3 v1.2</div>
    </header>

    <div class="sidebar-overlay" id="overlay"></div>

    <div class="app-shell">
        <aside class="app-sidebar" id="sidebar">
            {sidebar_content}
        </aside>

        <main class="app-main">
            <div class="breadcrumb-strip">REGISTRY / <span>{entity_name}</span></div>
            {body_content}
        </main>
    </div>

    <script>
        const btn = document.getElementById('navToggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('overlay');

        function toggle() {{
            const isMobile = window.innerWidth <= 768;
            if (isMobile) {{
                sidebar.classList.toggle('active');
                overlay.classList.toggle('active');
            }} else {{
                sidebar.classList.toggle('collapsed');
            }}
        }}

        btn.addEventListener('click', toggle);
        overlay.addEventListener('click', toggle);

        // Auto-highlight active link
        const currentPath = window.location.pathname.split('/').pop() || 'index.html';
        document.querySelectorAll('.c-html3-list__nav-item').forEach(link => {{
            if (link.getAttribute('href') === currentPath) {{
                link.classList.add('is-active');
            }}
        }});
    </script>
</body>
</html>"""
