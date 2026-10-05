"""The static task graph for "process a return," and the function that turns a dependency graph
into execution order.

Three nodes, not four: `check_eligibility` and `compute_refund_amount` each need only the order
id and nothing from each other; `decide` is the only node that needs both of their results. See
lesson 2.
"""

PLAN: dict[str, list[str]] = {
    "check_eligibility": [],
    "compute_refund_amount": [],
    "decide": ["check_eligibility", "compute_refund_amount"],
}


def waves(plan: dict[str, list[str]]) -> list[list[str]]:
    """Group a dependency graph into waves: every step in one wave has all its dependencies
    satisfied by earlier waves, and nothing in the same wave depends on anything else in it.

    Reasons only about each step's named dependencies, checked against a `set` of finished
    steps on every pass — the order the plan's own keys happen to be written in carries no
    information at all. See lesson 2 for a reordered-`PLAN` proof that this is actually true,
    not just asserted.
    """
    remaining = dict(plan)
    done: set[str] = set()
    result: list[list[str]] = []

    while remaining:
        ready = [step for step, deps in remaining.items() if all(d in done for d in deps)]
        if not ready:
            raise ValueError(f"no runnable step among {list(remaining)} - a cycle or a missing dependency")
        result.append(sorted(ready))
        done.update(ready)
        for step in ready:
            del remaining[step]

    return result
