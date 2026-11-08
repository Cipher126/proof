from __future__ import annotations

import argparse
import json
import platform
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded local Proof API benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", default="docs/benchmarks/local-latest.json")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        tenant = client.post("/v1/demo/tenants", json={"name": "Bounded benchmark tenant"}).json()
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
        source = account("Benchmark source")
        destination = account("Benchmark destination")
        funding = client.post(
            f"/v1/tenants/{tenant_id}/journals",
            headers=headers,
            json={
                "reference": "benchmark/funding",
                "description": "Fictional bounded benchmark funds",
                "entries": [
                    {"account_id": system, "amount_minor": -args.requests},
                    {"account_id": source, "amount_minor": args.requests},
                ],
            },
        )
        funding.raise_for_status()

    thread_state = threading.local()

    def submit(index: int) -> tuple[int, float]:
        if not hasattr(thread_state, "client"):
            thread_state.client = httpx.Client(base_url=args.base_url, timeout=30)
        started = time.perf_counter()
        response = thread_state.client.post(
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

    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(submit, range(args.requests)))
    wall_seconds = time.perf_counter() - wall_started
    latencies = [latency for _, latency in results]
    statuses: dict[str, int] = {}
    for status, _ in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "local synthetic portfolio evidence; not a production capacity claim",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "base_url": args.base_url,
        },
        "workload": {"requests": args.requests, "concurrency": args.concurrency},
        "results": {
            "status_counts": statuses,
            "wall_seconds": round(wall_seconds, 4),
            "throughput_per_second": round(args.requests / wall_seconds, 2),
            "latency_ms": {
                "min": round(min(latencies), 2),
                "mean": round(statistics.mean(latencies), 2),
                "p50": round(percentile(latencies, 0.50), 2),
                "p95": round(percentile(latencies, 0.95), 2),
                "max": round(max(latencies), 2),
            },
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
