"""A structured, human-auditable record of one `process_return()` run — which agent answered
which step, how many attempts it took, how long each one took, whether it succeeded, and the
final decision. See lesson 7.
"""
from dataclasses import dataclass, field


@dataclass
class StepRecord:
    step: str
    wave: int
    attempts: int
    succeeded: bool
    text: str
    duration: float


@dataclass
class DecisionReport:
    order_id: int
    steps: list[StepRecord] = field(default_factory=list)
    decision: str = ""


def print_report(report: DecisionReport) -> None:
    print(f"=== Decision Report: order {report.order_id} ===")
    current_wave = None
    for record in report.steps:
        if record.wave != current_wave:
            print(f"wave {record.wave}:")
            current_wave = record.wave
        mark = "SUCCEEDED" if record.succeeded else "FAILED"
        print(f"  {record.step:<22} [{record.attempts} attempt(s), {record.duration:.2f}s]  "
              f"{mark}  -> {record.text}")
    print(f"\nFINAL DECISION: {report.decision}")
