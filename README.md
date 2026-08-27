# CaseMentor

A mock case interviewer that runs in Telegram.

You send it a consulting case PDF. It reads the case, then interviews you on it the way an MBB partner would — asking one question at a time, pushing back when your structure is thin, making you do the math, handing you exhibits as images to read. It scores you silently the whole way through, and gives you evaluation at the end.

Built for drilling framework structure or full cases.

## What it does

- **Parses the case** — splits what you are allowed to know from what only the interviewer knows, and crops exhibits out as images
- **Runs a state-gated interview** — intro, then one question at a time, no skipping ahead and no answering questions from later in the case
- **Withholds info until you ask for it** — casebooks mark facts as "share if asked", and failing to ask counts against you
- **Hints on a ladder** — a probe, then a narrower probe, then one real hint, then the answer, logged as unassisted
- **Grades at the end** — three dimensions on a four-point scale, from evidence collected across the whole interview, with a written debrief
- **Logs the session to Notion** — optional

Type `/quit` any time to end early and be graded on what you completed. Session automatically ends after going silent for ten minutes.

## What it's built on

- [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) — runs the interviewer
- [Claude Code](https://claude.com/claude-code) — the agent runtime, and the skill format
- [Telegram Bot API](https://core.telegram.org/bots/api) — the chat interface
- [Docker Compose](https://docs.docker.com/compose/) — one container, one command
- [poppler](https://poppler.freedesktop.org/) — crops exhibit images out of the PDF
- [Notion MCP server](https://github.com/makenotion/notion-mcp-server) — optional case log

Nothing is exposed to the internet. The container polls Telegram outbound, so there is no
webhook, no tunnel, no domain, and no open port.

## Before you start

This is self-hosted. So you need Docker, a Telegram account, and an Anthropic API key.

**This costs money.** Every interview is billed to your own Anthropic key — roughly **$1.50–$3 per session**. There is no free tier and no shared key.

## Setup

1. **Getting API keys.** Have all of these on hand before you start — setup asks for them in one pass.

   - **Telegram bot token** — message [@BotFather](https://t.me/BotFather) → send `/newbot` → follow the prompts → store API key locally.

   - **Anthropic API key** — go to [console.anthropic.com](https://console.anthropic.com) → **API keys** → **Create key** → store API key locally.

   - **Notion access token and database URL** *(optional — skip it and the debrief still arrives in Telegram, just nowhere else)* — create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations) → copy its **Access token** → in Notion, create a new empty database as a full page, leaving the columns alone since setup creates them for you → open it → **⋯** → **Connections** → add your integration → copy the page URL from your browser's address bar → store API key locally.

2. Clone and run setup:

   ```bash
   git clone https://github.com/amdqiao/case-mentor.git case-mentor
   cd case-mentor
   ./setup.sh
   ```

3. Start it:

   ```bash
   docker compose up -d
   ```

4. Confirm it started:

   ```bash
   docker compose logs
   ```

   Expect `[startup] bot @yourbot | 1 allowed chat id(s)`.

5. In Telegram, send your bot `/case` with a case PDF attached.

## Common commands

```bash
docker compose logs -f          # follow the logs
docker compose restart          # restart
docker compose down             # stop
docker compose up -d --build    # rebuild after changing anything
curl -s localhost:8080/health   # check status
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bot ignores you | Your chat id is not in `TELEGRAM_ALLOWED_CHAT_IDS`. Rerun `./setup.sh` |
| `getUpdates failed: 409 Conflict` | A webhook is registered on this bot elsewhere. Stop the other deployment |
| `Credit balance is too low` | Get more credit at [console.anthropic.com](https://console.anthropic.com) |
| `JSON message exceeded maximum buffer size` | Raise `AGENT_MAX_BUFFER_MB` in `.env`, then rebuild |
| Debrief says the Notion write failed | The database is not shared with your integration — see the Notion bullet in step 1, then rerun `./setup.sh` |
| Nothing in the logs at all | `docker compose ps` — the container may have exited. Check `.env` exists |

## Configuration

All settings live in `.env`. See [`.env.example`](.env.example) for the full list with
defaults — timeouts, debounce, model, and upload limits.

## Customising the interviewer

The interviewer's persona, questioning rules, hint ladder, and grading rubric are plain
Markdown in [`skill/case-mentor/`](skill/case-mentor/). Edit them, then:

```bash
docker compose up -d --build
```

- `SKILL.md` — persona, state machine, output contract, move policy
- `references/cbs-parsing.md` — how a case PDF is turned into a structured case
- `references/rubric.md` — grading anchors, the spike rule, debrief format

## A note on case PDFs

None are included. Case material from RocketBlocks, casebooks, and firm prep sites is
copyrighted — bring your own.

## License

Dual-licensed under either of [MIT](LICENSE-MIT) or [Apache 2.0](LICENSE-APACHE), at your
option.
