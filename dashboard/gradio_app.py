"""GeoAnalysis Agent — Gradio Dashboard (Gradio 6.x compatible)."""
import sys, os, json, time, psycopg2, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr

CUSTOM_CSS = """
.gradio-container { background: #0a0a14 !important; font-family: 'Segoe UI', system-ui, sans-serif !important; color: #e8e8f0 !important; max-width: 100% !important; }
.app-header { padding: 18px 24px 10px; border-bottom: 1px solid #2a2a4a; background: linear-gradient(135deg, #121228 0%, #0a0a14 100%); }
.app-header h1 { font-size: 22px; font-weight: 700; color: #e8e8f0; margin: 0; }
.app-header h1 span { color: #f59e0b; }
.app-header p { font-size: 12px; color: #a0a0c0; margin: 3px 0 0 0; }
.map-container { border-radius: 12px; overflow: hidden; border: 1px solid #2a2a4a; }
.quick-btn { background: #1e1e3a !important; color: #a0a0c0 !important; border: 1px solid #2a2a4a !important; border-radius: 8px !important; font-size: 12px !important; text-align: left !important; padding: 8px 12px !important; }
.quick-btn:hover { background: #28284c !important; color: #e8e8f0 !important; border-color: #4a4a7a !important; }
.status-bar { background: #1e1e3a; border: 1px solid #2a2a4a; border-radius: 8px; padding: 10px 14px; font-size: 11px; color: #6868a0; font-family: 'Consolas', monospace; }
"""


def _get_db_password():
    try:
        with open("Credentials.json") as f:
            return json.load(f)["password"]
    except Exception:
        return os.environ.get("DB_PASSWORD", "")


def _build_map_html(highlight_areas=None):
    from dashboard.map_component import build_sydney_map, map_to_html
    pw = _get_db_password()
    raw = psycopg2.connect(host='localhost', port=5432, dbname='geoanalysis', user='postgres', password=pw)
    df = pd.read_sql_query("SELECT sa2_name, final_score, rank_overall FROM well_resourced_scores", raw)
    raw.close()
    m = build_sydney_map(df, highlight_areas=highlight_areas)
    return map_to_html(m)


def _extract_areas(text):
    pw = _get_db_password()
    try:
        raw = psycopg2.connect(host='localhost', port=5432, dbname='geoanalysis', user='postgres', password=pw)
        df = pd.read_sql_query('SELECT "SA2_NAME21" FROM selected_sa2_regions', raw)
        raw.close()
        known = set(df['SA2_NAME21'].tolist())
        return [n for n in sorted(known, key=len, reverse=True) if n.lower() in text.lower()][:8]
    except Exception:
        return []


_MAP_PLACEHOLDER = """<div style="text-align:center;padding:40px;color:#6868a0;background:#121228;border-radius:12px;border:1px solid #2a2a4a;">
<div style="font-size:48px;margin-bottom:12px;">🗺️</div>
<div style="font-size:16px;font-weight:600;color:#a0a0c0;">Sydney SA2 Resource Map</div>
<div style="font-size:12px;margin-top:6px;">Loading interactive map...</div></div>"""


def _safe_build_map(highlight_areas=None):
    """Build map HTML, return placeholder on failure."""
    try:
        return _build_map_html(highlight_areas)
    except Exception as e:
        return _MAP_PLACEHOLDER


def create_ui(agent, session_mgr):
    initial_map = _MAP_PLACEHOLDER  # Don't render 19MB map until first user request

    with gr.Blocks(title="GeoAnalysis — Sydney Resource Intelligence") as demo:

        gr.HTML("""<div class="app-header"><h1>Geo<span>Analysis</span></h1><p>Sydney SA2 Resource Intelligence — 109 areas · 4 dimensions · Real-time spatial analysis</p></div>""")

        map_display = gr.HTML(value=initial_map, elem_classes="map-container")

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(label="", height=400)
                msg = gr.Textbox(placeholder="Ask about resource gaps, accessibility, or recommendations...", lines=2)
                with gr.Row():
                    submit = gr.Button("✦ Analyze", variant="primary")
                    clear = gr.Button("Clear")

            with gr.Column(scale=2):
                gr.Markdown("### ⚡ Quick Analysis")
                q1 = gr.Button("🏥 Which areas have the weakest healthcare?", elem_classes="quick-btn")
                q2 = gr.Button("🚌 Analyze Parramatta transport vs neighbors", elem_classes="quick-btn")
                q3 = gr.Button("🏫 Rank areas by education coverage", elem_classes="quick-btn")
                q4 = gr.Button("💰 Is income correlated with resources?", elem_classes="quick-btn")

                gr.Markdown("### 📊 Session")
                ctx = gr.Textbox(value="Ready.", lines=4, interactive=False, elem_classes="status-bar")

        gr.HTML("""<div style="padding:8px 24px;border-top:1px solid #2a2a4a;font-size:10px;color:#6868a0;display:flex;justify-content:space-between"><span>Data: ABS · TfNSW · NSW DoE · AEC · City of Sydney</span><span>Powered by smolagents + DeepSeek</span></div>""")

        def respond(message, history):
            if not message or not message.strip():
                return "", history or [], _build_map_html(), "Ready."
            try:
                response = session_mgr.chat(message)
            except Exception as e:
                return "", history or [], _build_map_html(), f"Error: {e}"
            history = history or []
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response})
            areas = _extract_areas(response)
            return "", history, _build_map_html(highlight_areas=areas), session_mgr.get_context_summary()

        submit.click(respond, [msg, chatbot], [msg, chatbot, map_display, ctx])
        msg.submit(respond, [msg, chatbot], [msg, chatbot, map_display, ctx])
        clear.click(lambda: ("", [], _build_map_html(), "Cleared."), outputs=[msg, chatbot, map_display, ctx])

        for btn, query in [
            (q1, "Which areas have the weakest public service scores? List top 5 with data."),
            (q2, "Analyze Parramatta's transport accessibility and compare to its neighbors."),
            (q3, "Rank all areas by education coverage. Show the bottom 5."),
            (q4, "Is there a correlation between income and RAI? Show evidence."),
        ]:
            btn.click(lambda q=query: q, outputs=[msg]).then(respond, [msg, chatbot], [msg, chatbot, map_display, ctx])

    return demo


def launch(port=7860, share=False):
    from src.config import load_config
    from src.agent import create_agent_with_kb
    from src.session.session_manager import SessionManager
    from data_warehouse.connection import DatabaseManager

    config = load_config()
    db_mgr = DatabaseManager(config)
    engine, conn = db_mgr.connect()

    print("🧠 Building Agent...")
    agent, retriever = create_agent_with_kb(config, conn)
    session_mgr = SessionManager(agent)

    print(f"🌐 http://localhost:{port}")
    demo = create_ui(agent, session_mgr)
    demo.queue(default_concurrency_limit=1).launch(
        server_port=port, share=share, css=CUSTOM_CSS,
    )


if __name__ == "__main__":
    launch()
