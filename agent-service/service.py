"""
CaseMentor agent core.

Owns: session state, debounce, timers, Agent SDK calls, TOS parsing, and the first of
two privacy strips. Knows nothing about Telegram — `main.py` wires the two together.

The privacy invariant: only `message` and exhibit images ever reach the candidate.
`private_eval` (hidden evaluation evidence) and `state` are dropped here, and dropped
again independently in `main.py`. Two gates on purpose. Breaking this leaks the answer
key mid-interview.
"""

import asyncio, json, os, re, time, uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

# ---------------------------------------------------------------- config
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "4"))
INACTIVITY_TIMEOUT_MIN = float(os.getenv("INACTIVITY_TIMEOUT_MIN", "10"))
HARD_STOP_MIN = float(os.getenv("HARD_STOP_MIN", "50"))
SESSIONS_ROOT = Path(os.getenv("SESSIONS_ROOT", "/var/lib/case-mentor/sessions"))
STATE_FILE = Path(os.getenv("STATE_FILE", "/var/lib/case-mentor/state.json"))

# Notion is optional. No token -> no MCP server, and the skill falls back to printing the
# log into the debrief. The target ids are deployment-specific, so they are injected into
# the prompt at runtime rather than hardcoded in SKILL.md — the skill ships publicly.
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATA_SOURCE_ID = os.getenv("NOTION_DATA_SOURCE_ID", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

# The SDK caps a SINGLE stream-json line at 1 MB by default, and parsing a case blows
# straight through that: reading an N-page PDF returns every page as an image in one
# tool_result (a 17-page case = 2.5 MB), and reading back a cropped exhibit PNG costs
# another ~1.3 MB. Base64 adds ~33% on top of the rendered images, so the PDF's size on
# disk is not the number that matters — 595 KB on disk became 2.5 MB on the wire.
# This is a parse-time guard against a runaway line, not a memory budget.
MAX_BUFFER_BYTES = int(float(os.getenv("AGENT_MAX_BUFFER_MB", "32")) * 1024 * 1024)

SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- state
@dataclass
class Session:
    chat_id: str
    workdir: str
    session_id: str | None = None      # Agent SDK session id, captured from ResultMessage
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    active: bool = True
    # debounce
    buffer: list[str] = field(default_factory=list)
    buffer_seq: int = 0


SESSIONS: dict[str, Session] = {}
LOCKS: dict[str, asyncio.Lock] = {}


def _persist() -> None:
    """Survive service restarts: session_id + workdir are all we need to resume."""
    data = {
        cid: {k: v for k, v in asdict(s).items() if k not in ("buffer", "buffer_seq")}
        for cid, s in SESSIONS.items()
    }
    STATE_FILE.write_text(json.dumps(data, indent=2))


def _restore() -> None:
    if not STATE_FILE.exists():
        return
    for cid, d in json.loads(STATE_FILE.read_text()).items():
        SESSIONS[cid] = Session(**d)


_restore()


def session_for(chat_id: str) -> Session:
    if chat_id not in SESSIONS or not SESSIONS[chat_id].active:
        wd = SESSIONS_ROOT / f"{chat_id}-{uuid.uuid4().hex[:8]}"
        wd.mkdir(parents=True, exist_ok=True)
        SESSIONS[chat_id] = Session(chat_id=chat_id, workdir=str(wd))
    return SESSIONS[chat_id]


def workdir_for(chat_id: str) -> Path:
    """Where an inbound PDF should land. Creates the session if there isn't one."""
    return Path(session_for(chat_id).workdir)


def _lock(chat_id: str) -> asyncio.Lock:
    return LOCKS.setdefault(chat_id, asyncio.Lock())


def active_count() -> int:
    return sum(1 for s in SESSIONS.values() if s.active)


# ---------------------------------------------------------------- agent call
def _notion_mcp() -> dict[str, Any]:
    """
    Notion over stdio, authenticated with an internal integration token.

    NOT the hosted https://mcp.notion.com/mcp endpoint — that is OAuth-only and its
    CDN returns 403 (error 1010) to a headless container, so the server attached but
    exposed no tools and closures silently fell back to "Notion unavailable".

    OPENAPI_MCP_HEADERS is set alongside NOTION_TOKEN because older releases of the
    server read only the former. No token -> no server, and the skill's fallback
    (print the log into the reply) takes over.
    """
    if not NOTION_TOKEN:
        return {}
    return {
        "notion": {
            "type": "stdio",
            "command": "notion-mcp-server",
            "args": [],
            "env": {
                "NOTION_TOKEN": NOTION_TOKEN,
                "OPENAPI_MCP_HEADERS": json.dumps({
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                }),
            },
        }
    }


def _options(sess: Session) -> ClaudeAgentOptions:
    """
    The skill is baked into the image at $HOME/.claude/skills/case-mentor (see the
    entrypoint), so the agent auto-discovers it without mounting the host's config.
    """
    kwargs: dict[str, Any] = dict(
        cwd=sess.workdir,
        permission_mode="bypassPermissions",   # headless; no human to approve tool calls
        mcp_servers=_notion_mcp(),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Grep", "mcp__notion"],
        max_buffer_size=MAX_BUFFER_BYTES,
    )
    if sess.session_id:
        kwargs["resume"] = sess.session_id
    return ClaudeAgentOptions(**kwargs)


async def _run_agent(sess: Session, prompt: str) -> str:
    """Run one turn. Captures/refreshes the session id so the next turn resumes."""
    final_text = ""
    async for message in query(prompt=prompt, options=_options(sess)):
        if isinstance(message, ResultMessage):
            sess.session_id = message.session_id or sess.session_id
            if getattr(message, "subtype", "") == "success":
                final_text = message.result or ""
            else:
                raise RuntimeError(f"agent run failed: {message.subtype}")
    _persist()
    # Keep this. Without it, every agent-side failure surfaced as a generic parse error
    # and cost hours — including an exhausted API credit balance that was invisible.
    print(f"[agent raw output] {final_text[:2000]!r}", flush=True)
    return final_text


# ---------------------------------------------------------------- TOS parsing
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _parse_tos(raw: str) -> dict:
    """
    The skill contract is raw JSON. Be tolerant of stray fences, but never
    invent fields: a malformed turn must surface, not silently pass through.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
    m = _JSON_BLOCK.search(text)
    if not m:
        raise ValueError("no JSON object in agent output")
    tos = json.loads(m.group(0))
    if "message" not in tos:
        raise ValueError("TOS missing 'message'")
    return tos


def _exhibit_paths(sess: Session, paths: list[str]) -> list[str]:
    """
    Resolve exhibit files to absolute paths inside the session workdir.

    Confined to the workdir on purpose: the agent supplies these strings, and this
    service now uploads whatever they point at straight to Telegram. Without the
    containment check, `../../etc/passwd` would be deliverable.
    """
    root = Path(sess.workdir).resolve()
    out: list[str] = []
    for p in paths or []:
        candidate = Path(p)
        abs_p = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not abs_p.is_file():
            continue
        if root not in abs_p.parents and abs_p.parent != root:
            print(f"[exhibit] refusing path outside workdir: {p}", flush=True)
            continue
        out.append(str(abs_p))
    return out


# Fields the candidate must never see, under any circumstance.
FORBIDDEN_TOS_FIELDS = ("private_eval", "state", "sub_state", "move", "advance")


def _reply(sess: Session, tos: dict) -> dict:
    """
    Privacy gate 1 of 2: rebuild the outbound payload from scratch.

    Allow-list, never blacklist — a new TOS field added to the skill later is invisible
    to the candidate by default rather than leaking until someone notices.
    """
    if tos.get("session_over"):
        sess.active = False
    _persist()
    return {
        "chat_id": sess.chat_id,
        "message": str(tos["message"]),
        "photos": _exhibit_paths(sess, tos.get("exhibit_files", [])),
        "session_over": bool(tos.get("session_over")),
    }


def _runtime_context() -> str:
    """
    One line appended to every turn telling the skill where the case log goes.

    Appended per turn rather than announced once at /case: it costs ~100 characters and
    removes any dependence on the agent still remembering it 40 minutes later, at closure,
    which is the only moment it is used.
    """
    if not (NOTION_TOKEN and (NOTION_DATA_SOURCE_ID or NOTION_DATABASE_ID)):
        return "\nRuntime context: Notion logging is DISABLED. Skip the Notion case log."
    return (
        "\nRuntime context: Notion logging ENABLED. Case Log data_source_id="
        f"{NOTION_DATA_SOURCE_ID or '(none)'}, database_id={NOTION_DATABASE_ID or '(none)'}."
    )


# ---------------------------------------------------------------- turns
async def run_turn(chat_id: str, text: str, uploaded: list[str]) -> dict | None:
    """
    One candidate turn. Returns a sanitized reply, or None if debounced away.

    `uploaded` are filenames already written into the session workdir by the caller.
    """
    sess = session_for(chat_id)
    sess.last_activity = time.time()

    # ---- debounce: rapid-fire Telegram messages collapse into one turn
    sess.buffer.append(text)
    sess.buffer_seq += 1
    my_seq = sess.buffer_seq
    if not uploaded:                               # never delay a case upload
        await asyncio.sleep(DEBOUNCE_SECONDS)
        if sess.buffer_seq != my_seq:              # a newer message superseded us
            return None

    async with _lock(chat_id):
        merged = "\n".join(t for t in sess.buffer if t).strip()
        sess.buffer.clear()

        if uploaded:
            prompt = (
                f"The candidate sent the /case command with an uploaded case PDF.\n"
                f"Files in your working directory: {', '.join(uploaded)}\n"
                f"{'Accompanying message: ' + merged if merged else ''}\n"
                f"Begin the case per the case-mentor skill."
            )
        elif merged.startswith("/"):
            # Never hand a leading slash to the CLI — it intercepts it as its own command
            # and the skill never sees the turn. Describe it in prose instead.
            prompt = (
                f"The candidate sent the command: {merged}\n"
                f"(Treat this as a candidate command per the case-mentor skill.)"
            )
        else:
            prompt = merged or "(empty message)"

        prompt += _runtime_context()

        try:
            tos = _parse_tos(await _run_agent(sess, prompt))
        except Exception as e:                     # fail visibly, never silently
            print(f"[turn] error for {chat_id}: {e}", flush=True)
            sess.active = False
            _persist()
            return {
                "chat_id": chat_id,
                "message": "Something went wrong on my end. Send /case with the PDF to start again.",
                "photos": [],
                "session_over": True,
            }
        return _reply(sess, tos)


async def due_closures() -> list[dict]:
    """Closure turns for any session past its inactivity or hard-stop deadline."""
    now = time.time()
    out: list[dict] = []
    for sess in list(SESSIONS.values()):
        if not sess.active or not sess.session_id:
            continue
        if now - sess.last_activity >= INACTIVITY_TIMEOUT_MIN * 60:
            event = '{"event": "timeout_inactivity"}'
        elif now - sess.started_at >= HARD_STOP_MIN * 60:
            event = '{"event": "timeout_hard"}'
        else:
            continue
        async with _lock(sess.chat_id):
            try:
                tos = _parse_tos(await _run_agent(sess, event + _runtime_context()))
                out.append(_reply(sess, tos))
            except Exception as e:
                print(f"[timers] closure failed for {sess.chat_id}: {e}", flush=True)
                sess.active = False
                _persist()
    return out
