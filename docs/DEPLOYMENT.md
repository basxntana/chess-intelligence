# Deployment

Three services: PostgreSQL 16, the FastAPI backend (API + analysis worker processes), and the Next.js frontend.
`infrastructure/docker-compose.prod.yml` runs all three on one host.

## 1. Configure secrets

```bash
cp infrastructure/.env.example infrastructure/.env   # git-ignored; never commit it
```

| Variable | Required | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | Database password (long random string) |
| `PUBLIC_APP_URL` | yes | URL users open; the backend's only allowed CORS origin |
| `PUBLIC_API_URL` | yes | URL browsers use for the API; baked into the frontend at build time (rebuild to change) |
| `ANALYSIS_WORKERS` | no (2) | Engine worker processes, about one CPU core each |
| `MAX_QUEUED_JOBS` | no (20) | Pending + running analyses before `POST /analysis` returns 429 |
| `ANTHROPIC_API_KEY` | no | Enables Claude explanations; without it explanations are rule-based |
| `LOG_LEVEL` | no (INFO) | |

## 2. Start

```bash
docker compose --env-file infrastructure/.env -f infrastructure/docker-compose.prod.yml up -d --build
```

The backend applies database migrations (`alembic upgrade head`) on every start, then serves on port 8000.
Put a TLS-terminating reverse proxy (Caddy, nginx, or the host platform's load balancer) in front of ports 3000 and
8000 so that `PUBLIC_APP_URL` and `PUBLIC_API_URL` are HTTPS.

## 3. Operate

- **Health:** `GET /health` → `{"status":"ok","database":"ok"}`; used by the compose healthcheck.
- **Metrics:** `GET /metrics` (Prometheus text): `http_requests_total`, `http_request_duration_seconds`,
  `analysis_jobs{status}`, `database_up`. Keep it on an internal network or behind the proxy's auth.
- **Logs:** one JSON object per line on stdout (`docker compose logs backend`), each request with `request_id`,
  route template, status and duration. Send `X-Request-ID` to correlate with upstream logs; it is echoed back.
- **Restarts:** an analysis still pending/running 10 minutes after it started (far beyond the 60 s time limit) is
  marked `failed` ("interrupted"), at the next start or when a client polls it; users can re-run it. Younger jobs are
  left alone, so starting a second backend process never fails jobs that another process is still running.
- **Backups:** `docker compose exec db pg_dump -U chess chess_intelligence > backup.sql`.
- **Capacity:** one analysis at the default depth takes roughly 1-10 s of one core. Throughput ≈
  `ANALYSIS_WORKERS` analyses in parallel; the queue limit protects the host from floods.

## 4. Security notes

- The API has no user accounts (out of MVP scope); anyone who can reach it can create and delete analyses.
  Expose it only to the intended audience, or add authentication at the proxy.
- Inputs are validated at the API boundary (FEN length/syntax/legality, UCI pattern, bounded depth/time/candidates,
  language pattern); requests never reach the engine with an illegal position.
- Containers run as non-root; the database port is not published.
- Engine `PUT /engine/config` changes defaults for every user of that backend process; restrict it at the proxy in a
  shared deployment.
