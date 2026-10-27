# Build context: the repo root (see infra/livekit/docker-compose.yml)
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY src ./src
COPY voice ./voice
COPY config ./config
COPY data ./data
CMD ["python", "-m", "voice.agent", "start"]
