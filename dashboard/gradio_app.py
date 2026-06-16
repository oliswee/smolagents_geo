"""GeoAnalysis Agent — Dashboard.

Aesthetic: editorial data-dashboard. Dark navy + warm amber accents.
Hero element: Interactive Sydney SA2 map with live RAI color-coding.
Layout: Chat sidebar + Map viewport + Context footer.
"""
import gradio as gr
import re
from pathlib import Path


# ═══════════════════════════════════════════════════════════
# Custom CSS — distinctive, not cookie-cutter
# ═══════════════════════════════════════════════════════════
CUSTOM_CSS = r"""
/* ── Fonts ──────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:ital,wght@0,400;0,500;1,400&display=swap');

/* ── Global ─────────────────────────────────────────────── */
:root {
  --bg-primary: #0a0a14;
  --bg-secondary: #121228;
  --bg-tertiary: #1a1a32;
  --surface: #1e1e3a;
  --surface-hover: #28284c;
  --border: #2a2a4a;
  --border-active: #4a4a7a;
  --text-primary: #e8e8f0;
  --text-secondary: #a0a0c0;
  --text-muted: #6868a0;
  --accent-amber: #f59e0b;
  --accent-coral: #ff6b6b;
  --accent-teal: #2dd4bf;
  --accent-blue: #60a5fa;
  --accent-green: #4ade80;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --shadow: 0 4px 24px rgba(0,0,0,0.4);
  --transition: 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.gradio-container {
  background: var(--bg-primary) !important;
  font-family: 'DM Sans', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
  color: var(--text-primary) !important;
  max-width: 100% !important;
}

/* ── Header ─────────────────────────────────────────────── */
.app-header {
  padding: 20px 28px 12px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
}
.app-header h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}
.app-header h1 span { color: var(--accent-amber); }
.app-header p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 4px 0 0 0;
}

/* ── Chat panel ─────────────────────────────────────────── */
.chat-panel {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
}

/* ── Buttons ────────────────────────────────────────────── */
button.primary {
  background: var(--accent-amber) !important;
  color: #0a0a14 !important;
  font-weight: 600 !important;
  border: none !important;
  border-radius: var(--radius-sm) !important;
  transition: all var(--transition) !important;
}
button.primary:hover {
  background: #fbbf24 !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(245,158,11,0.3);
}

.quick-btn {
  background: var(--surface) !important;
  color: var(--text-secondary) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  font-size: 12px !important;
  transition: all var(--transition) !important;
  text-align: left !important;
  padding: 8px 12px !important;
}
.quick-btn:hover {
  background: var(--surface-hover) !important;
  color: var(--text-primary) !important;
  border-color: var(--border-active) !important;
}

/* ── Map container ──────────────────────────────────────── */
.map-container {
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

/* ── Status bar ─────────────────────────────────────────── */
.status-bar {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.status-bar .label { color: var(--text-secondary); font-weight: 500; }
.status-bar .value { color: var(--accent-teal); }

/* ── Tab override ───────────────────────────────────────── */
.tabs {
  border-bottom: 1px solid var(--border) !important;
}
.tab-nav button {
  color: var(--text-secondary) !important;
  font-weight: 500 !important;
}
.tab-nav button.selected {
  color: var(--accent-amber) !important;
  border-bottom: 2px solid var(--accent-amber) !important;
}

/* ── Markdown ───────────────────────────────────────────── */
.prose { color: var(--text-secondary); font-size: 13px; line-height: 1.7; }
.prose h3 { color: var(--text-primary); font-size: 15px; }

/* ── Chatbot customization ──────────────────────────────── */
.bubble-wrap { font-size: 13px; }
.message-row.bot .message { background: var(--surface); border-radius: var(--radius-sm); }
.message-row.user .message { background: var(--accent-amber); color: #0a0a14; }

/* ── Footer ─────────────────────────────────────────────── */
.app-footer {
  padding: 10px 28px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
}
"""


# ═══════════════════════════════════════════════════════════
# Helper: extract area names from Agent response
# ═══════════════════════════════════════════════════════════
def _extract_areas(text: str) -> list:
    """Heuristic: find SA2 area names mentioned in Agent response."""
    import pandas as pd, psycopg2, os

    # Load known area names
    try:
        pw = os.environ.get("DB_PASSWORD", "")
        raw = psycopg2.connect(
            host='localhost', port=5432, dbname='geoanalysis',
            user='postgres', password=pw
        )
        df = pd.read_sql_query('SELECT "SA2_NAME21" FROM selected_sa2_regions', raw)
        raw.close()
        known = set(df['SA2_NAME21'].tolist())
    except Exception:
        return []

    found = []
    for name in sorted(known, key=len, reverse=True):
        if name.lower() in text.lower():
            found.append(name)
    return found[:8]


# ═══════════════════════════════════════════════════════════
# Main UI
# ═══════════════════════════════════════════════════════════
def create_ui(agent, session_manager) -> gr.Blocks:
    import time
    from dashboard.map_component import quick_map_html

    with gr.Blocks(
        title="GeoAnalysis — Sydney Resource Intelligence",
        css=CUSTOM_CSS,
        theme=gr.themes.Base(),
        head="""
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        """,
    ) as demo:

        # ── Header ─────────────────────────────────────────
        gr.HTML("""
        <div class="app-header">
            <h1>Geo<span>Analysis</span></h1>
            <p>Sydney SA2 Resource Intelligence &mdash; 109 areas &middot; 4 dimensions &middot; Real-time spatial analysis</p>
        </div>
        """)

        # ── Map (hero element, full-width) ─────────────────
        with gr.Row():
            initial_map = quick_map_html()
            map_display = gr.HTML(
                value=initial_map,
                elem_classes="map-container",
            )

        # ── Main 2-column layout ───────────────────────────
        with gr.Row(equal_height=False):
            # Left: chat panel
            with gr.Column(scale=3, elem_classes="chat-panel"):
                chatbot = gr.Chatbot(
                    label="",
                    height=400,
                    show_copy_button=True,
                    bubble_full_width=False,
                    placeholder="""
                    <div style='color:#6868a0;text-align:center;padding:40px 20px;'>
                        <div style='font-size:40px;margin-bottom:12px;'>🏙️</div>
                        <div style='font-size:15px;font-weight:600;color:#a0a0c0;margin-bottom:6px;'>
                            Ask anything about Sydney's resource distribution
                        </div>
                        <div style='font-size:12px;color:#6868a0;'>
                            e.g. "Which areas near Parramatta lack public services?"
                        </div>
                    </div>""",
                )
                msg = gr.Textbox(
                    label="",
                    placeholder="Ask about resource gaps, accessibility, or recommendations...",
                    lines=2,
                    scale=1,
                    elem_id="chat-input",
                )
                with gr.Row():
                    submit_btn = gr.Button(
                        "✦ Analyze",
                        variant="primary",
                        size="sm",
                        elem_classes="primary",
                    )
                    clear_btn = gr.Button(
                        "Clear",
                        size="sm",
                    )

            # Right: context panel
            with gr.Column(scale=2):
                gr.HTML('<div class="prose"><h3>⚡ Quick Analysis</h3></div>')
                quick_btn_1 = gr.Button(
                    "🏥  Which areas have the weakest healthcare access?",
                    elem_classes="quick-btn",
                )
                quick_btn_2 = gr.Button(
                    "🚌  Analyze Parramatta's transport and compare with neighbors",
                    elem_classes="quick-btn",
                )
                quick_btn_3 = gr.Button(
                    "🏫  Rank all 109 areas by education coverage",
                    elem_classes="quick-btn",
                )
                quick_btn_4 = gr.Button(
                    "💰  Is higher income always = higher resources?",
                    elem_classes="quick-btn",
                )

                gr.HTML('<div class="prose" style="margin-top:16px;"><h3>📊 Session</h3></div>')
                context_display = gr.Textbox(
                    label="",
                    value="Ready. No analysis yet.",
                    lines=5,
                    interactive=False,
                    elem_classes="status-bar",
                    show_label=False,
                )

        # ── Footer ─────────────────────────────────────────
        gr.HTML("""
        <div class="app-footer">
            <span>Data: ABS Census 2021 &middot; Transport for NSW &middot; NSW DoE &middot; AEC &middot; City of Sydney</span>
            <span>Powered by smolagents + DeepSeek</span>
        </div>
        """)

        # ═══════════════════════════════════════════════════
        # Callbacks
        # ═══════════════════════════════════════════════════
        def respond(message, history):
            if not message or not message.strip():
                return "", history, quick_map_html(), "Ready."

            try:
                response = session_manager.chat(message)
            except Exception as e:
                response = f"❌ {str(e)}"
                return "", history if history else [], quick_map_html(), "Error."

            history = history or []
            history.append((message, response))

            # Extract areas for map highlighting
            areas = _extract_areas(response)
            new_map = quick_map_html(highlight_areas=areas if areas else None)
            ctx = session_manager.get_context_summary()

            return "", history, new_map, ctx

        def handle_quick(query):
            """Fill textbox and auto-trigger."""
            return query

        # Wire
        submit_btn.click(
            respond,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, map_display, context_display],
        )
        msg.submit(
            respond,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, map_display, context_display],
        )
        clear_btn.click(
            lambda: ("", [], quick_map_html(), "Cleared."),
            outputs=[msg, chatbot, map_display, context_display],
        )

        for btn, query in [
            (quick_btn_1, "Which areas have the weakest public service scores? List top 5 with data."),
            (quick_btn_2, "Analyze Parramatta's transport accessibility and compare it to its neighboring suburbs."),
            (quick_btn_3, "Rank all areas by education coverage. Show the bottom 5 and their z-scores."),
            (quick_btn_4, "Is there a correlation between median income and RAI scores? Show the data."),
        ]:
            btn.click(
                lambda q=query: q, outputs=[msg]
            ).then(
                respond, inputs=[msg, chatbot], outputs=[msg, chatbot, map_display, context_display]
            )

    return demo


def launch(config_path: str = "config.yaml", share: bool = False, port: int = 7860):
    from src.config import load_config
    from src.agent import create_agent_with_kb
    from src.session.session_manager import SessionManager
    from data_warehouse.connection import DatabaseManager

    config = load_config(config_path)
    db_mgr = DatabaseManager(config)
    _, conn = db_mgr.connect()

    print("🧠 Building Agent...")
    agent, retriever = create_agent_with_kb(config, conn)
    session_mgr = SessionManager(agent)

    print(f"🌐 Launching on http://localhost:{port}")
    demo = create_ui(agent, session_mgr)
    demo.queue(default_concurrency_limit=1).launch(
        server_port=port,
        share=share,
        favicon_path=None,
        show_api=False,
    )


if __name__ == "__main__":
    launch()
