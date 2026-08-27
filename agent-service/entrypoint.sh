#!/bin/sh
# $HOME is a Docker volume so the CLI's session index and transcripts survive restarts.
# The skill therefore cannot live in the image's $HOME — a named volume is populated from
# the image only the first time it is mounted, so later skill edits would never appear.
# Ship it at /opt and refresh the copy on every start instead.
set -e
mkdir -p "$HOME/.claude/skills"
rm -rf "$HOME/.claude/skills/case-mentor"
cp -r /opt/case-mentor/skill/case-mentor "$HOME/.claude/skills/case-mentor"
exec "$@"
