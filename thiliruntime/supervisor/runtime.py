"""Sequencing, state-passing, concurrent dispatch, and failure handling for "process a return."

`process_return()` holds the whole plan, calls every step in a wave concurrently, carries state
between waves, and never guesses when a worker fails — it retries what might be transient, aborts
honestly with whatever partial state it has when a worker doesn't recover, and returns a full,
auditable `DecisionReport` either way. It contains no business logic about orders, eligibility, or
tax — only the graph and the URLs it was handed. See lessons 4-7.
"""
import asyncio
import re
import time

from thilia2a import ask, parse_returnable

from thiliruntime.reports.decision_report import DecisionReport, StepRecord
from thiliruntime.supervisor.plan import PLAN, waves


async def call_with_retry(
    step: str,
    order_id: int,
    wave_index: int,
    step_urls: dict[str, str],
    max_attempts: int = 2,
    retry_delay: float = 0.5,
    timeout: float = 2.0,
) -> StepRecord:
    """Retry a transient failure (an exception or a timeout) up to `max_attempts` times, with a
    short pause between attempts. Return immediately on a deliberate `TASK_STATE_FAILED` verdict
    without retrying it — a worker's deterministic answer won't change on a second try, so
    retrying it only wastes time proving what's already known. See lesson 6.
    """
    start = time.monotonic()
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            state, text = await asyncio.wait_for(
                ask(str(order_id), base_url=step_urls[step]), timeout=timeout,
            )
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < max_attempts:
                await asyncio.sleep(retry_delay)
                continue
            return StepRecord(
                step, wave_index, attempt, False,
                f"{step} unreachable after {max_attempts} attempts: {last_error}",
                time.monotonic() - start,
            )

        if state == "TASK_STATE_FAILED":
            return StepRecord(step, wave_index, attempt, False, f"{step} failed: {text}", time.monotonic() - start)

        return StepRecord(step, wave_index, attempt, True, text, time.monotonic() - start)

    return StepRecord(
        step, wave_index, max_attempts, False,
        f"{step} unreachable after {max_attempts} attempts: {last_error}", time.monotonic() - start,
    )


async def process_return(order_id: int, step_urls: dict[str, str]) -> DecisionReport:
    """Run `PLAN` wave by wave: every step in a wave concurrently (lesson 5), with retry-or-abort
    on failure (lesson 6), collecting a full `DecisionReport` as it goes (lesson 7).

    `step_urls` maps a plan node's name to the base URL of the agent that answers it, e.g.
    `{"check_eligibility": "http://127.0.0.1:8101", "compute_refund_amount": "http://127.0.0.1:8105"}`.
    """
    report = DecisionReport(order_id=order_id)
    state: dict[str, tuple[bool, str]] = {}

    for wave_index, wave in enumerate(waves(PLAN)):
        worker_steps = [step for step in wave if step != "decide"]
        if worker_steps:
            records = await asyncio.gather(
                *[call_with_retry(step, order_id, wave_index, step_urls) for step in worker_steps]
            )
            for record in records:
                report.steps.append(record)
                state[record.step] = (record.succeeded, record.text)

    eligibility_ok, eligibility_text = state["check_eligibility"]
    refund_ok, refund_text = state["compute_refund_amount"]

    if not (eligibility_ok and refund_ok):
        e_word = "succeeded" if eligibility_ok else "failed"
        r_word = "succeeded" if refund_ok else "failed"
        report.decision = (
            f"ABORTED (partial state): check_eligibility {e_word}: {eligibility_text} | "
            f"compute_refund_amount {r_word}: {refund_text}"
        )
        return report

    eligible = parse_returnable(eligibility_text)
    refund_match = re.search(r"refund_amount=(\d+)", refund_text)
    refund_cents = int(refund_match.group(1)) if refund_match else None

    if eligible and refund_cents is not None:
        report.decision = f"APPROVED: refund {refund_cents} cents"
    else:
        report.decision = f"DENIED: {eligibility_text}"

    return report
