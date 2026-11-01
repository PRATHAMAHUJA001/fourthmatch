#!/usr/bin/env bash
# Idempotent FourthMatch demo setup for Ubuntu 24.04 (Lightsail / EC2). Run as a sudo-capable user:
#   curl -fsSL <raw setup.sh url> | sudo bash        # or: sudo bash deploy/setup.sh
# Optional env: REPO_URL, BRANCH, DOMAIN (e.g. demo.example.com; omit for plain http on the IP).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/PRATHAMAHUJA001/fourthmatch.git}"
BRANCH="${BRANCH:-main}"
APP_DIR=/opt/fourthmatch
APP_USER=fourthmatch
ENV_FILE=/etc/fourthmatch.env
DOMAIN="${DOMAIN:-}"

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo bash deploy/setup.sh)"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "== 1/7 packages"
apt-get update -y
apt-get install -y python3.12-venv ffmpeg fonts-dejavu-core sqlite3 git curl ca-certificates \
  debian-keyring debian-archive-keyring apt-transport-https gpg
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi
# Vite 8 needs Node >= 20.19; Ubuntu 24.04's apt nodejs is 18, so use NodeSource 22.
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

echo "== 2/7 user + code"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH" && git -C "$APP_DIR" checkout "$BRANCH" && git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "== 3/7 frontend build"
sudo -u "$APP_USER" -H bash -c "cd $APP_DIR/frontend && npm ci && npm run build"

echo "== 4/7 backend venv"
sudo -u "$APP_USER" -H bash -c "cd $APP_DIR/backend && python3.12 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt"

echo "== 5/7 env file (secrets stay here, never in the repo)"
if [ ! -f "$ENV_FILE" ]; then
  PASS="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)"
  cp "$APP_DIR/.env.example" "$ENV_FILE"
  { echo "DEMO_MODE=true"; echo "DEMO_PASSCODE=$PASS"; echo "LIVE_UPLOAD_LIMIT_PER_HOUR=10"; } >> "$ENV_FILE"
  echo ">>> Created $ENV_FILE. DEMO_PASSCODE=$PASS   (edit the file to set MODEL_API_KEY)"
fi
chown root:root "$ENV_FILE" && chmod 600 "$ENV_FILE"

echo "== 6/7 demo data (no model calls)"
sudo -u "$APP_USER" -H bash -c "set -a; . $ENV_FILE; set +a; cd $APP_DIR/backend && .venv/bin/python -m app.seed --demo"
# Packs freeze the verdict, so build them only when approved rules exist; with no rules every
# case would read "approve" (see the NO APPROVED RULES warning above and DEPLOY.md).
RULES="$(sqlite3 "$APP_DIR/data/fourthmatch.db" "select count(*) from rules where status='approved' and rule_id is not null" 2>/dev/null || echo 0)"
if [ "${RULES:-0}" -gt 0 ]; then
  sudo -u "$APP_USER" -H bash -c "set -a; . $ENV_FILE; set +a; cd $APP_DIR && PYTHONPATH=backend backend/.venv/bin/python scripts/build_evidence_packs.py" \
    || echo "WARN: evidence pack build failed (case pages still work; see output above)"
else
  echo "WARN: no approved rules loaded -> skipping evidence packs. Commit data/demo/snapshot.json (scripts/export_demo_snapshot.py) and re-run."
fi

echo "== 7/7 services"
install -m 644 "$APP_DIR/deploy/fourthmatch.service" /etc/systemd/system/fourthmatch.service
install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironment=FM_SITE=%s\n' "${DOMAIN:-:80}" > /etc/systemd/system/caddy.service.d/site.conf
systemctl daemon-reload
systemctl enable --now fourthmatch caddy
systemctl restart fourthmatch caddy
sleep 3
curl -fsS http://127.0.0.1:8000/api/health && echo && echo "OK. Open http://${DOMAIN:-<server public IP>}/"
