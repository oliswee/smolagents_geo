"""Gradio UI for GeoAnalysis Agent.

One-line launch with smolagents' built-in GradioUI,
extended with a custom map component for Folium integration.
"""
import gradio as gr
from smolagents import GradioUI


def create_ui(agent, session_manager) -> gr.Blocks:
    """Create a custom Gradio interface wrapping the smolagents agent.

    Args:
        agent: smolagents CodeAgent instance.
        session_manager: SessionManager instance.

    Returns:
        Gradio Blocks app.
    """
    # Use smolagents' built-in GradioUI as the base
    # This gives us the agent thinking process visualization for free
    base_ui = GradioUI(agent)

    # For a fully custom UI, we can build our own Blocks:
    with gr.Blocks(
        title="GeoAnalysis Agent — 悉尼城市规划分析助手",
        theme=gr.themes.Soft(),
    ) as demo:
        gr.Markdown("""
        # 🏙️ GeoAnalysis Agent
        ### 悉尼 109 个行政区的资源分配智能分析助手

        用自然语言提问，获取区域资源短板识别、空间可达性分析和差异化配置建议。
        """)

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="分析对话",
                    height=500,
                    show_copy_button=True,
                )
                msg = gr.Textbox(
                    label="输入你的问题",
                    placeholder="例如：Parramatta 周边哪些区缺诊所？交通也帮我看看",
                    lines=3,
                )
                with gr.Row():
                    submit_btn = gr.Button("🔍 分析", variant="primary")
                    clear_btn = gr.Button("🗑️ 清空对话")

            with gr.Column(scale=1):
                gr.Markdown("### 📊 快速分析")
                quick_btn_1 = gr.Button("🏥 哪些区医疗资源最缺？")
                quick_btn_2 = gr.Button("🚌 Parramatta 交通可达性如何？")
                quick_btn_3 = gr.Button("🏫 教育覆盖排名")
                quick_btn_4 = gr.Button("💰 高收入区资源一定好吗？")

                gr.Markdown("### 📋 会话状态")
                context_display = gr.Textbox(
                    label="当前分析上下文",
                    value="尚未开始分析",
                    lines=6,
                    interactive=False,
                )

                gr.Markdown("""
                ### 💡 示例提问
                - "分析 Wiley Park 的资源短板并给出建议"
                - "Inner South West 区域哪些区交通最好？"
                - "Granville 2公里内有多少学校？"
                - "上次那几个低资源区，分析一下教育维度"
                """)

        def respond(message, history):
            """Handle user message and return response."""
            if not message.strip():
                return "", history

            try:
                response = session_manager.chat(message)
            except Exception as e:
                response = f"❌ 分析出错: {str(e)}"

            history = history or []
            history.append((message, response))

            context = session_manager.get_context_summary()
            return "", history, context

        def quick_ask(question):
            return question

        # Wire up callbacks
        submit_btn.click(
            respond,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, context_display],
        )
        msg.submit(
            respond,
            inputs=[msg, chatbot],
            outputs=[msg, chatbot, context_display],
        )
        clear_btn.click(
            lambda: (session_manager.reset(), [], "对话已清空"),
            outputs=[chatbot, context_display],
        )

        # Quick buttons — fill the textbox
        quick_btn_1.click(
            lambda: "哪些区域在公共服务维度上资源最缺？列出 top 5",
            outputs=[msg],
        ).then(
            respond, inputs=[msg, chatbot], outputs=[msg, chatbot, context_display]
        )
        quick_btn_2.click(
            lambda: "分析 Parramatta 的交通可达性，并和它的邻居区域做对比",
            outputs=[msg],
        ).then(
            respond, inputs=[msg, chatbot], outputs=[msg, chatbot, context_display]
        )
        quick_btn_3.click(
            lambda: "按教育覆盖维度对全部 109 区排名，列出最缺教育资源的 5 个区",
            outputs=[msg],
        ).then(
            respond, inputs=[msg, chatbot], outputs=[msg, chatbot, context_display]
        )
        quick_btn_4.click(
            lambda: "高收入区域的 RAI 评分一定高吗？用数据说明",
            outputs=[msg],
        ).then(
            respond, inputs=[msg, chatbot], outputs=[msg, chatbot, context_display]
        )

    return demo


def launch(config_path: str = "config.yaml", share: bool = False):
    """Launch the GeoAnalysis Agent Gradio app.

    Args:
        config_path: Path to config.yaml.
        share: If True, create a public Gradio link.
    """
    from src.config import load_config
    from src.agent import create_agent_with_kb
    from src.session.session_manager import SessionManager
    from data_warehouse.connection import DatabaseManager

    config = load_config(config_path)
    db_mgr = DatabaseManager(config)
    _, conn = db_mgr.connect()

    print("Building agent and initializing knowledge base...")
    agent, retriever = create_agent_with_kb(config, conn)
    session_mgr = SessionManager(agent)

    print("Launching Gradio UI...")
    demo = create_ui(agent, session_mgr)
    demo.launch(share=share)


if __name__ == "__main__":
    launch()
