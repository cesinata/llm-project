"""Streamlit demo: ask Victoria's road crash data a question in plain English.

Run locally with `streamlit run streamlit_app.py`. On Streamlit Community Cloud, set the
provider and API key in the app's secrets (see README).
"""

from __future__ import annotations

import datetime as dt
import os
import threading

import streamlit as st

from crashsql.config import load_dotenv, warehouse_path

REPO_URL = "https://github.com/cesinata/llm-project"
DOCS_URL = "https://cesinata.github.io/llm-project/"
EXAMPLES = [
    "How many people were killed in road crashes in Victoria in 2024?",
    "Which council area had the largest increase in crashes from 2023 to 2024?",
    "Which year had the fewest crashes?",
    "What percentage of crashes in 2024 happened in the dark?",
    "How many crashes happened in New South Wales in 2024?",
]


def _secrets_to_env() -> None:
    try:
        secrets = dict(st.secrets)
    except Exception:  # no secrets file when running locally
        secrets = {}
    for key, value in secrets.items():
        if isinstance(value, str | int):
            os.environ.setdefault(key, str(value))
    load_dotenv()


_secrets_to_env()
QUESTIONS_PER_SESSION = int(os.environ.get("DEMO_QUESTIONS_PER_SESSION", "5"))
QUESTIONS_PER_DAY = int(os.environ.get("DEMO_QUESTIONS_PER_DAY", "100"))


class SharedDatabase:
    """One read-only DuckDB connection shared by all sessions, used by one thread at a time.

    DuckDB connections are not thread-safe, and a second connection to the same file in this
    process would fail because the first one locks the configuration.
    """

    def __init__(self, db):
        self._db = db
        self._lock = threading.Lock()
        self.dialect = db.dialect

    def list_tables(self):
        with self._lock:
            return self._db.list_tables()

    def describe_table(self, table):
        with self._lock:
            return self._db.describe_table(table)

    def run_query(self, sql, max_rows=50):
        with self._lock:
            return self._db.run_query(sql, max_rows=max_rows)


@st.cache_resource(show_spinner="Downloading and modelling the crash data (first visit only)...")
def get_database() -> SharedDatabase:
    from crashsql.cli import main as cli
    from crashsql.db import DuckDBDatabase

    if not warehouse_path().exists():
        if cli(["load"]) != 0 or cli(["build"]) != 0:
            raise RuntimeError("Building the warehouse failed; see the app logs.")
    return SharedDatabase(DuckDBDatabase(warehouse_path()))


@st.cache_resource
def shared_state() -> dict:
    """Answers and the daily question count, shared across all visitors."""
    return {"answers": {}, "day": dt.date.today(), "asked_today": 0, "lock": threading.Lock()}


def get_agent():
    from crashsql.agent import Agent
    from crashsql.llm import LLMClient

    return Agent(get_database(), LLMClient.from_env())


def ask(question: str) -> tuple[dict | None, str | None]:
    """Return (result, None) or (None, reason it was not answered)."""
    key = " ".join(question.lower().split())
    state = shared_state()
    if key in state["answers"]:
        return state["answers"][key], None

    asked = st.session_state.setdefault("asked", 0)
    if asked >= QUESTIONS_PER_SESSION:
        return None, (
            f"This demo answers {QUESTIONS_PER_SESSION} new questions per visit to stay within "
            "free API limits. The example questions still work, or run it yourself from GitHub."
        )
    with state["lock"]:
        if state["day"] != dt.date.today():
            state["day"], state["asked_today"] = dt.date.today(), 0
        if state["asked_today"] >= QUESTIONS_PER_DAY:
            return None, "The demo has reached today's question limit. Please try again tomorrow."
        state["asked_today"] += 1
    st.session_state["asked"] = asked + 1

    result = get_agent().ask(question).to_dict()
    if result["error"] is None:
        state["answers"][key] = result
    return result, None


def show(result: dict) -> None:
    if result["error"]:
        if result["provider_error"]:
            st.error("The language model service is busy or out of quota. Please try again later.")
        else:
            st.error(f"The agent could not answer: {result['error']}")
        return

    st.markdown(f"### {result['answer']}")
    if result["sql"]:
        st.code(result["sql"], language="sql")
        if result["rows"]:
            st.dataframe(
                [dict(zip(result["columns"], row, strict=False)) for row in result["rows"]],
                hide_index=True,
            )
    else:
        st.caption("No query: the agent decided the data cannot answer this question.")

    tokens = result["prompt_tokens"] + result["completion_tokens"]
    cols = st.columns(3)
    cols[0].metric("Steps", result["steps"])
    cols[1].metric("Tokens", f"{tokens:,}")
    cols[2].metric("Seconds", f"{result['latency_s']:.1f}")

    with st.expander("How the agent got there"):
        for i, step in enumerate(result["trace"], start=1):
            args = step["args"] if isinstance(step["args"], dict) else {}
            table = f" `{args['table_name']}`" if args.get("table_name") else ""
            st.markdown(f"**{i}. `{step['tool']}`**{table}")
            if args.get("sql"):
                st.code(args["sql"], language="sql")
            st.text(step["output"][:800])


st.set_page_config(page_title="crashsql: ask Victoria's crash data", layout="centered")
st.title("Ask Victoria's road crash data")
st.write(
    "An LLM agent turns your question into SQL, runs it on 202,554 police-reported crashes "
    "(2012 to March 2026), checks its own work, and answers in a sentence."
)

with st.sidebar:
    st.subheader("About")
    st.markdown(
        f"- [Code on GitHub]({REPO_URL})\n"
        f"- [How it works (learning path)]({DOCS_URL})\n"
        "- Data: [Victoria Road Crash Data](https://discover.data.vic.gov.au/dataset/"
        "victoria-road-crash-data), CC BY 4.0"
    )
    provider = os.environ.get("LLM_PROVIDER", "groq")
    model = os.environ.get("LLM_MODEL") or "default model"
    st.caption(f"Model: {provider} / {model}")
    questions_left = st.empty()

st.write("Try one:")
clicked = None
for example in EXAMPLES:
    if st.button(example, width="stretch"):
        clicked = example

with st.form("ask"):
    typed = st.text_input(
        "Or ask your own",
        placeholder="e.g. Which day of the week has the most crashes?",
        max_chars=300,
    )
    submitted = st.form_submit_button("Ask", type="primary")

question = clicked or (typed.strip() if submitted else "")
if question:
    st.caption(f"Question: {question}")
    with st.spinner("Thinking, writing SQL, checking the result..."):
        result, refusal = ask(question)
    if refusal:
        st.warning(refusal)
    else:
        show(result)

left = max(QUESTIONS_PER_SESSION - st.session_state.get("asked", 0), 0)
questions_left.caption(f"New questions left this visit: {left}")
