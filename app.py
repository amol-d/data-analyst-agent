"""Gradio demo UI for the Data Analyst Agent, mounted on FastAPI.

The uploaded dataframe lives in per-session gr.State — never shared across visitors.
"""

from __future__ import annotations

import gradio as gr

from data_analyst_agent.agent import DataAnalystAgent
from data_analyst_agent.config import CONFIG
from data_analyst_agent.security import RateLimitError, ValidationError, sanitize_text, validate_upload
from data_analyst_agent.web import LIMITER, caller_id, make_app, run

_agent: DataAnalystAgent | None = None
ALLOWED = {".csv"}


def _get_agent() -> DataAnalystAgent:
    global _agent
    if _agent is None:
        _agent = DataAnalystAgent()
    return _agent


def load_csv(file_obj, request: gr.Request):
    if file_obj is None:
        return None, "Upload a CSV file to begin."
    path = file_obj if isinstance(file_obj, str) else getattr(file_obj, "name", None)
    try:
        validate_upload(path, ALLOWED)
        df = _get_agent().load(path)
    except ValidationError as exc:
        return None, f"⚠️ {exc}"
    except Exception:  # noqa: BLE001
        return None, "⚠️ Could not read that file."
    rows, cols = df.shape
    return df, f"✅ Loaded **{rows} rows × {cols} columns**. Ask a question below."


def ask(question: str, df, request: gr.Request):
    try:
        clean = sanitize_text(question, field="a question", min_chars=3, max_chars=400)
    except ValidationError as exc:
        yield f"⚠️ {exc}"
        return
    if df is None:
        yield "⚠️ Please upload a CSV first."
        return
    try:
        LIMITER.check(caller_id(request))
    except RateLimitError as exc:
        yield f"⏳ {exc}"
        return
    if not CONFIG.api_key_present:
        yield "⚠️ The demo is not configured (missing API key). See the GitHub repo to run it locally."
        return
    yield "📊 Analyzing the data…"
    try:
        yield _get_agent().analyze(df, clean)
    except Exception:  # noqa: BLE001
        yield "⚠️ Something went wrong. Please try again in a moment."


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Data Analyst Agent — Day 07", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "## 📊 Data Analyst Agent\n"
            "Upload a CSV, then ask questions — the agent profiles the data (schema, "
            "stats, sample) and reasons over it. *(No code is executed on your data.)*\n\n"
            "*Day 07 of 14 AI Agents in 14 Days — data analysis + structured reasoning.*"
        )
        df_state = gr.State(None)
        file_in = gr.File(label="CSV file", file_types=[".csv"], file_count="single")
        status = gr.Markdown("Upload a CSV file to begin.")
        question = gr.Textbox(label="Your question", placeholder="e.g. Which category has the highest average value?", lines=2)
        run_btn = gr.Button("Analyze", variant="primary")
        out = gr.Markdown()
        file_in.change(load_csv, inputs=file_in, outputs=[df_state, status])
        run_btn.click(ask, inputs=[question, df_state], outputs=out)
        question.submit(ask, inputs=[question, df_state], outputs=out)
    demo.queue(default_concurrency_limit=2, max_size=20)
    return demo


app = make_app(build_demo(), title="Data Analyst Agent")

if __name__ == "__main__":
    run(app)
