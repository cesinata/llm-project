from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .db import Database, QueryResult

SYSTEM_PROMPT = """\
You are a data analyst answering questions about road crashes in Victoria, Australia.
You answer by writing {dialect} SQL against the tables you can inspect with your tools.

How to work:
1. Call list_tables, then describe_table for the tables you need. Read the column
   descriptions: they explain what each column means and list the exact category labels.
2. Use run_sql to test queries. If a query errors or the result looks wrong, fix it and retry.
3. Finish by calling final_answer with the single SQL query that answers the question and a
   short plain-English answer.

Rules:
- Filter text columns with the exact labels shown by describe_table (they are case-sensitive).
- Crashes (rows) and people (persons_* columns) are different things. Count rows for
  "how many crashes"; sum persons_* columns for "how many people".
- The latest year is only partly reported. Exclude it (is_complete_year = true) when
  comparing years or reporting trends, unless the user asks about that year specifically.
- Every number in your answer must come from a query result. Never estimate or invent figures.
- If the data cannot answer the question, call final_answer with sql set to null and explain why.
- Only SELECT queries are allowed.
"""

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List the available tables with their descriptions and row counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": (
                "Show a table's columns, types and descriptions, plus the exact values of "
                "low-cardinality text columns."
            ),
            "parameters": {
                "type": "object",
                "properties": {"table_name": {"type": "string"}},
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Run one SELECT query and see up to 30 rows of the result.",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "Submit the final SQL query and a short plain-English answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": ["string", "null"],
                        "description": "The query that answers the question, or null.",
                    },
                    "answer": {"type": "string"},
                },
                "required": ["sql", "answer"],
            },
        },
    },
]


class ChatModel(Protocol):
    model: str

    def chat(self, messages: list[dict], tools: list[dict]) -> Any: ...


@dataclass
class AgentResult:
    question: str
    answer: str | None = None
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    steps: int = 0
    sql_attempts: int = 0
    sql_errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    error: str | None = None
    trace: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and self.answer is not None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["rows"] = [list(r) for r in self.rows]
        return data


def _to_json(payload: Any) -> str:
    return json.dumps(payload, default=str)


class Agent:
    def __init__(
        self,
        db: Database,
        llm: ChatModel,
        max_steps: int = 12,
        preview_rows: int = 30,
        verbose: bool = False,
    ):
        self.db = db
        self.llm = llm
        self.max_steps = max_steps
        self.preview_rows = preview_rows
        self.verbose = verbose

    def ask(self, question: str) -> AgentResult:
        result = AgentResult(question=question)
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT.format(dialect=self.db.dialect)},
            {"role": "user", "content": question},
        ]
        last_good: tuple[str, QueryResult] | None = None
        start = time.perf_counter()
        try:
            for _ in range(self.max_steps):
                result.steps += 1
                response = self.llm.chat(messages, TOOLS)
                result.prompt_tokens += response.prompt_tokens
                result.completion_tokens += response.completion_tokens
                message = response.message
                tool_calls = message.tool_calls or []

                if not tool_calls:
                    # Some models answer in plain text instead of calling final_answer.
                    result.answer = (message.content or "").strip() or None
                    if last_good:
                        result.sql = last_good[0]
                        result.columns, result.rows = last_good[1].columns, last_good[1].rows
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {
                                    "name": c.function.name,
                                    "arguments": c.function.arguments,
                                },
                            }
                            for c in tool_calls
                        ],
                    }
                )

                finished = False
                for call in tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    output, sql_ok, query = self._run_tool(name, args, result)
                    if name == "run_sql" and query is not None:
                        last_good = (args.get("sql", ""), query)
                    result.trace.append({"tool": name, "args": args, "output": output[:2000]})
                    if self.verbose:
                        print(f"-> {name}({_to_json(args)[:300]})\n   {output[:300]}")
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                    if name == "final_answer" and sql_ok:
                        finished = True
                if finished:
                    break
            else:
                result.error = f"No final answer after {self.max_steps} steps."
        except Exception as exc:  # noqa: BLE001 - surface provider/network errors in the result
            result.error = f"{type(exc).__name__}: {exc}"
        result.latency_s = time.perf_counter() - start
        return result

    def _run_tool(
        self, name: str, args: dict, result: AgentResult
    ) -> tuple[str, bool, QueryResult | None]:
        """Return (tool output for the model, whether the call succeeded, any query result)."""
        try:
            if name == "list_tables":
                tables = [
                    {"table": t.name, "description": t.description, "rows": t.row_count}
                    for t in self.db.list_tables()
                ]
                return _to_json(tables), True, None

            if name == "describe_table":
                columns = self.db.describe_table(args.get("table_name", ""))
                payload = []
                for c in columns:
                    entry: dict[str, Any] = {"column": c.name, "type": c.type}
                    if c.description:
                        entry["description"] = c.description
                    if c.sample_values:
                        entry["values"] = c.sample_values
                    payload.append(entry)
                return _to_json(payload), True, None

            if name == "run_sql":
                result.sql_attempts += 1
                query = self.db.run_query(args.get("sql", ""), max_rows=self.preview_rows)
                output = _to_json(
                    {"columns": query.columns, "rows": query.rows, "truncated": query.truncated}
                )
                return output, True, query

            if name == "final_answer":
                sql = args.get("sql")
                if sql:
                    result.sql_attempts += 1
                    query = self.db.run_query(sql, max_rows=50)
                    result.sql = sql
                    result.columns, result.rows = query.columns, query.rows
                result.answer = args.get("answer", "")
                return "Answer recorded.", True, None

            return f"Error: unknown tool {name!r}.", False, None
        except Exception as exc:  # noqa: BLE001 - errors go back to the model so it can retry
            if name in ("run_sql", "final_answer"):
                result.sql_errors += 1
            return f"Error: {type(exc).__name__}: {exc}", False, None
