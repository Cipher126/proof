from __future__ import annotations

import argparse
import os
import json
import time
import uuid

from sqlalchemy.exc import OperationalError

from proof.db import SessionLocal
from proof.messaging.http_sink import HttpSink
from proof.messaging.service import dispatch_batch, requeue_dead_letter
from proof.operations.telemetry import configure_tracing
from proof.payments.service import expire_due_payment


def run() -> None:
    parser = argparse.ArgumentParser(description="Dispatch Proof transactional outbox events")
    parser.add_argument("--once", action="store_true", help="dispatch one batch and exit")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--requeue", type=uuid.UUID, help="requeue one dead-lettered event")
    parser.add_argument("--tenant", type=uuid.UUID)
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.requeue:
        if args.tenant is None or not args.reason or not args.reason.strip():
            parser.error("--requeue requires --tenant and --reason")
        with SessionLocal() as session:
            requeue_dead_letter(session, args.tenant, args.requeue, actor="worker-cli", reason=args.reason)
        return
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    url = os.getenv("PROOF_OUTBOX_URL")
    deliver = HttpSink(url, os.getenv("PROOF_OUTBOX_TOKEN")) if url else None
    configure_tracing("proof-worker")
    failures = {
        value.strip()
        for value in os.getenv("PROOF_OUTBOX_FAIL_EVENT_TYPES", "").split(",")
        if value.strip()
    }
    while True:
        try:
            for _ in range(min(args.batch_size, 20)):
                with SessionLocal() as session:
                    if not expire_due_payment(session):
                        break
            for _ in range(args.batch_size if deliver else 1):
                with SessionLocal() as session:
                    result = dispatch_batch(
                        session, batch_size=1 if deliver else args.batch_size,
                        fail_event_types=failures, deliver=deliver,
                    )
                if result["processed"] == 0:
                    break
                print(json.dumps({"event": "outbox.dispatched", **result}), flush=True)
        except OperationalError:
            print(json.dumps({"event": "outbox.database_unavailable"}), flush=True)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            return
        time.sleep(1)
