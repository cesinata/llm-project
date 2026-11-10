from crashsql.config import EVALS_DIR
from crashsql.evaluate import check_gold, load_questions, results_match


def test_exact_match():
    assert results_match([(1, "a")], [(1, "a")])


def test_ignores_column_order_and_extra_columns():
    gold = [("CASEY", 51), ("GEELONG", 41)]
    pred = [(1, 51, "CASEY"), (2, 41, "GEELONG")]
    assert results_match(gold, pred)


def test_row_order_only_checked_when_required():
    gold = [(2015, 10), (2016, 12)]
    pred = [(2016, 12), (2015, 10)]
    assert results_match(gold, pred, order_matters=False)
    assert not results_match(gold, pred, order_matters=True)


def test_numbers_compared_to_one_decimal():
    assert results_match([(22.1,)], [(22.08,)])
    assert results_match([(284,)], [(284.0,)])
    assert not results_match([(22.1,)], [(0.221,)])


def test_wrong_row_count_or_values_fail():
    assert not results_match([(1,)], [(1,), (2,)])
    assert not results_match([("CASEY", 51)], [("CASEY", 50)])
    assert not results_match([("a", 1)], [(1,)])


def test_columns_need_distinct_matches():
    # Both gold columns hold 5, but the prediction has only one column with 5.
    assert not results_match([(5, 5)], [(5, 6)])


def test_question_file_is_valid():
    questions = load_questions(EVALS_DIR / "questions.yaml")
    assert len({q.id for q in questions}) == len(questions)
    assert any(q.gold_sql is None for q in questions)


def test_all_gold_queries_run(db):
    questions = load_questions(EVALS_DIR / "questions.yaml")
    assert check_gold(db, questions) == []
