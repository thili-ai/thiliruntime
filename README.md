# thiliruntime

**A small, hackable multi-agent supervisor.** Three A2A agents — Order, Catalog, and a new Refund
Agent — plus a supervisor that holds the whole plan, calls the independent ones concurrently,
survives a worker failing mid-plan, and reports exactly what happened. It processes one real
task end to end: **"process order #79's return request."**

> ⚠️ Educational reference implementation, not production. Error handling, retries, and
> persistence are deliberately minimal — the point is to see every moving part of orchestrating
> several agents, not to harden it.

## 📚 Built lesson-by-lesson in a Learn Fast course

`thiliruntime` is the reference implementation for the **[Learn Fast](https://learnfast.thili.ai)
course "Orchestrate a Multi-Agent System."** The Order Agent and Catalog Agent are reused
unchanged from `thilia2a`, imported as a real dependency — this course builds the one piece that
course didn't need: a supervisor that owns sequencing when a task is bigger than any one worker.

| Lesson | You build | Files |
|---|---|---|
| 1 · From delegation to supervision | Nothing new yet — contrast `thilia2a`'s agent-initiated delegation with a supervisor that decides the whole sequence up front | — (recap only) |
| 2 · The plan as a dependency graph | `PLAN`, `waves()` | `thiliruntime/supervisor/plan.py` |
| 3 · The third worker | `RefundExecutor`, `build_refund_card`, `build_refund_app` | `thiliruntime/agents/refund_agent.py` |
| 4 · Wiring the supervisor | the first `process_return()`, calling each wave in order | `thiliruntime/supervisor/runtime.py` |
| 5 · Exploiting independence | `process_return()` generalized to run every step in a wave concurrently, measured against the sequential version | `thiliruntime/supervisor/runtime.py` |
| 6 · A worker fails mid-plan | `call_with_retry()` — fixed-count retry, then abort with partial state | `thiliruntime/supervisor/runtime.py` |
| 7 · The decision report | `StepRecord`, `DecisionReport`, `print_report()` | `thiliruntime/reports/decision_report.py` |
| 8 · Batch measurement | a ~30-case grading run, scored against independently-computed verdicts | `tests/batch_eval.py` |

Every lesson's `process_return()` is the same function gaining real capability — concurrency,
retry, reporting — not three different functions. By lesson 7 it's the version shipped here.

## Quickstart (no API key)

```bash
pip install -e ".[dev]"
python examples/quickstart.py
pytest tests/batch_eval.py -q
```

```python
import asyncio
import threading
import time

import uvicorn
from thilia2a import build_catalog_app, build_order_app

from thiliruntime import build_refund_app, print_report, process_return


async def main():
    threading.Thread(target=lambda: uvicorn.run(build_catalog_app(), port=8102, log_level="warning"), daemon=True).start()
    threading.Thread(target=lambda: uvicorn.run(build_order_app(), port=8101, log_level="warning"), daemon=True).start()
    threading.Thread(target=lambda: uvicorn.run(build_refund_app(), port=8105, log_level="warning"), daemon=True).start()
    time.sleep(2)

    step_urls = {
        "check_eligibility": "http://127.0.0.1:8101",
        "compute_refund_amount": "http://127.0.0.1:8105",
    }
    report = await process_return(79, step_urls)
    print_report(report)

asyncio.run(main())
```

## Why a supervisor, not a bigger delegation

`thilia2a` works when one agent can own the whole task and reach out when it hits a gap. Adding a
Refund Agent breaks that: it needs *two* upstream results (the order's price/tax, and whether the
return is even eligible), and none of the three workers can correctly own calling it — each would
have to acquire knowledge that belongs to a different worker's job. A **supervisor** holds the
plan before any worker runs instead, and contains none of their business logic. See lesson 1.

## Why the plan is a graph, not a list

`check_eligibility` and `compute_refund_amount` both need only the order id — nothing from each
other. `decide` needs both. Written as a list, that independence is invisible; written as the
dependency graph in `supervisor/plan.py`, `waves()` groups them into two waves instead of three,
and — proven, not asserted, in lesson 2 — the order the graph's keys happen to be *typed* in
carries no information at all. Only each step's own declared dependencies do.

## Why `compute_refund_amount` can succeed on an order that gets `DENIED`

`RefundExecutor` has no concept of eligibility, on purpose — an empty dependency list in the plan,
so lesson 5 has something genuinely independent to run concurrently. `process_return()`'s `decide`
step is what reads both results and discards the refund amount when the order isn't eligible.
`DecisionReport` shows this happening explicitly rather than hiding it — see lesson 7.

## Why failures are retried-or-aborted, never both treated the same

A timeout or connection error might clear up on a second try — `call_with_retry()` retries those,
a fixed number of times, with a short delay. A deliberate `TASK_STATE_FAILED` verdict won't change
on a second try, so it's returned immediately. When one of two concurrent steps fails and the
other doesn't, `process_return()` aborts with both halves of the partial state reported, never a
crash and never a guessed answer. See lesson 6.

## License

MIT © 2026 thili.ai
