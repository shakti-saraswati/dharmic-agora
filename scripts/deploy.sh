#!/bin/bash
set -euo pipefail

# SAB Docker Compose Deployment Script
# Usage: ./scripts/deploy.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🚀 SAB Deployment Script"
echo "========================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found!${NC}"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️  Please edit .env and set SAB_JWT_SECRET before deploying!${NC}"
    echo "Generate a secret with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    exit 1
fi

# Check if SAB_JWT_SECRET is still default
if grep -q "SAB_JWT_SECRET=change-me-in-production" .env; then
    echo -e "${RED}❌ Error: SAB_JWT_SECRET is still set to default value!${NC}"
    echo "Please update .env with a secure secret before deploying."
    exit 1
fi

echo "📦 Step 1/5: Pulling latest code..."
if [ -d .git ]; then
    git pull origin main || echo -e "${YELLOW}⚠️  Git pull failed or not needed${NC}"
else
    echo -e "${YELLOW}⚠️  Not a git repository, skipping pull${NC}"
fi

echo ""
echo "🏗️  Step 2/5: Building containers..."
docker compose build --no-cache

echo ""
echo "🗄️  Step 3/5: Running migrations (if any)..."
# For SQLite, migrations are handled by the app on startup
# If you add Alembic or similar later, run migrations here
echo "SQLite auto-migrates on startup - skipping explicit migrations"

echo ""
echo "⬆️  Step 4/5: Starting services..."
docker compose down
docker compose up -d

echo ""
echo "🏥 Step 5/5: Health check..."
echo "Waiting for services to be healthy..."

# Wait for sab-api to be healthy
MAX_WAIT=60
WAIT_COUNT=0
while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if docker compose ps | grep -q "sab_api.*healthy"; then
        echo -e "${GREEN}✅ sab-api is healthy${NC}"
        break
    fi
    echo -n "."
    sleep 2
    WAIT_COUNT=$((WAIT_COUNT + 2))
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo -e "${RED}❌ Health check timeout!${NC}"
    echo "Container logs:"
    docker compose logs sab-api
    exit 1
fi

# Test the endpoint
echo ""
echo "🧪 Testing health endpoint..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Health endpoint responding${NC}"
else
    echo -e "${YELLOW}⚠️  Health endpoint not accessible from host${NC}"
fi

echo ""
echo "📊 Deployment Status:"
echo "===================="
docker compose ps

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "📝 Next steps:"
echo "  • Check logs: docker compose logs -f"
echo "  • Stop services: docker compose down"
echo "  • View status: docker compose ps"
echo ""
echo "🌐 Endpoints:"
echo "  • API (local): http://localhost:8000"
echo "  • API (proxy): http://localhost (Caddy)"
echo "  • Health: http://localhost:8000/health"
echo "  • Docs: http://localhost:8000/docs"
echo ""

# Load domain from .env
source .env
if [ -n "${SAB_DOMAIN:-}" ]; then
    echo "  • Production: https://$SAB_DOMAIN"
    echo ""
    echo -e "${YELLOW}⚠️  Remember to point your DNS to this server!${NC}"
fi

echo ""
echo "🔥 SAB is live!"
