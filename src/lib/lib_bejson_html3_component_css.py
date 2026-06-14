"""
Library:      lib_bejson_html3_component_css.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.0.1 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-05-29
Description:  Central registry for BECSS component styles.
              Organized into the @layer components layer.
"""

VERSION = "3.0.1"
SCRIPT_NAME = "lib_bejson_html3_component_css.py"
RELATIONAL_ID = "c7d6b5a4-1f8a-4e8a-9d6c-5f4b5a6c7d8f"

COMPONENT_CSS = """
@layer components {{
    /* Stats Bar */
    .c-stats-bar {{
        display: flex; gap: 24px; padding: 24px;
        background: var(--bg-surface); margin-bottom: 24px;
        border-left: 4px solid var(--primary);
    }}
    .c-stats-bar__item {{ flex: 1; }}
    .c-stats-bar__label {{
        font-size: 0.65rem; color: var(--text-muted);
        font-family: var(--font-mono); text-transform: uppercase;
    }}
    .c-stats-bar__value {{
        font-size: 1.5rem; font-weight: 800; color: var(--primary);
    }}

    /* Cards */
    .c-card {{
        background: var(--bg-page); border: 1px solid var(--border);
        padding: 24px; margin-bottom: 24px; border-radius: var(--radius);
        box-shadow: var(--shadow-sm);
    }}
    .c-card__title {{
        font-size: 1.1rem; color: var(--primary);
        text-transform: uppercase; letter-spacing: 0.05em;
        margin-bottom: 12px; font-weight: 800;
    }}
    .c-card__body {{ font-size: 0.95rem; color: var(--text-main); }}
    
    .c-card--brutal {{
        border: 4px solid var(--border); border-radius: 0;
        box-shadow: 8px 8px 0px var(--border);
    }}

    /* Badges */
    .c-badge {{
        font-family: var(--font-mono); font-size: 0.65rem;
        font-weight: 800; padding: 2px 8px;
        background: var(--bg-alt); border-radius: 2px;
        text-transform: uppercase;
    }}
    .c-badge--success {{ color: oklch(70% 0.2 140); }}
    .c-badge--fail {{ color: oklch(60% 0.2 25); }}

    /* Code Box */
    .c-code-box {{
        background: #000; border-left: 4px solid var(--primary);
        margin: 24px 0; position: relative;
    }}
    .c-code-box__header {{
        display: flex; justify-content: space-between; align-items: center;
        padding: 8px 16px; background: rgba(255,255,255,0.05);
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }}
    .c-code-box__title {{
        font-family: var(--font-mono); font-size: 0.7rem;
        color: var(--primary); font-weight: 800; text-transform: uppercase;
    }}
    .c-code-box__copy {{
        background: var(--primary); color: white; border: none;
        padding: 4px 12px; font-size: 0.65rem; font-weight: 800;
        cursor: pointer; text-transform: uppercase;
    }}
    .c-code-box__pre {{ margin: 0; padding: 20px; color: oklch(85% 0.2 140); overflow-x: auto; }}
    .c-code-box__code {{ font-family: var(--font-mono); font-size: 0.85rem; }}

    /* Tables */
    .c-table-container {{ 
        width: 100%; 
        overflow-x: auto; 
        margin-bottom: 24px; 
        border: 1px solid var(--border);
        border-radius: var(--radius);
    }}
    .c-table {{
        width: 100%; border-collapse: collapse; font-size: 0.9rem;
        min-width: 600px;
    }}
    .c-table th {{
        background: var(--bg-alt); padding: 12px; text-align: left;
        font-weight: 800; text-transform: uppercase; font-size: 0.75rem;
        border-bottom: 2px solid var(--border); color: var(--text-muted);
        position: sticky; top: 0; z-index: 10;
    }}
    .c-table td {{ 
        padding: 12px; 
        border-bottom: 1px solid var(--border-muted); 
        word-break: break-word;
        overflow-wrap: anywhere;
    }}
    .c-table tr:hover {{ background: var(--bg-alt); }}

    /* Subtabs */
    .c-subtabs {{ 
        display: flex; 
        gap: 0; 
        margin-bottom: 12px; 
        border: 1px solid var(--border); 
        width: 100%; 
        overflow-x: auto; 
        scrollbar-width: none; 
        -ms-overflow-style: none;
    }}
    .c-subtabs::-webkit-scrollbar {{ display: none; }}
    .c-subtabs__btn {{
        border: none; padding: 12px 24px; font-weight: 800; font-size: 0.8rem;
        cursor: pointer; font-family: var(--font-sans); background: transparent;
        color: var(--text-muted); transition: var(--transition);
        white-space: nowrap;
        border-right: 1px solid var(--border);
    }}
    .c-subtabs__btn:last-child {{ border-right: none; }}
    .c-subtabs__btn:hover {{ background: var(--bg-alt); color: var(--primary); }}
    .c-subtabs__btn--active {{ background: var(--primary) !important; color: white !important; }}

    /* Typography & Body Text */
    .c-card__body {{ 
        font-size: 0.95rem; 
        color: var(--text-main); 
        line-height: 1.7;
        max-width: 100%;
        overflow-wrap: anywhere;
        word-break: break-word;
    }}
    .c-card__body p {{ margin-bottom: 1.25rem; }}
    .c-card__body ul, .c-card__body ol {{ margin-bottom: 1.25rem; padding-left: 1.5rem; }}
    .c-card__body li {{ margin-bottom: 0.6rem; }}
    .c-card__body h1, .c-card__body h2, .c-card__body h3 {{ 
        color: var(--primary); 
        margin-top: 1.5rem; 
        margin-bottom: 0.75rem; 
        text-transform: uppercase;
        font-weight: 800;
        letter-spacing: 0.05em;
    }}

    .c-dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .c-dl__item {{ margin-bottom: 12px; border-left: 2px solid var(--border); padding-left: 12px; }}
    .c-dl__term {{ font-size: 0.65rem; font-family: var(--font-mono); color: var(--text-muted); text-transform: uppercase; }}
    .c-dl__desc {{ font-weight: 700; font-size: 1rem; color: var(--text-main); }}
    /* Card Grid */
    .c-card-grid {{
        display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 24px;
    }}

    /* Widgets */
    .c-widget {{
        background: var(--bg-page); border: 1px solid var(--border);
        display: flex; flex-direction: column; overflow: hidden;
        border-radius: var(--radius); box-shadow: var(--shadow-sm);
    }}
    .c-widget__header {{
        padding: 8px 16px; background: var(--bg-alt);
        border-bottom: 1px solid var(--border); display: flex;
        justify-content: space-between; font-family: var(--font-mono);
        font-size: 0.7rem; font-weight: 700;
    }}
    .c-widget__body {{ flex: 1; padding: 16px; overflow: auto; }}

    /* Gallery */
    .c-gallery-grid {{
        display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 16px;
    }}
    .c-gallery-item {{
        background: var(--bg-surface); border: 1px solid var(--border);
        padding: 8px; border-radius: var(--radius); transition: var(--transition);
    }}
    .c-gallery-item:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-sm); }}
    .c-gallery-item img {{ width: 100%; height: 150px; object-fit: cover; border-radius: 4px; display: block; }}
    .c-gallery-item__label {{
        margin-top: 8px; font-size: 0.75rem; color: var(--text-muted);
        text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }}

    /* Video Grid */
    .c-video-grid {{
        display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 24px;
    }}
    .c-video-card {{
        background: var(--bg-page); border: 1px solid var(--border);
        border-radius: var(--radius); overflow: hidden;
    }}
    .c-video-card__header {{
        padding: 10px 16px; background: var(--bg-alt);
        font-weight: 700; font-size: 0.85rem; border-bottom: 1px solid var(--border);
    }}
    .c-video-card__embed {{ position: relative; padding-bottom: 56.25%; height: 0; }}
    .c-video-card__embed iframe {{
        position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;
    }}

    /* Info Box */
    .c-info-box {{
        background: var(--bg-page); border: 1px solid var(--border);
        padding: 24px; border-radius: var(--radius); position: relative;
    }}
    .c-info-box__title {{
        font-size: 1rem; font-weight: 800; color: var(--primary);
        margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
    }}
    .c-info-box__dot {{ width: 8px; height: 8px; background: var(--primary); border-radius: 50%; }}
    .c-info-box__content {{ font-size: 0.95rem; color: var(--text-main); line-height: 1.5; }}
    .c-info-box__link {{
        display: inline-block; margin-top: 16px; font-size: 0.85rem;
        font-weight: 700; color: var(--primary); text-decoration: none;
    }}

    /* Carousel */
    .c-carousel {{ position: relative; overflow: hidden; width: 100%; border: 1px solid var(--border); background: var(--bg-surface); }}
    .c-carousel__track {{ display: flex; transition: transform 0.3s ease; }}
    .c-carousel__slide {{ min-width: 100%; padding: 20px; box-sizing: border-box; }}
    .c-carousel__controls {{ display: flex; justify-content: space-between; padding: 10px; background: rgba(0,0,0,0.05); }}
    .c-carousel__btn {{
        background: transparent; border: 1px solid var(--primary);
        color: var(--primary); font-family: var(--font-mono);
        padding: 5px 12px; cursor: pointer; font-weight: 700; font-size: 0.75rem;
    }}
    .c-carousel__btn:hover {{ background: var(--primary); color: white; }}

    /* Dialog */
    .c-dialog-mask {{
        display: none; position: fixed; z-index: 4000; left: 0; top: 0; width: 100%; height: 100%;
        background-color: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
    }}
    .c-dialog {{
        position: relative; background-color: var(--bg-page); margin: 10% auto; padding: 0;
        border: 2px solid var(--primary); width: 80%; max-width: 600px;
        box-shadow: 10px 10px 0px rgba(0,0,0,0.1); border-radius: var(--radius);
    }}
    .c-dialog__header {{
        padding: 12px 20px; background: var(--bg-alt); border-bottom: 1px solid var(--border);
        display: flex; justify-content: space-between; align-items: center;
    }}
    .c-dialog__title {{ font-family: var(--font-mono); font-weight: 800; font-size: 0.85rem; text-transform: uppercase; color: var(--primary); }}
    .c-dialog__close {{ background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-muted); }}
    .c-dialog__body {{ padding: 24px; font-size: 0.95rem; color: var(--text-main); line-height: 1.6; }}
    .c-dialog__footer {{
        padding: 12px 20px; background: var(--bg-alt); border-top: 1px solid var(--border);
        display: flex; justify-content: flex-end; gap: 12px;
    }}

    /* Lightbox */
    .c-lightbox {{ display: none; position: fixed; z-index: 5000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.95); }}
    .c-lightbox__content {{ margin: auto; display: block; width: 85%; max-width: 1200px; max-height: 85%; margin-top: 5%; object-fit: contain; }}
    .c-lightbox__caption {{ margin: auto; display: block; width: 80%; text-align: center; color: white; padding: 20px 0; font-family: var(--font-mono); font-size: 0.9rem; }}
    .c-lightbox__close {{ position: absolute; top: 20px; right: 30px; color: white; font-size: 40px; font-weight: bold; cursor: pointer; }}
    /* Table Controls & Pagination */
    .c-table-controls {{ display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
    .c-table-controls__label {{ font-family: var(--font-mono); font-size: 0.7rem; font-weight: 800; color: var(--primary); text-transform: uppercase; }}
    .c-table-controls__select, .c-table-controls__input {{ 
        font-family: var(--font-sans); font-size: 0.8rem; padding: 4px 12px; 
        background-color: var(--bg-page); color: var(--text-main); border: 1px solid var(--border); 
        border-radius: var(--radius); outline: none; cursor: pointer;
    }}
    .c-table-controls__select:focus, .c-table-controls__input:focus {{ border-color: var(--primary); }}
    .c-table-controls__count {{ margin-left: auto; font-family: var(--font-mono); color: var(--text-muted); font-size: 0.7rem; font-weight: 700; }}

    .c-pagination {{ display: flex; align-items: center; gap: 8px; margin-top: 16px; }}
    .c-pagination__btn {{
        background: var(--bg-alt); border: 1px solid var(--border);
        padding: 4px 12px; border-radius: var(--radius); cursor: pointer;
        font-family: var(--font-mono); font-size: 0.75rem; font-weight: 700;
        transition: var(--transition);
    }}
    .c-pagination__btn:hover:not(:disabled) {{ background: var(--primary); color: white; border-color: var(--primary); }}
    .c-pagination__btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
    .c-pagination__info {{ font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted); }}

    /* Indicators (Used in Table Cells) */
    .c-indicator {{ font-weight: 800; text-transform: uppercase; }}
    .c-indicator--success {{ color: oklch(70% 0.2 140); }}
    .c-indicator--fail {{ color: oklch(60% 0.2 25); }}
    .c-null-val {{ color: var(--text-muted); font-style: italic; opacity: 0.7; }}
    /* Animations */
    .c-terminal-boot {{ font-family: var(--font-mono); color: var(--text-muted); padding: 24px; }}
    .c-terminal-line {{ margin-bottom: 8px; font-size: 0.85rem; }}

    .c-glitch-wrapper {{ position: relative; text-align: center; }}
    .c-glitch-text {{
        font-size: clamp(3rem, 10vw, 7rem); font-weight: 900;
        letter-spacing: 0.5rem; color: var(--text-main); position: relative;
    }}
    .c-glitch-text::before, .c-glitch-text::after {{
        content: attr(data-text); position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: transparent;
    }}
    .c-glitch-text::before {{ left: 4px; text-shadow: -3px 0 var(--primary); clip-path: polygon(0 0, 100% 0, 100% 35%, 0 35%); animation: glitch-anim-1 0.4s infinite; }}
    .c-glitch-text::after {{ left: -4px; text-shadow: 3px 0 var(--text-main); clip-path: polygon(0 65%, 100% 65%, 100% 100%, 0 100%); animation: glitch-anim-1 0.3s infinite reverse; }}
    .c-glitch-subtitle {{ color: var(--primary); letter-spacing: 0.3rem; margin-top: 1rem; font-family: var(--font-mono); font-weight: 700; text-transform: uppercase; }}
    /* Metrics */
    .c-metric-card {{
        background: var(--bg-surface); border: 1px solid var(--border);
        padding: 24px; border-top: 4px solid var(--primary);
        transition: var(--transition); border-radius: var(--radius);
        box-shadow: var(--shadow-sm);
    }}
    .c-metric-card__title {{
        font-family: var(--font-mono); font-size: 0.7rem;
        color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;
        font-weight: 700;
    }}
    .c-metric-card__value {{ font-size: 2rem; font-weight: 800; color: var(--text-main); }}
    .c-metric-card__trend {{
        font-family: var(--font-mono); font-size: 0.75rem;
        margin-top: 12px; font-weight: 800; display: flex; align-items: center; gap: 4px;
    }}
    .c-metric-card__trend-label {{ color: var(--text-muted); font-weight: 400; font-size: 0.7rem; }}

    .c-data-dist {{
        margin-bottom: 24px; background: var(--bg-surface);
        border: 1px solid var(--border); padding: 20px;
        border-radius: var(--radius);
    }}
    .c-data-dist__title {{
        font-family: var(--font-mono); font-size: 0.75rem;
        color: var(--text-muted); text-transform: uppercase;
        margin-bottom: 16px; font-weight: 800;
    }}
    .c-data-dist__track {{
        width: 100%; height: 16px; background: var(--border-muted);
        overflow: hidden; margin-bottom: 20px; display: flex;
        border-radius: 8px;
    }}
    .c-data-dist__bar {{ height: 100%; transition: width 0.3s ease; }}
    .c-data-dist__legend {{ display: flex; flex-wrap: wrap; gap: 20px; }}
    .c-data-dist__legend-item {{ display: flex; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-main); }}
    .c-data-dist__swatch {{ width: 12px; height: 12px; border-radius: 2px; }}

    .c-summary-stats {{
        margin-bottom: 24px; background: var(--bg-surface);
        border: 1px solid var(--border); border-radius: var(--radius);
        overflow: hidden; display: flex; flex-direction: column;
    }}
    .c-summary-stats__header {{
        padding: 12px 20px; border-bottom: 1px solid var(--border);
        font-family: var(--font-mono); font-size: 0.75rem; font-weight: 800;
        color: var(--text-main); text-transform: uppercase; background: var(--bg-alt);
    }}
    .c-summary-stats__grid {{ display: flex; flex-wrap: wrap; background: var(--bg-page); }}
    .c-summary-stats__item {{
        flex: 1; min-width: 100px; text-align: center;
        border-right: 1px solid var(--border-muted); padding: 16px;
    }}
    .c-summary-stats__item:last-child {{ border-right: none; }}
    .c-summary-stats__label {{
        font-family: var(--font-mono); font-size: 0.65rem;
        color: var(--text-muted); text-transform: uppercase;
    }}
    .c-summary-stats__value {{ font-size: 1.1rem; font-weight: 800; color: var(--primary); margin-top: 4px; }}
    /* Feed & Grid */
    .c-feed {{ display: flex; flex-direction: column; gap: 32px; }}
    .c-feed-item {{
        padding-bottom: 32px; border-bottom: 1px solid var(--border-muted);
    }}
    .c-feed-item:last-child {{ border-bottom: none; }}
    .c-feed-item__title {{ font-size: 1.5rem; margin-bottom: 8px; font-weight: 800; }}
    .c-feed-item__title a {{ color: var(--text-main); }}
    .c-feed-item__title a:hover {{ color: var(--primary); text-decoration: none; }}
    .c-feed-item__meta {{ font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted); margin-bottom: 16px; }}
    .c-feed-item__body {{ font-size: 1.1rem; line-height: 1.6; color: var(--text-main); }}
    .c-feed-item__tags {{ display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }}
    .c-feed-tag {{
        font-family: var(--font-mono); font-size: 0.65rem; background: var(--bg-alt);
        padding: 4px 10px; border-radius: 100px; color: var(--text-muted);
        font-weight: 700; text-transform: uppercase;
    }}
    /* Bento Grid */
    .c-bento-grid {{
        display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        grid-auto-rows: 200px; gap: 16px; padding: 16px; width: 100%;
    }}
    .c-bento-item {{
        background: var(--bg-page); border: 1px solid var(--border);
        padding: 24px; display: flex; flex-direction: column;
        transition: var(--transition); border-radius: var(--radius);
        box-shadow: var(--shadow-sm);
    }}
    .c-bento-item:hover {{ transform: translateY(-4px); box-shadow: 0 8px 16px rgba(0,0,0,0.1); }}
    .c-bento-item--w2 {{ grid-column: span 2; }}
    .c-bento-item--w3 {{ grid-column: span 2; grid-row: span 2; }}
    .c-bento-item__label {{
        font-family: var(--font-mono); font-size: 0.7rem; color: var(--primary);
        font-weight: 800; text-transform: uppercase; margin-bottom: 8px;
    }}
    .c-bento-item__value {{ font-size: 1.5rem; font-weight: 800; color: var(--text-main); }}
    .c-bento-item--w3 .c-bento-item__value {{ font-size: 3rem; }}
    /* Forms & Buttons */
    .c-button {{
        background: var(--primary); color: white; border: none;
        padding: 10px 24px; font-family: var(--font-mono); font-weight: 800;
        font-size: 0.75rem; cursor: pointer; border-radius: var(--radius);
        text-transform: uppercase; transition: var(--transition);
        display: inline-block; text-align: center;
    }}
    .c-button:hover {{ opacity: 0.9; transform: translateY(-1px); }}
    .c-button:active {{ transform: translateY(0); }}

    .c-input {{
        background: var(--bg-page); border: 1px solid var(--border);
        color: var(--text-main); padding: 8px 12px; font-family: var(--font-sans);
        font-size: 0.9rem; border-radius: var(--radius); outline: none;
        width: 100%; transition: border-color 0.2s;
    }}
    .c-input:focus {{ border-color: var(--primary); }}
/* Utilities */
.u-mb-8 {{ margin-bottom: 8px; }}
.u-font-mono {{ font-family: var(--font-mono); }}
.u-fs-tiny {{ font-size: 0.65rem; }}
.u-fs-small {{ font-size: 0.75rem; }}

/* Dark Mode Utility */
.u-dark {{
    --bg-page: #0F0F0F;
    --bg-alt: #1A1A1A;
    --bg-surface: #1A1A1A;
    --text-main: #F2F2F2;
    --text-muted: #9CA3AF;
    --border: #262626;
    --border-muted: #1F1F1F;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.5);
}}
.u-dark body {{ background-color: var(--bg-page); color: var(--text-main); }}
.u-dark .c-header, .u-dark .c-sidebar, .u-dark .c-footer {{ background-color: var(--bg-page); border-color: var(--border); }}
.u-dark .c-card, .u-dark .c-widget, .u-dark .c-table {{ background-color: var(--bg-alt); border-color: var(--border); }}
.u-dark .c-table th {{ background-color: var(--bg-page); color: var(--text-muted); }}
.u-dark .c-input {{ background-color: var(--bg-page); color: var(--text-main); border-color: var(--border); }}
.u-dark .c-subtabs {{ border-color: var(--border); }}
.u-dark .c-subtabs__btn {{ color: var(--text-muted); }}
.u-dark .c-sidebar__link {{ color: var(--text-main); }}
.u-dark .c-sidebar__link:hover {{ background-color: var(--bg-alt); }}
}}

    /* Toasts */
    .c-toast-container {{
        position: fixed; top: 24px; right: 24px; z-index: 9999;
        display: flex; flex-direction: column; gap: 12px;
    }}
    .c-toast {{
        background: var(--bg-page); border: 1px solid var(--border);
        padding: 16px 24px; border-radius: var(--radius);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        font-family: var(--font-sans); font-size: 0.85rem; font-weight: 600;
        display: flex; align-items: center; gap: 12px; min-width: 280px;
        animation: toast-in 0.3s ease-out forwards;
        border-left: 4px solid var(--primary);
    }}
    @keyframes toast-in {{ from {{ opacity: 0; transform: translateX(20px); }} to {{ opacity: 1; transform: translateX(0); }} }}

    /* Progress Bar */
    .c-progress-container {{ width: 100%; margin: 12px 0; }}
    .c-progress-bar {{
        width: 100%; height: 8px; background: var(--bg-alt);
        border-radius: 100px; overflow: hidden; position: relative;
    }}
    .c-progress-fill {{
        height: 100%; background: var(--primary); border-radius: 100px;
        transition: width 0.4s ease;
    }}
    .c-progress-label {{
        display: flex; justify-content: space-between; margin-bottom: 6px;
        font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-muted);
        text-transform: uppercase; font-weight: 700;
    }}

    /* Empty State */
    .c-empty-state {{
        padding: 60px 24px; text-align: center; background: var(--bg-surface);
        border: 1px dashed var(--border); border-radius: var(--radius);
        display: flex; flex-direction: column; align-items: center; gap: 16px;
    }}
    .c-empty-state__icon {{ font-size: 3rem; opacity: 0.3; }}
    .c-empty-state__title {{ font-weight: 800; font-size: 1.1rem; color: var(--text-main); }}
    .c-empty-state__text {{ font-size: 0.9rem; color: var(--text-muted); max-width: 400px; }}

    /* Accordion */
    .c-accordion {{ border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
    .c-accordion__item {{ border-bottom: 1px solid var(--border); }}
    .c-accordion__item:last-child {{ border-bottom: none; }}
    .c-accordion__header {{
        padding: 16px 20px; background: var(--bg-page); cursor: pointer;
        display: flex; justify-content: space-between; align-items: center;
        font-weight: 700; font-size: 0.9rem; transition: background 0.2s;
    }}
    .c-accordion__header:hover {{ background: var(--bg-alt); }}
    .c-accordion__icon {{ transition: transform 0.2s; color: var(--primary); }}
    .c-accordion__content {{ padding: 20px; background: var(--bg-surface); display: none; font-size: 0.95rem; }}

    /* Breadcrumbs */
    .c-breadcrumbs {{ display: flex; align-items: center; gap: 8px; list-style: none; padding: 0; margin: 0; }}
    .c-breadcrumbs__item {{ display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: var(--text-muted); }}
    .c-breadcrumbs__item a {{ color: var(--primary); text-decoration: none; font-weight: 600; }}
    .c-breadcrumbs__separator {{ opacity: 0.5; font-family: var(--font-mono); }}
    /* Charts */
    .c-chart-container {{
        position: relative; width: 100%; margin-bottom: 24px;
        background: var(--bg-surface); border: 1px solid var(--border);
        padding: 20px; border-left: 4px solid var(--primary);
        border-radius: var(--radius);
    }}
    .c-chart-title {{
        margin-top: 0; font-family: var(--font-mono); font-size: 0.85rem;
        margin-bottom: 16px; color: var(--text-main); text-transform: uppercase;
        font-weight: 800;
    }}
}}
"""
