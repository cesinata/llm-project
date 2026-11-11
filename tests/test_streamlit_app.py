from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402
from test_agent import ScriptedLLM, tool_call  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
COUNT_SQL = "select count(*) from crashes"
ANSWER = "There are 1,000 crashes."


def scripted_client():
    return ScriptedLLM(
        [
            (None, [tool_call("describe_table", 1, table_name="crashes")]),
            (None, [tool_call("run_sql", 2, sql=COUNT_SQL)]),
            (None, [tool_call("final_answer", 3, sql=COUNT_SQL, answer=ANSWER)]),
        ]
    )


@pytest.fixture()
def app(warehouse, monkeypatch):
    monkeypatch.setenv("CRASHSQL_DB", str(warehouse))
    monkeypatch.setattr("crashsql.llm.LLMClient.from_env", staticmethod(scripted_client))
    st.cache_resource.clear()
    yield AppTest.from_file(APP, default_timeout=30)
    st.cache_resource.clear()


def ask(at, question):
    at.text_input[0].input(question)
    at.button[-1].click()  # the form's Ask button comes last
    return at.run()


def test_answers_with_sql_rows_and_trace(app):
    at = ask(app.run(), "How many crashes?")
    assert not at.exception
    assert any(ANSWER in m.value for m in at.markdown)
    assert any(c.value == COUNT_SQL for c in at.code)
    assert at.dataframe[0].value.iloc[0, 0] == 1000
    assert [m.value for m in at.metric][0] == "3"
    assert "New questions left this visit: 4" in [c.value for c in at.sidebar.caption]


def test_example_button_asks_immediately(app):
    at = app.run()
    at.button[0].click()
    at.run()
    assert not at.exception
    assert any(c.value == COUNT_SQL for c in at.code)


def test_session_limit_but_repeated_questions_are_free(app, monkeypatch):
    monkeypatch.setenv("DEMO_QUESTIONS_PER_SESSION", "1")
    at = ask(app.run(), "How many crashes?")
    assert not at.warning
    at = ask(at, "  how many CRASHES? ")  # same question, served from the shared cache
    assert not at.warning
    at = ask(at, "Which day has the most crashes?")
    assert "new questions per visit" in at.warning[0].value
