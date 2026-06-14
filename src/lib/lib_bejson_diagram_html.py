"""
Library:      lib_bejson_diagram_html.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  BECSS-compliant visualizer for BEJSON relational structures.
"""

import json
import os
from datetime import datetime

BECSS_DIAGRAM_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}} · BEJSON 104db</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Roboto+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  @layer reset, base, layout, components, interactive;
  
  @layer reset {{
      *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
      html, body {{ width: 100%; height: 100%; overflow: hidden; }}
  }}

  @layer base {{
      :root {{
          --primary: {{ACCENT_COLOR}};
          --bg-page: {{BG_COLOR}};
          --text-main: oklch(95% 0 0);
          --text-muted: oklch(60% 0 0);
          --font-sans: 'Inter', sans-serif;
          --font-mono: 'Roboto Mono', monospace;
      }}
      body {{ background-color: var(--bg-page); color: var(--text-main); font-family: var(--font-mono); }}
  }}

  @layer layout {{
      .c-diagram-page {{ display: flex; flex-direction: column; height: 100dvh; }}
      .c-diagram-header {{
          padding: 16px 24px; background: rgba(0,0,0,0.4);
          border-bottom: 1px solid var(--primary); backdrop-filter: blur(10px);
      }}
      .c-diagram-header h1 {{ font-family: 'Orbitron'; font-size: 1.25rem; letter-spacing: 2px; color: var(--primary); }}
      .c-diagram-header p {{ font-size: 0.75rem; color: var(--text-muted); margin-top: 4px; }}
      
      .c-diagram-wrapper {{ flex: 1; position: relative; overflow: hidden; }}
      #diagram-svg {{ width: 100%; height: 100%; }}
      
      .c-diagram-footer {{
          padding: 8px 24px; background: rgba(0,0,0,0.4);
          font-size: 0.65rem; color: var(--text-muted); display: flex; gap: 24px;
          border-top: 1px solid oklch(20% 0 0);
      }}
  }}

  @layer interactive {{
      .conn-path {{ stroke-dasharray: 5 4; animation: flow 2s linear infinite; }}
      @keyframes flow {{ from {{ stroke-dashoffset: 20; }} to {{ stroke-dashoffset: 0; }} }}
  }}
</style>
</head>
<body>
<div class="c-diagram-page">
  <header class="c-diagram-header">
      <span class="u-font-mono u-fs-tiny" style="color:var(--primary); opacity:0.6;">BEJSON · 104db · {{MODE}} VIEW</span>
      <h1>{{TITLE}}</h1>
      <p>{{SUBTITLE}}</p>
  </header>

  <div class="c-diagram-wrapper">
    <svg id="diagram-svg" viewBox="0 0 1440 720" preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id="dots" x="0" y="0" width="32" height="32" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="rgba(255,255,255,0.05)"/>
        </pattern>
        <filter id="glow-primary" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="5" result="blur"/>
          <feFlood flood-color="{{ACCENT_COLOR}}" flood-opacity="0.5" result="c"/>
          <feComposite in="c" in2="blur" operator="in" result="shadow"/>
          <feMerge><feMergeNode in="shadow"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <rect width="100%" height="100%" fill="url(#dots)"/>
      <g id="connectors-layer"></g>
      <g id="nodes-layer"></g>
    </svg>
  </div>

  <footer class="c-diagram-footer">
    <span>FORMAT: BEJSON 104db</span>
    <span>ENGINE: HTML3 V3.0</span>
    <span>TIMESTAMP: {{TIMESTAMP}}</span>
  </footer>
</div>

<script id="bejson-data" type="application/json">
{{DIAGRAM_DATA}}
</script>

<script>
(function() {{
  var THEME = {{ accent: "{{ACCENT_COLOR}}", bg: "{{BG_COLOR}}" }};

  function render() {{
    var dataEl = document.getElementById("bejson-data");
    if (!dataEl) return;
    var bejson = JSON.parse(dataEl.textContent);
    var fields = bejson.Fields;
    var fi = {{}};
    fields.forEach(function(f, i) {{ fi[f.name] = i; }});

    var shapes = bejson.Values
      .filter(function(r) {{ return r[fi["Record_Type_Parent"]] === "Shape"; }})
      .map(function(r) {{
        return {{
          id: r[fi["id_Shape"]] || r[fi["s_id"]],
          label: r[fi["label_Shape"]] || r[fi["s_label"]],
          text: r[fi["text_Shape"]] || r[fi["s_sublabel"]] || "",
          x: r[fi["x_Shape"]] || r[fi["s_x"]] || 0,
          y: r[fi["y_Shape"]] || r[fi["s_y"]] || 0,
          w: r[fi["w_Shape"]] || 150,
          h: r[fi["h_Shape"]] || 60,
          color: r[fi["color_Shape"]] || r[fi["s_color"]] || THEME.accent
        }};
      }});

    var connectors = bejson.Values
      .filter(function(r) {{ return r[fi["Record_Type_Parent"]] === "Connector"; }})
      .map(function(r) {{
        return {{
          from: r[fi["from_Connector"]] || r[fi["c_from"]],
          to: r[fi["to_Connector"]] || r[fi["c_to"]],
          label: r[fi["label_Connector"]] || r[fi["c_label"]] || ""
        }};
      }});

    var shapeMap = {{}};
    shapes.forEach(function(s) {{ shapeMap[s.id] = s; }});
    var connLayer = document.getElementById("connectors-layer");
    var nodeLayer = document.getElementById("nodes-layer");

    connectors.forEach(function(conn) {{
      var from = shapeMap[conn.from];
      var to = shapeMap[conn.to];
      if (!from || !to) return;
      
      var d = "M " + (from.x + from.w) + " " + (from.y + from.h/2) + " C " + (from.x + from.w + 50) + " " + (from.y + from.h/2) + ", " + (to.x - 50) + " " + (to.y + to.h/2) + ", " + to.x + " " + (to.y + to.h/2);
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", from.color);
      path.setAttribute("class", "conn-path");
      connLayer.appendChild(path);
    }});

    shapes.forEach(function(s) {{
      var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("transform", "translate(" + s.x + "," + s.y + ")");
      g.innerHTML = '<rect width="' + s.w + '" height="' + s.h + '" rx="4" fill="rgba(0,0,0,0.6)" stroke="' + s.color + '" stroke-width="2" filter="url(#glow-primary)" />' +
                     '<text x="' + (s.w/2) + '" y="' + (s.h/2 + 5) + '" text-anchor="middle" fill="' + s.color + '" font-family="Orbitron" font-size="12" font-weight="700">' + s.label + '</text>';
      nodeLayer.appendChild(g);
    }});
  }}
  document.addEventListener("DOMContentLoaded", render);
}})();
</script>
</body>
</html>
"""

def export_high_fidelity_diagram(json_data, output_path, title="System Diagram"):
    """
    Exports a BEJSON 104db diagram as a high-fidelity BECSS HTML file.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = BECSS_DIAGRAM_TEMPLATE.replace("{{TITLE}}", title) \
                                 .replace("{{SUBTITLE}}", "Relational logic map generated via BEJSON 104db") \
                                 .replace("{{MODE}}", "HIGH-FIDELITY") \
                                 .replace("{{ACCENT_COLOR}}", "oklch(65% 0.2 25)") \
                                 .replace("{{BG_COLOR}}", "oklch(5% 0 0)") \
                                 .replace("{{TIMESTAMP}}", timestamp) \
                                 .replace("{{DIAGRAM_DATA}}", json.dumps(json_data, indent=2))
                             
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return True
