import json
from types import SimpleNamespace

from crashsql.agent import Agent
from crashsql.llm import ChatResponse


def tool_call(name, i, **args):
    return SimpleNamespace(
        id=f"call_{i}", function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


class ScriptedLLM:
    """Replays a fixed list of assistant messages and records what it was sent."""

    model = "scripted"

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append(list(messages))
        content, calls = self.turns.pop(0)
        return ChatResponse(SimpleNamespace(content=content, tool_calls=calls), 100, 20)


def test_happy_path_with_self_correction(db):
    count_sql = "select count(*) from crashes"
    llm = ScriptedLLM(
        [
            (None, [tool_call("list_tables", 1)]),
            (None, [tool_call("describe_table", 2, table_name="crashes")]),
            (None, [tool_call("run_sql", 3, sql="select count(*) from crash")]),
            (None, [tool_call("run_sql", 4, sql=count_sql)]),
            (None, [tool_call("final_answer", 5, sql=count_sql, answer="1000 crashes.")]),
        ]
    )
    result = Agent(db, llm).ask("How many crashes?")

    assert result.ok
    assert result.rows == [(1000,)]
    assert result.sql_errors == 1
    assert result.sql_attempts == 3
    assert result.steps == 5
    assert result.prompt_tokens == 500
    # The SQL error was passed back to the model so it could fix the table name.
    tool_messages = [m for m in llm.seen[3] if m["role"] == "tool"]
    assert "Catalog Error" in tool_messages[-1]["content"]


def test_unsafe_sql_is_reported_back_not_run(db):
    llm = ScriptedLLM(
        [
            (None, [tool_call("run_sql", 1, sql="drop table crashes")]),
            (None, [tool_call("final_answer", 2, sql=None, answer="I can only read data.")]),
        ]
    )
    result = Agent(db, llm).ask("Delete everything")
    assert result.ok
    assert result.sql is None
    assert result.sql_errors == 1
    assert "Only SELECT" in result.trace[0]["output"]


def test_failed_final_answer_does_not_finish(db):
    llm = ScriptedLLM(
        [
            (None, [tool_call("final_answer", 1, sql="select nope from crashes", answer="?")]),
            (None, [tool_call("final_answer", 2, sql="select 1", answer="Fixed.")]),
        ]
    )
    result = Agent(db, llm).ask("q")
    assert result.ok
    assert result.answer == "Fixed."
    assert result.steps == 2


def test_empty_reply_is_nudged_to_final_answer(db):
    count_sql = "select count(*) from crashes"
    llm = ScriptedLLM(
        [
            (None, [tool_call("run_sql", 1, sql=count_sql)]),
            ("", None),
            (None, [tool_call("final_answer", 2, sql=count_sql, answer="1000 crashes.")]),
        ]
    )
    result = Agent(db, llm).ask("How many crashes?")
    assert result.ok
    assert result.answer == "1000 crashes."
    assert "final_answer" in llm.seen[2][-1]["content"]


def test_final_answer_typed_as_json_text(db):
    reply = '```json\n{"sql": "select count(*) from crashes", "answer": "1000 crashes."}\n```'
    llm = ScriptedLLM([(reply, None)])
    result = Agent(db, llm).ask("How many crashes?")
    assert result.ok
    assert result.rows == [(1000,)]
    assert result.steps == 1


def test_plain_text_answer_falls_back_to_last_good_sql(db):
    llm = ScriptedLLM(
        [
            (None, [tool_call("run_sql", 1, sql="select count(*) from crashes")]),
            ("There are 1000 crashes.", None),
            ("There are 1000 crashes.", None),
        ]
    )
    result = Agent(db, llm, max_nudges=1).ask("How many crashes?")
    assert result.ok
    assert result.sql == "select count(*) from crashes"
    assert result.rows == [(1000,)]


def test_gives_up_after_max_steps(db):
    llm = ScriptedLLM([(None, [tool_call("list_tables", i)]) for i in range(3)])
    result = Agent(db, llm, max_steps=3).ask("q")
    assert not result.ok
    assert "3 steps" in result.error


def test_provider_errors_are_captured(db):
    class Broken:
        model = "broken"

        def chat(self, messages, tools):
            raise ConnectionError("rate limited")

    result = Agent(db, Broken()).ask("q")
    assert not result.ok
    assert "rate limited" in result.error
