#!/usr/bin/env bash
# CaseMentor setup. Prompts for credentials, validates them, writes .env.
# Nothing here is sent anywhere except to Anthropic, Telegram, and Notion themselves.
set -euo pipefail

cd "$(dirname "$0")"
ENV_FILE=".env"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
warn() { printf "\033[33m%s\033[0m\n" "$1"; }
die()  { printf "\033[31m%s\033[0m\n" "$1" >&2; exit 1; }

command -v curl >/dev/null || die "curl is required."
command -v docker >/dev/null || warn "docker not found — you'll need it to run CaseMentor."

echo
bold "CaseMentor setup"
echo "Three things are required: an Anthropic API key, a Telegram bot token, and your"
echo "Telegram chat id. Notion is optional and can be skipped."
echo

if [ -f "$ENV_FILE" ]; then
  warn "$ENV_FILE already exists."
  read -r -p "Overwrite it? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || die "Keeping the existing $ENV_FILE. Nothing changed."
fi

# ---------------------------------------------------------------- Anthropic
bold "1. Anthropic API key"
echo "   Create one at https://console.anthropic.com -> API keys"
echo "   Every interview is billed to this key (roughly \$1.50-\$3 per session)."
read -r -s -p "   ANTHROPIC_API_KEY: " ANTHROPIC_API_KEY; echo
[ -n "$ANTHROPIC_API_KEY" ] || die "An API key is required."

# ---------------------------------------------------------------- Telegram
echo
bold "2. Telegram bot token"
echo "   In Telegram, message @BotFather and send /newbot. It replies with a token."
read -r -s -p "   TELEGRAM_BOT_TOKEN: " TELEGRAM_BOT_TOKEN; echo
[ -n "$TELEGRAM_BOT_TOKEN" ] || die "A bot token is required."

echo "   Checking the token..."
BOT_JSON=$(curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" || true)
echo "$BOT_JSON" | grep -q '"ok":true' || die "Telegram rejected that token. Check it and rerun."
BOT_NAME=$(echo "$BOT_JSON" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')
echo "   OK — bot is @${BOT_NAME}"

# ---------------------------------------------------------------- chat id
echo
bold "3. Your Telegram chat id"
echo "   Only ids listed here can use the bot. This is what stops a stranger who finds"
echo "   your bot from running interviews on your API key."
echo
echo "   a) detect it — open Telegram, send any message to @${BOT_NAME}, then continue"
echo "   b) enter it manually (get it from @userinfobot)"
read -r -p "   Choose [a/b]: " choice

CHAT_IDS=""
if [[ "$choice" =~ ^[Aa]$ ]]; then
  read -r -p "   Send a message to @${BOT_NAME}, then press Enter... " _
  UPDATES=$(curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" || true)
  CHAT_IDS=$(echo "$UPDATES" | tr '{' '\n' | sed -n 's/.*"chat":.*"id":\(-\?[0-9]*\).*/\1/p' \
             | sort -u | paste -sd, -)
  # Fall back to a looser match if the message shape differs.
  [ -n "$CHAT_IDS" ] || CHAT_IDS=$(echo "$UPDATES" | sed -n 's/.*"chat":{"id":\(-\?[0-9]*\).*/\1/p' \
             | sort -u | paste -sd, -)
  if [ -n "$CHAT_IDS" ]; then
    echo "   Detected: $CHAT_IDS"
  else
    warn "   Couldn't detect one. Enter it manually."
  fi
fi

if [ -z "$CHAT_IDS" ]; then
  read -r -p "   TELEGRAM_ALLOWED_CHAT_IDS (comma-separated): " CHAT_IDS
fi
[ -n "$CHAT_IDS" ] || die "At least one chat id is required — the bot refuses everyone otherwise."

# ---------------------------------------------------------------- Notion
echo
bold "4. Notion case log (optional)"
echo "   Writes one row per completed interview. Skip it and the debrief still arrives"
echo "   in Telegram — nothing else changes."
read -r -p "   Enable Notion? [y/N] " use_notion

NOTION_TOKEN=""; NOTION_DATABASE_ID=""; NOTION_DATA_SOURCE_ID=""
if [[ "$use_notion" =~ ^[Yy]$ ]]; then
  if ! command -v python3 >/dev/null; then
    warn "   python3 is needed to set up the Notion database automatically."
    warn "   Continuing with Notion DISABLED."
    use_notion="n"
  fi
fi

if [[ "$use_notion" =~ ^[Yy]$ ]]; then
  echo
  echo "   a) Create an integration at https://www.notion.so/my-integrations"
  echo "      and copy its Internal Integration Secret."
  echo "   b) In Notion, create a new EMPTY database (a full page, not inline)."
  echo "      Do not add any columns — they get created for you."
  echo "   c) Open it, click ... -> Connections, and add your integration."
  echo
  read -r -s -p "   NOTION_TOKEN: " NOTION_TOKEN; echo
  read -r -p "   Case Log database URL: " NOTION_DB_URL

  echo "   Setting up the database..."
  if PROV=$(python3 scripts/notion_provision.py "$NOTION_TOKEN" "$NOTION_DB_URL"); then
    NOTION_DATA_SOURCE_ID=$(echo "$PROV" | awk '{print $1}')
    NOTION_DATABASE_ID=$(echo "$PROV" | awk '{print $2}')
    echo "   OK — Notion case log ready."
  else
    warn "   Continuing with Notion DISABLED — fix the above and rerun setup."
    NOTION_TOKEN=""; NOTION_DATABASE_ID=""; NOTION_DATA_SOURCE_ID=""
  fi
fi

# ---------------------------------------------------------------- write
cat > "$ENV_FILE" <<EOF
# Written by setup.sh. Never commit this file.
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ANTHROPIC_MODEL=claude-sonnet-5

TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_ALLOWED_CHAT_IDS=${CHAT_IDS}

NOTION_TOKEN=${NOTION_TOKEN}
NOTION_DATA_SOURCE_ID=${NOTION_DATA_SOURCE_ID}
NOTION_DATABASE_ID=${NOTION_DATABASE_ID}

DEBOUNCE_SECONDS=4
INACTIVITY_TIMEOUT_MIN=10
HARD_STOP_MIN=50
AGENT_MAX_BUFFER_MB=32
MAX_PDF_MB=20
EOF
chmod 600 "$ENV_FILE"

echo
bold "Done. Wrote $ENV_FILE (permissions 600)."
echo "Notion: $([ -n "$NOTION_TOKEN" ] && echo enabled || echo disabled)"
echo
echo "Start it:"
echo "  docker compose up -d --build"
echo
echo "Then message @${BOT_NAME} on Telegram with a case PDF."
