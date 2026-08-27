"""
CaseMentor entrypoint: Telegram long-poll loop + timeout ticker + a health endpoint.

Replaces the n8n workflow. Everything n8n used to do — normalise the update, reject
media, attach the PDF, call the agent, sanitise, chunk, send text, send exhibits, poll
for timeouts every minute — happens here.
"""

import asyncio
import contextlib
import os
from pathlib import Path

from fastapi import FastAPI

import service
import telegram

TIMER_TICK_SECONDS = float(os.getenv("TIMER_TICK_SECONDS", "60"))

_stop = asyncio.Event()
_tasks: list[asyncio.Task] = []
_tg: telegram.Telegram | None = None


# ---------------------------------------------------------------- privacy gate 2 of 2
def outbound(reply: dict) -> tuple[str, list[Path]]:
    """
    Second, independent strip before anything leaves for Telegram.

    service._reply() already allow-listed these fields. This repeats the work from the
    raw dict rather than trusting it, so a regression in one layer cannot leak evaluation
    evidence on its own — the same reason the n8n build sanitised in two places.
    """
    leaked = [k for k in service.FORBIDDEN_TOS_FIELDS if k in reply]
    if leaked:
        raise AssertionError(f"privacy gate: forbidden field(s) in outbound reply: {leaked}")
    text = str(reply.get("message", "")).strip()
    photos = [Path(p) for p in reply.get("photos", []) if Path(p).is_file()]
    return text, photos


async def deliver(chat_id: str, reply: dict | None) -> None:
    if reply is None:                               # debounced away — send nothing
        return
    text, photos = outbound(reply)
    await _tg.send_message(chat_id, text)
    for p in photos:
        try:
            await _tg.send_photo(chat_id, p)
        except Exception as e:
            print(f"[deliver] exhibit {p.name} failed: {_tg.scrub(e)}", flush=True)


# ---------------------------------------------------------------- inbound
async def handle(chat_id: str, text: str, documents: list[dict]) -> None:
    uploaded: list[str] = []
    for doc in documents:
        # Take only the basename: the filename is attacker-controlled and would otherwise
        # let "../../x" escape the session workdir.
        name = Path(doc.get("file_name") or "case.pdf").name
        dest = service.workdir_for(chat_id) / name
        try:
            size = await _tg.download(doc["file_id"], dest)
            print(f"[upload] {name} ({size} bytes) -> {dest}", flush=True)
            uploaded.append(name)
        except ValueError as e:                     # too large
            await _tg.send_message(chat_id, f"That PDF is too large. {e}")
            return
        except Exception as e:
            print(f"[upload] failed: {_tg.scrub(e)}", flush=True)
            await _tg.send_message(chat_id, "I couldn't download that file. Try sending it again.")
            return

    await deliver(chat_id, await service.run_turn(chat_id, text, uploaded))


# ---------------------------------------------------------------- loops
async def timer_loop() -> None:
    """Replaces n8n's every-minute schedule trigger."""
    while not _stop.is_set():
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(_stop.wait(), timeout=TIMER_TICK_SECONDS)
        if _stop.is_set():
            return
        try:
            for reply in await service.due_closures():
                await deliver(reply["chat_id"], reply)
        except Exception as e:
            print(f"[timers] tick failed: {e}", flush=True)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _tg
    _tg = telegram.Telegram()
    await _tg.delete_webhook()          # a stale webhook makes getUpdates 409 forever
    me = await _tg.get_me()
    allowed = telegram.allowed_chat_ids()
    print(f"[startup] bot @{me.get('username')} | {len(allowed)} allowed chat id(s)", flush=True)
    _tasks.append(asyncio.create_task(telegram.poll_forever(_tg, handle, _stop)))
    _tasks.append(asyncio.create_task(timer_loop()))
    try:
        yield
    finally:
        _stop.set()
        for t in _tasks:
            t.cancel()
        await asyncio.gather(*_tasks, return_exceptions=True)
        await _tg.aclose()


app = FastAPI(title="CaseMentor", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "sessions_active": service.active_count(),
        "allowed_chat_ids": len(telegram.allowed_chat_ids()),
        "notion": bool(service.NOTION_TOKEN),
        "debounce_s": service.DEBOUNCE_SECONDS,
        "inactivity_min": service.INACTIVITY_TIMEOUT_MIN,
        "hard_stop_min": service.HARD_STOP_MIN,
    }
