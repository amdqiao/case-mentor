"""
Telegram Bot API client and long-poll loop.

Replaces the n8n relay. Long polling needs no webhook, no public URL, and no tunnel:
the container reaches out to Telegram rather than being reached, so a laptop behind NAT
works the same as a server.

This module owns Telegram specifics and nothing else. It never imports agent internals —
it calls back into whatever handler `poll_forever` is given.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

# Telegram hard-caps a text message at 4096 characters. 4000 leaves headroom.
CHUNK_LIMIT = 4000

# A case PDF is a few hundred KB. The Bot API refuses to serve files over 20 MB anyway.
MAX_PDF_BYTES = int(float(os.getenv("MAX_PDF_MB", "20")) * 1024 * 1024)

MEDIA_REJECTION = (
    "I can only work from a case PDF. Send the case as a PDF document "
    "and I'll take it from there."
)


def allowed_chat_ids() -> set[str]:
    """
    Empty set means the bot answers nobody — deliberately fail closed.

    Self-hosting hides the server, not the bot: Telegram usernames are searchable, so an
    open bot lets a stranger run case interviews on the host's API key. This is the only
    thing standing between the bot and someone else's bill.
    """
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


class Telegram:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self._token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        self._api = f"https://api.telegram.org/bot{self._token}"
        self._files = f"https://api.telegram.org/file/bot{self._token}"
        # Long polling holds a request open for `timeout` seconds; the read timeout must
        # outlast it, or every poll dies client-side instead of returning an empty list.
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0))

    async def aclose(self) -> None:
        await self._http.aclose()

    def scrub(self, text: Any) -> str:
        """
        The bot token is part of every API URL, so httpx errors quote it verbatim.
        Everything logged from this module goes through here first.
        """
        return str(text).replace(self._token, "<bot-token>")

    async def _call(self, method: str, **params: Any) -> Any:
        r = await self._http.post(f"{self._api}/{method}", json=params)
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(f"telegram {method} failed: {self.scrub(body)}")
        return body.get("result")

    async def get_me(self) -> dict:
        return await self._call("getMe")

    async def delete_webhook(self) -> None:
        """
        Long polling and webhooks are mutually exclusive: with a webhook registered,
        getUpdates returns 409 forever. Clearing it at startup makes migrating from a
        webhook deployment work without the operator having to know that.

        Pending updates are kept, not dropped — a message sent during the switchover
        should still get answered.
        """
        await self._call("deleteWebhook", drop_pending_updates=False)

    async def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict]:
        return await self._call(
            "getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"]
        )

    async def send_message(self, chat_id: str, text: str) -> None:
        """Plain text on purpose: Markdown parsing eats the underscores in sub_state ids."""
        if not text.strip():
            return                                  # Telegram rejects an empty message
        for i in range(0, len(text), CHUNK_LIMIT):
            await self._call("sendMessage", chat_id=chat_id, text=text[i : i + CHUNK_LIMIT])

    async def send_photo(self, chat_id: str, path: Path) -> None:
        """
        Upload the bytes directly rather than handing Telegram a URL to fetch.

        The URL approach needed a publicly reachable service and minted in-memory tokens
        that 404'd after any restart. Multipart upload has neither problem.
        """
        with path.open("rb") as fh:
            r = await self._http.post(
                f"{self._api}/sendPhoto",
                data={"chat_id": chat_id},
                files={"photo": (path.name, fh, "application/octet-stream")},
            )
        r.raise_for_status()
        if not r.json().get("ok"):
            raise RuntimeError(f"telegram sendPhoto failed: {self.scrub(r.text[:200])}")

    async def download(self, file_id: str, dest: Path) -> int:
        """Stream to disk, aborting past MAX_PDF_BYTES so a bad upload can't fill the volume."""
        info = await self._call("getFile", file_id=file_id)
        written = 0
        async with self._http.stream("GET", f"{self._files}/{info['file_path']}") as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_bytes():
                    written += len(chunk)
                    if written > MAX_PDF_BYTES:
                        fh.close()
                        dest.unlink(missing_ok=True)
                        raise ValueError(f"PDF exceeds MAX_PDF_MB ({MAX_PDF_BYTES} bytes)")
                    fh.write(chunk)
        return written


def classify(message: dict) -> tuple[str, Any]:
    """
    ('pdf', document) | ('text', str) | ('unsupported', None) | ('ignore', None)

    Anything that is not a PDF or text is refused rather than guessed at: reading the
    exhibit is part of the skill being tested, so a photo of a case is not a substitute.
    """
    doc = message.get("document")
    if doc:
        name = (doc.get("file_name") or "").lower()
        if doc.get("mime_type") == "application/pdf" or name.endswith(".pdf"):
            return "pdf", doc
        return "unsupported", None
    for key in ("photo", "video", "audio", "voice", "sticker", "video_note", "animation"):
        if message.get(key):
            return "unsupported", None
    text = (message.get("text") or message.get("caption") or "").strip()
    return ("text", text) if text else ("ignore", None)


# handler(chat_id, text, documents) — documents are raw Telegram document objects; the
# handler owns the session workdir, so it decides where they land.
Handler = Callable[[str, str, list[dict]], Awaitable[None]]


async def poll_forever(tg: Telegram, handle: Handler, stop: asyncio.Event) -> None:
    """
    One consumer per bot token — Telegram rejects concurrent getUpdates on the same
    token, so never run two instances of this service against one bot.
    """
    allowed = allowed_chat_ids()
    if not allowed:
        print("[telegram] TELEGRAM_ALLOWED_CHAT_IDS empty — ignoring all messages", flush=True)

    offset: int | None = None
    while not stop.is_set():
        try:
            updates = await tg.get_updates(offset)
        except Exception as e:                      # transient network / 5xx
            print(f"[telegram] getUpdates failed: {tg.scrub(e)}", flush=True)
            await asyncio.sleep(3)
            continue

        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message")
            if not msg:
                continue
            chat_id = str(msg["chat"]["id"])
            if chat_id not in allowed:
                print(f"[telegram] ignored message from chat_id {chat_id}", flush=True)
                continue

            kind, payload = classify(msg)
            if kind == "ignore":
                continue
            if kind == "unsupported":
                await tg.send_message(chat_id, MEDIA_REJECTION)
                continue

            try:
                if kind == "pdf":
                    await handle(chat_id, (msg.get("caption") or "").strip(), [payload])
                else:
                    await handle(chat_id, payload, [])
            except Exception as e:
                print(f"[telegram] handler error for {chat_id}: {tg.scrub(e)}", flush=True)
