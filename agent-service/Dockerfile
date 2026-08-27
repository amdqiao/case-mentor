# Build context is the REPO ROOT, not agent-service/, because the image needs both the
# service and the skill folder:  docker build -f agent-service/Dockerfile .
# docker-compose.yml already does this.
FROM python:3.12-slim

# poppler-utils: the skill crops exhibit images out of the case PDF with pdftoppm.
RUN apt-get update && apt-get install -y poppler-utils curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code @notionhq/notion-mcp-server

# Non-root is required: the CLI refuses --dangerously-skip-permissions as root, and the
# service runs with permission_mode="bypassPermissions".
RUN useradd -m -u 1000 agent

WORKDIR /app
COPY agent-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent-service/service.py agent-service/telegram.py agent-service/main.py ./

# The skill ships as a reviewable folder, not a zip, and is baked in rather than mounted
# from the host — no host Claude config is ever exposed to this container.
COPY skill/case-mentor /opt/case-mentor/skill/case-mentor
COPY agent-service/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
 && mkdir -p /var/lib/case-mentor \
 && chown -R agent:agent /var/lib/case-mentor /app /opt/case-mentor

USER agent
ENV HOME=/home/agent
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
