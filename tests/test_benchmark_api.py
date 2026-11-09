import json
import runpy
import sys
from pathlib import Path

import httpx
import pytest


def test_failed_transfer_runs_both_layouts_and_saves_evidence(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_api.py"
    main = runpy.run_path(str(script))["main"]
    output = tmp_path / "benchmark.json"
    client = httpx.Client
    transfer_attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal transfer_attempts
        path = request.url.path
        if path.endswith("/transfers"):
            transfer_attempts += 1
            if transfer_attempts == 1:
                return httpx.Response(503)
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if path.endswith("/balance"):
            return httpx.Response(200, json={"balance_minor": 1})
        return httpx.Response(201, json={"id": "fixture"})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=transport, **kwargs))
    monkeypatch.setattr(sys, "argv", [
        str(script), "--requests", "1", "--concurrency", "1", "--output", str(output),
    ])
    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert transfer_attempts == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["hot"]["results"]["status_counts"] == {"503": 1}
    assert report["spread"]["results"]["transport_errors"] == 1
    for workload in report.values():
        assert "pair 0 source balance differs from the expected result" in workload["errors"]
        assert "expected 1 HTTP 201 transfers, received 0" in workload["errors"]
