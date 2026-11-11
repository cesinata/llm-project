"""Execution-accuracy evaluation: an answer is correct when its query returns the same data
as the gold query, ignoring column names, column order and extra columns."""

from __future__ import annotations

import datetime as dt
import decimal
import itertools
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .db import DuckDBDatabase


@dataclass
class Question:
    id: str
    question: str
    gold_sql: str | None
    difficulty: str = "medium"
    order_matters: bool = False
    notes: str = ""


def load_questions(path: Path) -> list[Question]:
    raw = yaml.safe_load(path.read_text())
    return [Question(**item) for item in raw["questions"]]


def _norm(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float | decimal.Decimal):
        # One decimal place: gold queries round ratios to 1 dp, counts are integers.
        return round(float(value), 1) + 0.0
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    return str(value).strip()


def _normalise(rows: list[tuple]) -> list[tuple]:
    return [tuple(_norm(v) for v in row) for row in rows]


def results_match(gold: list[tuple], pred: list[tuple], order_matters: bool = False) -> bool:
    gold, pred = _normalise(gold), _normalise(pred)
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    n_gold, n_pred = len(gold[0]), len(pred[0])
    if n_pred < n_gold:
        return False

    def column(rows: list[tuple], i: int) -> list:
        return [r[i] for r in rows]

    def same_values(a: list, b: list) -> bool:
        return a == b if order_matters else Counter(a) == Counter(b)

    # Each gold column must map to a distinct predicted column with the same values.
    candidates = [
        [j for j in range(n_pred) if same_values(column(gold, i), column(pred, j))]
        for i in range(n_gold)
    ]
    if any(not c for c in candidates):
        return False
    for mapping in itertools.product(*candidates):
        if len(set(mapping)) != len(mapping):
            continue
        projected = [tuple(row[j] for j in mapping) for row in pred]
        if order_matters and projected == gold:
            return True
        if not order_matters and Counter(projected) == Counter(gold):
            return True
    return False


def check_gold(db: DuckDBDatabase, questions: list[Question]) -> list[tuple[str, str]]:
    failures = []
    for q in questions:
        if q.gold_sql is None:
            continue
        try:
            db.run_query_all(q.gold_sql)
        except Exception as exc:  # noqa: BLE001
            failures.append((q.id, f"{type(exc).__name__}: {exc}"))
    return failures


def run_eval(agent, db: DuckDBDatabase, questions: list[Question], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    model = re.sub(r"[^A-Za-z0-9._-]", "_", getattr(agent.llm, "model", "unknown"))
    records_path = out_dir / f"{stamp}_{model}.jsonl"

    records = []
    with records_path.open("w") as fh:
        for q in questions:
            result = agent.ask(q.question)
            if q.gold_sql is None:
                correct = result.ok and result.sql is None
            elif not result.ok or result.sql is None:
                correct = False
            else:
                try:
                    gold = db.run_query_all(q.gold_sql).rows
                    pred = db.run_query_all(result.sql).rows
                    correct = results_match(gold, pred, q.order_matters)
                except Exception as exc:  # noqa: BLE001
                    result.error = result.error or f"{type(exc).__name__}: {exc}"
                    correct = False
            record = {
                "id": q.id,
                "difficulty": q.difficulty,
                "correct": correct,
                **result.to_dict(),
            }
            records.append(record)
            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()
            print(f"{'PASS' if correct else 'FAIL'} {q.id}: {q.question}", flush=True)

    summary = summarise(records, model=getattr(agent.llm, "model", "unknown"))
    summary["records"] = str(records_path)
    (out_dir / f"{stamp}_{model}.summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def summarise(records: list[dict], model: str) -> dict:
    n = len(records)
    if n == 0:
        return {"model": model, "questions": 0}
    by_difficulty: dict[str, list[bool]] = {}
    for r in records:
        by_difficulty.setdefault(r["difficulty"], []).append(r["correct"])
    total_tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in records)
    return {
        "model": model,
        "questions": n,
        "execution_accuracy": round(sum(r["correct"] for r in records) / n, 3),
        "by_difficulty": {
            k: {"n": len(v), "accuracy": round(sum(v) / len(v), 3)}
            for k, v in sorted(by_difficulty.items())
        },
        "self_corrected": sum(1 for r in records if r["correct"] and r["sql_errors"] > 0),
        "avg_steps": round(sum(r["steps"] for r in records) / n, 2),
        "avg_tokens": round(total_tokens / n),
        "total_tokens": total_tokens,
        "avg_latency_s": round(sum(r["latency_s"] for r in records) / n, 2),
    }
