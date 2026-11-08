from __future__ import annotations

import argparse
import os

from proof.db import SessionLocal
from proof.messaging.service import dispatch_batch


def run() -> None:
    parser = argparse.ArgumentParser(description="Dispatch Proof transactional outbox events")
    parser.add_argument("--once", action="store_true", help="dispatch one batch and exit")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not args.once:
        parser.error("only --once mode is available in the current portfolio milestone")
    failures = {
        value.strip()
        for value in os.getenv("PROOF_OUTBOX_FAIL_EVENT_TYPES", "").split(",")
        if value.strip()
    }
    with SessionLocal() as session:
        print(dispatch_batch(session, batch_size=args.batch_size, fail_event_types=failures))
