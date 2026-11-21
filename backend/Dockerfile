FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
RUN pip install --no-cache-dir . && useradd --system --uid 1001 app
USER app
# Apply migrations, then serve. Analysis jobs run in ANALYSIS_WORKERS processes inside this container.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log"]
