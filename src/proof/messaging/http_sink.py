from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from proof.messaging.models import OutboxEvent
from proof.messaging.service import DeliveryFailure


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpSink:
    def __init__(self, url: str, token: str | None) -> None:
        target = urlsplit(url)
        is_local = target.scheme == "http" and target.hostname in {"127.0.0.1", "::1", "localhost"}
        if (target.scheme != "https" and not is_local) or not target.hostname or target.username:
            raise ValueError("outbox destination must use HTTPS or loopback HTTP")
        self.url = url
        self.token = token
        self.opener = build_opener(NoRedirect())

    def __call__(self, event: OutboxEvent) -> None:
        message = json.dumps({
            "id": str(event.id), "type": event.event_type, "occurred_at": event.occurred_at.isoformat(),
            "data": event.payload,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", "Idempotency-Key": str(event.id)}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.url, data=message, headers=headers, method="POST")
        try:
            with self.opener.open(request, timeout=3) as response:
                if not 200 <= response.status < 300:
                    raise DeliveryFailure(f"receiver returned HTTP {response.status}")
        except HTTPError as exc:
            exc.close()
            raise DeliveryFailure(f"receiver returned HTTP {exc.code}") from None
        except (URLError, OSError):
            raise DeliveryFailure("receiver connection failed") from None
