"""
Library:      lib_html3_charts.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  BECSS-compliant interactive chart visualization engine with multi-dataset support.
"""

import json
import uuid

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_charts.py"
RELATIONAL_ID = "389b1b4b-fc84-46be-a5e9-e15601fcdc00"

def html_chart(chart_type="bar", title="", labels=None, data=None, color=None, height="300px", datasets=None):
    """
    Generates a responsive Chart.js canvas. Supports multiple datasets.
    datasets: list of {"label": "...", "data": [...], "color": "..."}
    """
    if labels is None: labels = []
    
    chart_id = f"chart_{uuid.uuid4().hex[:8]}"
    # XSS Remediation: Secure Data Bridging (prevent </script> breakout)
    labels_js = json.dumps(labels).replace("</", "<\\/")
    
    # Standardize datasets
    if datasets is None:
        if data is None: data = []
        accent = color or "oklch(65% 0.2 25)"
        datasets = [{"label": title, "data": data, "borderColor": accent, "backgroundColor": accent.replace(')', ' / 0.2)')}]
    else:
        for ds in datasets:
            c = ds.get("color") or "oklch(65% 0.2 25)"
            ds["borderColor"] = c
            ds["backgroundColor"] = c.replace(')', ' / 0.2)')
            ds["borderWidth"] = 2
            ds["tension"] = 0.3
            ds["fill"] = (chart_type == 'line')
            
    # XSS Remediation: Secure Data Bridging (prevent </script> breakout)
    datasets_js = json.dumps(datasets).replace("</", "<\\/")
    
    style = f"height:{height};"
    border_style = f" border-left-color: {color};" if color else ""

    html = f"""
    <div class="c-chart-container" style="{style}{border_style}">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px;">
            {f'<h4 class="c-chart-title" style="margin-bottom:0;">{title}</h4>' if title else '<div></div>'}
            <button class="c-button" onclick="exportChart('{chart_id}', '{title or 'chart'}')" style="padding:4px 10px; font-size:0.6rem;">SAVE PNG</button>
        </div>
        <canvas id="{chart_id}"></canvas>
    </div>
    
    <script>
    (function() {{
        if (typeof window.exportChart !== 'function') {{
            window.exportChart = function(id, name) {{
                var canvas = document.getElementById(id);
                var link = document.createElement('a');
                link.download = name.toLowerCase().replace(/\\s+/g, '_') + '.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            }};
        }}

        function initChart() {{
            var ctx = document.getElementById('{chart_id}').getContext('2d');
            new Chart(ctx, {{
                type: '{chart_type}',
                data: {{
                    labels: {labels_js},
                    datasets: {datasets_js}
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: { 'true' if chart_type in ('pie', 'doughnut') or len(datasets) > 1 else 'false' } }}
                    }},
                    scales: {{
                        y: {{ beginAtZero: true, display: { 'false' if chart_type in ('pie', 'doughnut') else 'true' } }},
                        x: {{ display: { 'false' if chart_type in ('pie', 'doughnut') else 'true' } }}
                    }}
                }}
            }});
        }}

        if (typeof Chart === 'undefined') {{
            if (!window.chartJsLoading) {{
                window.chartJsLoading = true;
                var script = document.createElement('script');
                script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
                script.onload = initChart;
                document.head.appendChild(script);
            }} else {{
                var checkInterval = setInterval(function() {{
                    if (typeof Chart !== 'undefined') {{
                        clearInterval(checkInterval);
                        initChart();
                    }}
                }}, 100);
            }}
        }} else {{
            initChart();
        }}
    }})();
    </script>
    """
    return html

def html_sparkline(data=None, color=None, height="50px"):
    """
    Creates a tiny, minimalist BECSS sparkline.
    """
    if data is None: data = []
    
    chart_id = f"spark_{uuid.uuid4().hex[:8]}"
    # XSS Remediation: Secure Data Bridging (prevent </script> breakout)
    labels_js = json.dumps([""] * len(data)).replace("</", "<\\/")
    data_js = json.dumps(data).replace("</", "<\\/")
    accent = color or "oklch(65% 0.2 25)"
    
    html = f"""
    <div style="height:{height}; width:100%; margin-top: 10px;">
        <canvas id="{chart_id}"></canvas>
    </div>
    <script>
    (function() {{
        function initSpark() {{
            var ctx = document.getElementById('{chart_id}').getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {labels_js},
                    datasets: [{{
                        data: {data_js},
                        borderColor: '{accent}',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.4,
                        fill: true,
                        backgroundColor: '{accent}'.replace(')', ' / 0.1)')
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }},
                    scales: {{ x: {{ display: false }}, y: {{ display: false }} }},
                    layout: {{ padding: 0 }}
                }}
            }});
        }}
        
        if (typeof Chart === 'undefined') {{
            if (!window.chartJsLoading) {{
                window.chartJsLoading = true;
                var script = document.createElement('script');
                script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
                script.onload = initSpark;
                document.head.appendChild(script);
            }} else {{
                var checkInterval = setInterval(function() {{
                    if (typeof Chart !== 'undefined') {{ clearInterval(checkInterval); initSpark(); }}
                }}, 100);
            }}
        }} else {{ initSpark(); }}
    }})();
    </script>
    """
    return html
