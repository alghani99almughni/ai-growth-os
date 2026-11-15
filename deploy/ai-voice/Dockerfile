FROM node:22-bookworm-slim AS web-build
WORKDIR /workspace/apps/ai-voice-standalone/web
COPY apps/ai-voice-standalone/web/package.json ./
RUN npm install
COPY apps/ai-voice-standalone/web/ ./
RUN npm run build

FROM node:22-bookworm-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NEXT_TELEMETRY_DISABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv nginx supervisor ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY apps/api/requirements.txt /app/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt
COPY apps/api /app/api
COPY --from=web-build /workspace/apps/ai-voice-standalone/web /app/web
COPY deploy/ai-voice/nginx.conf.template /etc/nginx/templates/ai-voice.conf.template
COPY deploy/ai-voice/supervisord.conf /etc/supervisor/conf.d/ai-voice.conf
COPY deploy/ai-voice/start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p /run/nginx
ENV PATH="/opt/venv/bin:$PATH" PORT=10000
EXPOSE 10000
CMD ["/app/start.sh"]
