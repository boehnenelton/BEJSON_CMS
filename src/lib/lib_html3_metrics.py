"""
Library:      lib_html3_metrics.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  BECSS-compliant metrics and statistical visualization components.
"""

VERSION = "3.0.0"
SCRIPT_NAME = "lib_html3_metrics.py"
RELATIONAL_ID = "0abd819a-92af-4aba-bcf9-95a5fe3985c9"

import math

def calculate_trend(current, previous):
    """Calculates the percentage trend between two numbers."""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return ((current - previous) / previous) * 100.0

def html_metric_card(title, value, previous_value=None, prefix="", suffix="", inverse_colors=False, color=None):
    """
    BECSS Metric Card with trend indicators.
    """
    trend_html = ""
    if previous_value is not None:
        trend = calculate_trend(value, previous_value)
        is_positive = trend > 0
        is_neutral = trend == 0
        
        if is_neutral:
            trend_color = "var(--text-muted)"
            arrow = "⬌"
        else:
            if inverse_colors:
                trend_color = "var(--primary)" if is_positive else "oklch(70% 0.2 140)" 
            else:
                trend_color = "oklch(70% 0.2 140)" if is_positive else "var(--primary)"
            arrow = "▲" if is_positive else "▼"
            
        trend_html = f"""
        <div class="c-metric-card__trend" style="color: {trend_color};">
            {arrow} {abs(trend):.1f}% <span class="c-metric-card__trend-label">vs previous</span>
        </div>
        """

    border_top_style = f" border-top-color: {color};" if color else ""

    return f"""
    <div class="c-metric-card" style="{border_top_style}">
        <div class="c-metric-card__title">{title}</div>
        <div class="c-metric-card__value">{prefix}{value}{suffix}</div>
        {trend_html}
    </div>
    """

def html_data_distribution(title, data_dict, color="var(--primary)"):
    """
    BECSS Data Distribution bar.
    """
    total = sum(data_dict.values())
    if total == 0: total = 1
    
    bars_html = ""
    legend_html = ""
    
    opacities = [1.0, 0.7, 0.4, 0.2, 0.1]
    
    for i, (label, val) in enumerate(data_dict.items()):
        percentage = (val / total) * 100
        opacity = opacities[i % len(opacities)]
        bg_style = f"background: {color}; opacity: {opacity};"
        
        bars_html += f'<div class="c-data-dist__bar" style="width: {percentage}%; {bg_style}" title="{label}: {val} ({percentage:.1f}%)"></div>'
        
        legend_html += f"""
        <div class="c-data-dist__legend-item">
            <div class="c-data-dist__swatch" style="{bg_style}"></div>
            <span>{label}: <b>{val}</b> ({percentage:.1f}%)</span>
        </div>
        """

    return f"""
    <div class="c-data-dist">
        <div class="c-data-dist__title">{title}</div>
        <div class="c-data-dist__track">
            {bars_html}
        </div>
        <div class="c-data-dist__legend">
            {legend_html}
        </div>
    </div>
    """

def html_summary_statistics(title, data_list, prefix="", suffix="", color=None):
    """
    BECSS Summary Statistics grid.
    """
    if not data_list:
        return f"<div class='c-card'>No data for {title}</div>"
        
    sorted_data = sorted(data_list)
    n = len(sorted_data)
    
    val_min = sorted_data[0]
    val_max = sorted_data[-1]
    mean = sum(sorted_data) / n
    
    if n % 2 == 0:
        median = (sorted_data[n//2 - 1] + sorted_data[n//2]) / 2
    else:
        median = sorted_data[n//2]
        
    stats = [
        ("Count", f"{n}"),
        ("Mean", f"{prefix}{mean:.2f}{suffix}"),
        ("Median", f"{prefix}{median:.2f}{suffix}"),
        ("Min", f"{prefix}{val_min}{suffix}"),
        ("Max", f"{prefix}{val_max}{suffix}")
    ]
    
    stats_html = ""
    val_style = f" style='color: {color};'" if color else ""
    for label, val in stats:
        stats_html += f"""
        <div class="c-summary-stats__item">
            <div class="c-summary-stats__label">{label}</div>
            <div class="c-summary-stats__value"{val_style}>{val}</div>
        </div>
        """
        
    return f"""
    <div class="c-summary-stats">
        <div class="c-summary-stats__header">{title}</div>
        <div class="c-summary-stats__grid">
            {stats_html}
        </div>
    </div>
    """
