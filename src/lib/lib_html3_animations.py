"""
Library:      lib_html3_animations.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  BECSS-compliant CSS animations and cinematic reveals.
"""

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_animations.py"
RELATIONAL_ID = "f06a6dc2-cd93-405f-8005-0a65886a665c"
ES5_SAFE = True

def css_animation_keyframes():
    """Returns global keyframes for system animations."""
    return """
@layer interactive {
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
    @keyframes scanMove { 0% { top: 20%; } 100% { top: 80%; } }
    @keyframes expandBrackets {
        0% { gap: 0; opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
        15% { opacity: 1; transform: translate(-50%, -50%) scale(1.1); }
        30% { gap: clamp(10rem, 20vw, 22rem); transform: translate(-50%, -50%) scale(1); }
        85% { gap: clamp(10rem, 20vw, 22rem); opacity: 1; transform: translate(-50%, -50%) scale(1); }
        100% { gap: clamp(15rem, 30vw, 30rem); opacity: 0; transform: translate(-50%, -50%) scale(1.2); }
    }
    @keyframes glitch-anim-1 {
        0% { clip-path: polygon(0 10%, 100% 10%, 100% 30%, 0 30%); transform: translate(0); }
        20% { clip-path: polygon(0 50%, 100% 50%, 100% 60%, 0 60%); transform: translate(-5px, 2px); }
        40% { clip-path: polygon(0 15%, 100% 15%, 100% 25%, 0 25%); transform: translate(5px, -2px); }
        100% { clip-path: polygon(0 40%, 100% 40%, 100% 50%, 0 50%); transform: translate(0); }
    }
    @keyframes flashBang {
        0% { opacity: 0; }
        10% { opacity: 1; background-color: #ffffff; }
        20% { background-color: var(--primary); }
        100% { opacity: 0; }
    }
    @keyframes cinematicZoom {
        0% { opacity: 1; transform: scale(1.1); filter: blur(4px); }
        15% { opacity: 1; transform: scale(1); filter: blur(0); }
        80% { opacity: 1; transform: scale(0.98); filter: blur(0); }
        100% { opacity: 0; transform: scale(0.95); filter: blur(10px); }
    }
}
"""

def html_intro_terminal(lines, impact_callback=""):
    """
    BECSS Terminal typewriter boot sequence.
    """
    import json
    # XSS Remediation: Secure Data Bridging (prevent </script> breakout)
    lines_json = json.dumps(lines).replace("</", "<\\/")
    callback_js = f"if (typeof window['{impact_callback}'] === 'function') window['{impact_callback}']();" if impact_callback else ""
    
    return f"""
    <div id="terminal-boot" class="c-terminal-boot"></div>
    <script>
    (function() {{
        var lines = {lines_json};
        var el = document.getElementById('terminal-boot');
        var delay = 0;
        for (var i = 0; i < lines.length; i++) {{
            (function(text, index) {{
                delay += 300 - (index * 20);
                setTimeout(function() {{
                    var div = document.createElement('div');
                    div.className = 'c-terminal-line';
                    // XSS Remediation: Use textContent instead of innerHTML
                    div.textContent = text;
                    el.appendChild(div);
                    if (index === lines.length - 1) {{
                        setTimeout(function() {{ 
                            el.style.opacity = '0';
                            el.style.transition = 'opacity 0.5s';
                            {callback_js}
                        }}, 600);
                    }}
                }}, delay);
            }})(lines[i], i);
        }}
    }})();
    </script>
    """

def html_glitch_reveal(text, subtitle=""):
    """BECSS Glitch cinematic reveal."""
    import html as html_mod
    safe_text = html_mod.escape(text)
    safe_subtitle = html_mod.escape(subtitle)
    return f"""
    <div class="c-glitch-wrapper">
        <h1 class="c-glitch-text" data-text="{safe_text}">{safe_text}</h1>
        <p class="c-glitch-subtitle">{safe_subtitle}</p>
    </div>
    """
