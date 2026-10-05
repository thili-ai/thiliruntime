"""Keys-free quickstart: stand up all three agents and process two orders end to end, with a
full, auditable decision report for each.

Run: python examples/quickstart.py
"""
import asyncio
import threading
import time

import uvicorn
from thilia2a import build_catalog_app, build_order_app

from thiliruntime import build_refund_app, print_report, process_return


def _run(app, port):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


async def main():
    catalog_app = build_catalog_app()
    order_app = build_order_app()
    refund_app = build_refund_app()

    threading.Thread(target=_run, args=(catalog_app, 8102), daemon=True).start()
    threading.Thread(target=_run, args=(order_app, 8101), daemon=True).start()
    threading.Thread(target=_run, args=(refund_app, 8105), daemon=True).start()
    time.sleep(2)

    step_urls = {
        "check_eligibility": "http://127.0.0.1:8101",
        "compute_refund_amount": "http://127.0.0.1:8105",
    }

    for order_id in [79, 3]:
        report = await process_return(order_id, step_urls)
        print_report(report)
        print()


if __name__ == "__main__":
    asyncio.run(main())
