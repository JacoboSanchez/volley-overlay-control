"""Pure-ASGI request-body size cap.

Route-level guards like the icon uploads' ``_reject_oversized_body`` key
off the ``Content-Length`` header, which a chunked-transfer client simply
omits — and by the time a handler's streamed read runs, Starlette's
multipart parser has already consumed (and spooled to disk) the whole
body during ``File(...)`` dependency resolution. The only place a hard
limit can actually bound the resource spend is the ASGI layer, before
any parsing happens.

The middleware fast-fails a declared oversized ``Content-Length`` and
otherwise counts ``http.request`` bytes as the app pulls them, replying
413 and refusing to deliver further body once the cap is crossed. The
cap is deliberately generous — a global backstop against abuse, not a
per-route policy; tighter per-route checks (which produce friendlier
errors earlier) stay where they are.
"""

import json
import logging

from app.constants import REQUEST_MAX_BODY_BYTES

logger = logging.getLogger(__name__)


class BodySizeLimitMiddleware:
    """Reject request bodies larger than *max_bytes* with a 413."""

    def __init__(self, app, max_bytes: int = REQUEST_MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await self._send_413(send)
                    return
            except ValueError:
                pass  # malformed header — let the framework reject it

        state = {"received": 0, "response_started": False, "tripped": False}

        async def limited_receive():
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > self.max_bytes:
                    state["tripped"] = True
                    logger.warning(
                        "Request body exceeded REQUEST_MAX_BODY_BYTES (%d) for %s %s",
                        self.max_bytes, scope.get("method"), scope.get("path"),
                    )
                    # Present the truncated stream as complete; the app sees
                    # a short body and we race it with the 413 below.
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                if state["tripped"]:
                    # Replace whatever the app produced from the truncated
                    # body with the 413.
                    await self._send_413(send)
                    raise _ResponseSent()
                state["response_started"] = True
            # A response that started before the cap tripped (streaming
            # handler) passes through untouched — too late to replace it.
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _ResponseSent:
            pass

    @staticmethod
    async def _send_413(send):
        body = json.dumps({"detail": "Request body is too large."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


class _ResponseSent(Exception):
    """Internal control flow: the 413 was already written."""
