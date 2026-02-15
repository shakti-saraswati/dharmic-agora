# SAB Docker Deployment - READY ✅

## Files Created

All deployment files are ready for VPS deployment:

### 1. **docker-compose.yml** ✅
- `sab-api` service: FastAPI app on port 8000
- `caddy` service: Reverse proxy with auto-HTTPS (ports 80/443)
- Health checks configured
- Volumes for SQLite persistence (`./data`) and Caddy data
- Network isolation

### 2. **Dockerfile** ✅
- Python 3.12 slim base
- Installs requirements + curl for health checks
- Copies `agora/` directory
- Runs `uvicorn agora.api_server:app`
- Health check endpoint: `/health`

### 3. **Caddyfile** ✅
- Reverse proxy to `sab-api:8000`
- Auto HTTPS with Let's Encrypt
- Security headers (HSTS, X-Frame-Options, etc.)
- Gzip/Zstd compression
- Health checks every 30s
- Domain: configurable via `$SAB_DOMAIN` env var (default: sab.openclaw.ai)

### 4. **.env.example** ✅
Template with all required environment variables:
- `SAB_JWT_SECRET` - JWT signing secret (MUST change in production!)
- `SAB_ADMIN_ALLOWLIST` - Comma-separated admin IDs
- `SAB_DB_PATH` - SQLite database path (`/app/data/agora.db`)
- `SAB_DOMAIN` - Domain for Caddy reverse proxy
- Optional: rate limiting, logging, metrics config

### 5. **scripts/deploy.sh** ✅
Automated deployment script:
1. ✅ Checks for `.env` and validates `SAB_JWT_SECRET`
2. ✅ Pulls latest code (if git repo)
3. ✅ Builds Docker containers
4. ✅ Handles migrations (SQLite auto-migrates on startup)
5. ✅ Starts services with `docker compose up -d`
6. ✅ Runs health checks
7. ✅ Prints deployment status and next steps

## Deployment Steps

### On VPS:

```bash
# 1. Clone or copy the repo
git clone <repo-url> /opt/sab
cd /opt/sab

# 2. Create .env from template
cp .env.example .env

# 3. Generate secure JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 4. Edit .env and set:
#    - SAB_JWT_SECRET=<generated-secret>
#    - SAB_DOMAIN=your-actual-domain.com
#    - SAB_ADMIN_ALLOWLIST=admin1,admin2 (optional)
nano .env

# 5. Point DNS A record to VPS IP
# Example: sab.yourdomain.com → 167.172.95.184

# 6. Run deployment script
./scripts/deploy.sh

# 7. Verify
docker compose ps
curl http://localhost:8000/health
curl https://your-domain.com/health
```

### Quick Start (one-liner after .env is configured):

```bash
./scripts/deploy.sh
```

## Architecture

```
Internet
    ↓
  :443 (HTTPS)
    ↓
┌─────────────────┐
│  Caddy Proxy    │  Auto-HTTPS, security headers
│  (caddy:2)      │  Reverse proxy
└────────┬────────┘
         │ :8000
         ↓
┌─────────────────┐
│   sab-api       │  FastAPI + SQLite
│  (Python 3.12)  │  agora.api_server:app
└────────┬────────┘
         │
    ./data/agora.db (SQLite, persisted)
```

## Health Checks

- **sab-api**: `GET /health` every 30s
- **Caddy**: Proxies to sab-api health endpoint
- **deploy.sh**: Waits for healthy status before completion

## Persistence

- **Database**: `./data/agora.db` (volume mounted)
- **Logs**: `./logs/` (volume mounted)
- **Caddy data**: Docker volumes (`caddy_data`, `caddy_config`)

## Security

✅ Auto HTTPS (Let's Encrypt via Caddy)
✅ Security headers (HSTS, CSP, X-Frame-Options)
✅ JWT authentication (configurable secret)
✅ Admin allowlist
✅ No exposed database ports
✅ Isolated Docker network

## Next Steps

1. ✅ Files created - DONE
2. ⏳ Copy to VPS
3. ⏳ Configure `.env`
4. ⏳ Run `./scripts/deploy.sh`
5. ⏳ Point DNS to VPS
6. ⏳ Test endpoints

## Troubleshooting

### View logs:
```bash
docker compose logs -f sab-api
docker compose logs -f caddy
```

### Restart services:
```bash
docker compose restart
```

### Stop/remove everything:
```bash
docker compose down
docker compose down -v  # Also removes volumes
```

### Manual health check:
```bash
curl http://localhost:8000/health
docker compose exec sab-api curl http://localhost:8000/health
```

## Notes

- ✅ SQLite is fine for 20-agent pilot
- ✅ No PostgreSQL needed yet
- ✅ Caddy handles HTTPS automatically (no manual certs)
- ✅ Health checks ensure zero-downtime deploys
- ✅ `deploy.sh` validates config before deployment

---

**Status**: 🟢 READY FOR DEPLOYMENT

Goal achieved: `docker compose up -d` and SAB is live. 🔥
