from __future__ import annotations

import argparse
from urllib.parse import urlsplit

import httpx


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(client: httpx.Client) -> tuple[str, str, str]:
    ready = client.get("/ready")
    ready.raise_for_status()
    check(ready.json()["status"] == "ready", "database is not ready")
    dashboard = client.get("/")
    dashboard.raise_for_status()
    check("Proof · Payment Operations" in dashboard.text, "dashboard bundle is missing")

    response = client.post("/v1/demo/scenarios/canonical")
    response.raise_for_status()
    scenario = response.json()
    check(scenario["fictional"], "expected fictional scenario")
    check(scenario["transfer_replayed"] and scenario["provider_duplicate"], "missing replay evidence")
    root = f"/v1/tenants/{scenario['tenant_id']}"
    headers = {"Authorization": f"Bearer {scenario['access_token']}"}

    def request(method: str, path: str) -> dict:
        response = client.request(method, root + path, headers=headers)
        response.raise_for_status()
        return response.json()

    transfer = scenario["transfer"]
    path = f"/operations/transfers/{transfer['id']}/timeline"
    check(client.get(root + path).status_code == 401, "tenant data is readable without a credential")
    timeline = request("GET", path)
    check(any(item["data"].get("classification") == "ignored_out_of_order"
              for item in timeline["items"]), "missing out-of-order evidence")

    statement_id = scenario["statement"]["id"]
    close = f"/demo/settlements/{statement_id}/close"
    check(client.post(root + close, headers=headers).status_code == 409, "an unresolved batch closed")
    finding = scenario["findings"][0]
    check(finding["kind"] == "amount_mismatch", "expected an amount mismatch")
    adjust = f"/demo/findings/{finding['id']}/adjust"
    resolution = request("POST", adjust)
    adjustment_id = resolution["adjustment_journal_id"]
    check(resolution["status"] == "resolved" and bool(adjustment_id), "adjustment did not resolve the finding")
    check(request("POST", adjust)["adjustment_journal_id"] == adjustment_id, "retry created a second adjustment")

    for journal_id in (transfer["journal_id"], adjustment_id):
        journal = request("GET", f"/journals/{journal_id}")
        check(sum(entry["amount_minor"] for entry in journal["entries"]) == 0, "journal did not balance")

    balance = request("GET", f"/accounts/{scenario['accounts']['customer']}/balance")
    check(balance["balance_minor"] == 2_475_000, "unexpected customer balance")
    check(request("POST", close)["status"] == "closed", "settlement batch did not close")
    return scenario["tenant_id"], transfer["id"], scenario["access_token"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one fictional Proof case and verify the full HTTP flow")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    loopback = url.hostname in {"localhost", "127.0.0.1", "::1"}
    if (url.scheme != "https" and not (url.scheme == "http" and loopback)) or not url.hostname or url.username:
        parser.error("use an HTTPS URL or a loopback HTTP URL")
    try:
        with httpx.Client(base_url=args.base_url, timeout=75, follow_redirects=False) as client:
            verify(client)
    except httpx.HTTPStatusError as exc:
        parser.exit(1, f"Proof smoke check failed at {exc.request.method} {exc.request.url.path} "
                       f"(HTTP {exc.response.status_code}).\n")
    except httpx.RequestError:
        parser.exit(1, "Proof smoke check failed to connect. Check the app URL and database readiness.\n")
    except (KeyError, IndexError, TypeError):
        parser.exit(1, "Proof smoke check received an unexpected response shape.\n")
    except ValueError as exc:
        parser.exit(1, f"Proof smoke check failed: {exc}.\n")
    print("Proof smoke check passed: replay evidence, balanced journals, one adjustment, and settlement closure.")


if __name__ == "__main__":
    main()
