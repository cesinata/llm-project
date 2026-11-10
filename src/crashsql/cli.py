from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import DBT_DIR, EVALS_DIR, RAW_CSV, SAMPLE_CSV, load_dotenv, warehouse_path


def cmd_load(args: argparse.Namespace) -> int:
    from .data import download, load_raw

    if args.sample:
        csv = SAMPLE_CSV
    else:
        print(f"Downloading crash data to {RAW_CSV} (about 70 MB, skipped if present)...")
        csv = download(force=args.force)
    rows = load_raw(csv, warehouse_path())
    print(f"Loaded {rows:,} rows from {csv.name} into raw.crashes in {warehouse_path()}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    env = {**os.environ, "CRASHSQL_DB": str(warehouse_path().resolve())}
    command = ["dbt", "build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if args.target:
        command += ["--target", args.target]
    return subprocess.call(command, env=env)


def cmd_ask(args: argparse.Namespace) -> int:
    from .agent import Agent
    from .db import DuckDBDatabase
    from .llm import LLMClient

    db = DuckDBDatabase(warehouse_path())
    agent = Agent(db, LLMClient.from_env(), verbose=args.verbose)
    result = agent.ask(args.question)
    if result.sql:
        print(f"\nSQL:\n{result.sql}\n")
    if result.rows:
        print(" | ".join(result.columns))
        for row in result.rows[:20]:
            print(" | ".join(str(v) for v in row))
        print()
    print(result.answer or result.error)
    print(
        f"\n[{result.steps} steps, {result.prompt_tokens + result.completion_tokens:,} tokens, "
        f"{result.latency_s:.1f}s]"
    )
    return 0 if result.ok else 1


def cmd_eval(args: argparse.Namespace) -> int:
    from .db import DuckDBDatabase
    from .evaluate import check_gold, load_questions, run_eval

    questions = load_questions(Path(args.questions))
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q.id in wanted]
    db = DuckDBDatabase(warehouse_path())

    if args.gold_only:
        failures = check_gold(db, questions)
        for qid, error in failures:
            print(f"FAIL {qid}: {error}")
        print(f"{len(questions) - len(failures)}/{len(questions)} gold queries ran.")
        return 1 if failures else 0

    from .agent import Agent
    from .llm import LLMClient

    agent = Agent(db, LLMClient.from_env())
    summary = run_eval(agent, db, questions, Path(args.out))
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="crashsql")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("load", help="Download the crash CSV and load it into DuckDB.")
    p.add_argument("--sample", action="store_true", help="Use the bundled 1,000-row sample.")
    p.add_argument("--force", action="store_true", help="Re-download even if the CSV exists.")
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("build", help="Run dbt build (models + data tests).")
    p.add_argument("--target", help="dbt target, e.g. snowflake. Defaults to duckdb.")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("ask", help="Ask a question in plain English.")
    p.add_argument("question")
    p.add_argument("-v", "--verbose", action="store_true", help="Print each tool call.")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("eval", help="Run the evaluation set.")
    p.add_argument("--questions", default=str(EVALS_DIR / "questions.yaml"))
    p.add_argument("--out", default=str(EVALS_DIR / "results"))
    p.add_argument("--only", help="Comma-separated question ids.")
    p.add_argument("--gold-only", action="store_true", help="Only check the gold SQL runs.")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
