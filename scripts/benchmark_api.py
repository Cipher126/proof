from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import Engine, text


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = math.ceil(len(ordered) * fraction) - 1
    return ordered[index]


def run(base_url: str, requests: int, concurrency: int, layout: str, engine: Engine | None = None) -> dict:
    pairs = 1 if layout == "hot" else concurrency
    with httpx.Client(base_url=base_url, timeout=30) as client:
        created = client.post("/v1/demo/tenants", json={"name": "Bounded benchmark tenant"})
        created.raise_for_status()
        tenant = created.json()
        tenant_id = tenant["id"]
        headers = {"X-Tenant-ID": tenant_id}

        def account(name: str, allow_negative: bool = False) -> str:
            response = client.post(
                f"/v1/tenants/{tenant_id}/accounts",
                headers=headers,
                json={"name": name, "currency": "NGN", "allow_negative": allow_negative},
            )
            response.raise_for_status()
            return response.json()["id"]

        system = account("Benchmark system", True)
        accounts = [(account(f"Source {n}"), account(f"Destination {n}")) for n in range(pairs)]
        funding = client.post(
            f"/v1/tenants/{tenant_id}/journals",
            headers=headers,
            json={
                "reference": "benchmark/funding",
                "description": "Fictional bounded benchmark funds",
                "entries": [
                    {"account_id": system, "amount_minor": -requests},
                    *({"account_id": source, "amount_minor": len(range(n, requests, pairs))}
                      for n, (source, _) in enumerate(accounts)),
                ],
            },
        )
        funding.raise_for_status()

    def submit(client: httpx.Client, index: int) -> tuple[int, float]:
        source, destination = accounts[index % pairs]
        started = time.perf_counter()
        response = client.post(
            f"/v1/tenants/{tenant_id}/transfers",
            headers={
                "X-Tenant-ID": tenant_id,
                "Idempotency-Key": f"benchmark-key-{index:08d}",
            },
            json={
                "client_reference": f"benchmark-transfer-{index:08d}",
                "source_account_id": source,
                "destination_account_id": destination,
                "amount_minor": 1,
                "description": "Fictional bounded benchmark transfer",
            },
        )
        return response.status_code, (time.perf_counter() - started) * 1000

    stop = threading.Event()

    def sample_locks() -> list[int]:
        samples = []
        if engine is not None:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                while not stop.is_set():
                    samples.append(connection.scalar(text("""
                        SELECT count(*) FROM pg_stat_activity
                        WHERE application_name = 'proof-drill-api' AND wait_event_type = 'Lock'
                    """)))
                    stop.wait(0.01)
        return samples

    with httpx.Client(base_url=base_url, timeout=30) as client, ThreadPoolExecutor(
        max_workers=concurrency + 1,
    ) as executor:
        sampler = executor.submit(sample_locks)
        wall_started = time.perf_counter()
        try:
            def lane(n: int):
                return [submit(client, index) for index in range(n, requests, concurrency)]

            results = [result for lane_results in executor.map(lane, range(concurrency)) for result in lane_results]
        finally:
            stop.set()
        wall_seconds = time.perf_counter() - wall_started
        samples = sampler.result()
        for n, (source, destination) in enumerate(accounts):
            for account_id, expected in ((source, 0), (destination, len(range(n, requests, pairs)))):
                balance = client.get(f"/v1/tenants/{tenant_id}/accounts/{account_id}/balance", headers=headers)
                balance.raise_for_status()
                if balance.json()["balance_minor"] != expected:
                    raise RuntimeError(f"{layout} account balance differs from the expected result")
    latencies = [latency for _, latency in results]
    statuses: dict[str, int] = {}
    for status, _ in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    if statuses != {"201": requests}:
        raise RuntimeError(f"unexpected {layout} transfer status counts: {statuses}")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "local synthetic portfolio evidence; not a production capacity claim",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "workload": {"requests": requests, "concurrency": concurrency, "account_pairs": pairs, "layout": layout},
        "results": {
            "status_counts": statuses,
            "wall_seconds": round(wall_seconds, 4),
            "throughput_per_second": round(requests / wall_seconds, 2),
            "lock_samples": {
                "total": len(samples),
                "with_waiters": sum(sample > 0 for sample in samples),
                "peak_waiters": max(samples, default=0),
            } if engine is not None else None,
            "latency_ms": {
                "min": round(min(latencies), 2),
                "mean": round(statistics.mean(latencies), 2),
                "p50": round(percentile(latencies, 0.50), 2),
                "p95": round(percentile(latencies, 0.95), 2),
                "max": round(max(latencies), 2),
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare hot and spread accounts on a development-mode Proof instance")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", default="artifacts/benchmarks/latest.json")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= min(args.requests, 32) or args.requests > 10_000:
        parser.error("use 1–10,000 requests and concurrency between 1 and min(requests, 32)")
    report = {
        layout: run(args.base_url, args.requests, args.concurrency, layout)
        for layout in ("hot", "spread")
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
