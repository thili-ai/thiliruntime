"""Stand up all three real agents and run `process_return()` against every single-item order in
the seeded shop, scored against an independently-computed expected eligibility verdict and refund
amount — not a hand-picked list. See lesson 8.

Run with: `pytest tests/batch_eval.py -q`
"""
import sqlite3
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import pytest
import uvicorn
from thilia2a import build_catalog_app, build_order_app
from thilimcp import seed_shop

from thiliruntime import build_refund_app, process_return

TODAY = date(2026, 9, 30)
WINDOWS = {"electronics": 15, "clothing": 30, "perishables": 0}


def _run(app, port):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="session")
def step_urls():
    return {
        "check_eligibility": "http://127.0.0.1:8101",
        "compute_refund_amount": "http://127.0.0.1:8105",
    }


@pytest.fixture(scope="session", autouse=True)
def agents():
    tmp = Path(tempfile.mkdtemp())
    catalog_app = build_catalog_app(db_path=str(tmp / "catalog.db"))
    order_app = build_order_app(shop_db_path=str(tmp / "shop.db"))
    refund_app = build_refund_app(shop_db_path=str(tmp / "shop.db"))

    threading.Thread(target=_run, args=(catalog_app, 8102), daemon=True).start()
    threading.Thread(target=_run, args=(order_app, 8101), daemon=True).start()
    threading.Thread(target=_run, args=(refund_app, 8105), daemon=True).start()
    time.sleep(2)
    yield


@pytest.fixture(scope="session")
def grading_set():
    """Every single-item order's independently-computed expected eligibility and refund amount,
    plus a deterministic slice of ineligible cases, to reach a ~30-case batch."""
    conn = seed_shop(str(Path(tempfile.mkdtemp()) / "ground_truth.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT o.id, o.created_at, p.category, p.price_cents, p.tax_rate_percent, oi.quantity,
               count(oi.id) AS n_items
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        GROUP BY o.id HAVING n_items = 1
        ORDER BY o.id
    """).fetchall()

    cases = []
    for r in rows:
        delivered = date.fromisoformat(r["created_at"])
        days_elapsed = (TODAY - delivered).days
        window = WINDOWS[r["category"]]
        eligible = days_elapsed <= window
        subtotal = r["price_cents"] * r["quantity"]
        tax = subtotal * r["tax_rate_percent"] // 100
        cases.append({"order_id": r["id"], "eligible": eligible, "refund_cents": subtotal + tax})

    true_cases = [c for c in cases if c["eligible"]]
    false_cases = [c for c in cases if not c["eligible"]]
    return sorted(true_cases + false_cases[:24], key=lambda c: c["order_id"])


def _check(decision: str, case: dict) -> bool:
    if case["eligible"]:
        return decision == f"APPROVED: refund {case['refund_cents']} cents"
    return decision.startswith("DENIED")


async def test_batch_scores_every_case_correctly(grading_set, step_urls):
    for case in grading_set:
        report = await process_return(case["order_id"], step_urls)
        assert _check(report.decision, case), (case, report.decision)


async def test_independent_steps_land_in_the_same_wave(grading_set, step_urls):
    case = next(c for c in grading_set if c["eligible"])
    report = await process_return(case["order_id"], step_urls)
    wave_0_steps = {s.step for s in report.steps if s.wave == 0}
    assert wave_0_steps == {"check_eligibility", "compute_refund_amount"}
