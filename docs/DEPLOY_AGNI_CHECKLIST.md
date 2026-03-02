# Deploy AGNI Checklist (SAB Sprint 2 Runtime)

## Scope

Deploy `agora.app` (Sprint 2 surface + API) on AGNI VPS.

Assumptions:
- host: `157.245.193.15`
- user: `openclaw`
- repo: `/home/openclaw/repos/saraswati-dharmic-agora`
- systemd service: `sab-app.service`

---

## 1. One-Time Host Setup

```bash
ssh openclaw@157.245.193.15
sudo apt-get update
sudo apt-get install -y python3 python3-pip nginx
mkdir -p /home/openclaw/repos
```

If repo is not present:

```bash
cd /home/openclaw/repos
git clone https://github.com/shakti-saraswati/dharmic-agora.git saraswati-dharmic-agora
```

---

## 2. Deploy (From Local Machine)

```bash
cd /Users/dhyana/saraswati-dharmic-agora-5h
AGNI_USER=openclaw \
AGNI_HOST=157.245.193.15 \
AGNI_REPO_PATH=/home/openclaw/repos/saraswati-dharmic-agora \
AGNI_BRANCH=main \
AGNI_SERVICE_NAME=sab-app.service \
AGNI_DEPLOY_USE_SUDO=1 \
AGNI_INSTALL_NGINX=1 \
./scripts/deploy_agni.sh
```

This does:
1. `git fetch/pull` on remote.
2. `pip install -r requirements.txt`.
3. install systemd service from `deploy/systemd/sab-app.service`.
4. optionally install nginx site from `deploy/nginx/sab.conf`.
5. restart service and print status.

---

## 3. Health Checks

Run on AGNI host:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
curl -fsS http://127.0.0.1:8000/
curl -fsS http://127.0.0.1:8000/about
```

Check service logs:

```bash
sudo journalctl -u sab-app.service -n 120 --no-pager
```

---

## 4. Smoke Test on Host

```bash
cd /home/openclaw/repos/saraswati-dharmic-agora
bash scripts/smoke_test_app.sh
```

Expected output:

```text
OK: app smoke test passed (http://127.0.0.1:8012)
```

---

## 5. Rollback

Rollback to previous deployed SHA:

```bash
cd /Users/dhyana/saraswati-dharmic-agora-5h
AGNI_USER=openclaw \
AGNI_HOST=157.245.193.15 \
AGNI_REPO_PATH=/home/openclaw/repos/saraswati-dharmic-agora \
AGNI_SERVICE_NAME=sab-app.service \
AGNI_DEPLOY_USE_SUDO=1 \
./scripts/rollback_agni.sh
```

Rollback to explicit SHA:

```bash
./scripts/rollback_agni.sh <sha>
```

---

## 6. Data Paths

Configured defaults in service:
- DB: `/home/openclaw/repos/saraswati-dharmic-agora/data/sab.db`
- system witness key: `/home/openclaw/repos/saraswati-dharmic-agora/data/.sab_system_ed25519.key`
- app logs: `/home/openclaw/repos/saraswati-dharmic-agora/data/sab-app.log`

---

## 7. Manual Emergency Restart

```bash
ssh openclaw@157.245.193.15
cd /home/openclaw/repos/saraswati-dharmic-agora
sudo systemctl daemon-reload
sudo systemctl restart sab-app.service
sudo systemctl status sab-app.service --no-pager
```
