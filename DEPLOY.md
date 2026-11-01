# Deploying the FourthMatch demo on AWS (Lightsail, no Docker)

One small Ubuntu 24.04 VM: Caddy (HTTP/auto-HTTPS) -> uvicorn (1 worker, systemd) -> FastAPI,
which serves `/api` and the built SPA. SQLite + local `storage/`. Cost about **$5-10/month**
(Lightsail 1 GB = $5, 2 GB = $10). **Delete the instance after judging.**

## 1. Create the instance
Console: Lightsail -> Create instance -> Linux/Unix -> OS only -> **Ubuntu 24.04 LTS** -> plan
1 GB (2 GB if `npm ci` runs out of memory) -> name `fourthmatch`. Or CLI:
```bash
aws lightsail create-instances --instance-names fourthmatch --availability-zone ap-south-1a \
  --blueprint-id ubuntu_24_04 --bundle-id small_3_0
aws lightsail open-instance-public-ports --instance-name fourthmatch \
  --port-info fromPort=80,toPort=80,protocol=TCP
aws lightsail open-instance-public-ports --instance-name fourthmatch \
  --port-info fromPort=443,toPort=443,protocol=TCP
aws lightsail get-instance --instance-name fourthmatch --query instance.publicIpAddress
```
(Console: instance -> Networking -> add rules for HTTP 80 and HTTPS 443; 22 is open by default.
Optionally attach a static IP.) For HTTPS, point a DNS A record at the IP first.

## 2. Install
```bash
ssh -i <key.pem> ubuntu@<PUBLIC_IP>
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/PRATHAMAHUJA001/fourthmatch.git /tmp/fm && cd /tmp/fm
sudo DOMAIN=demo.example.com bash deploy/setup.sh     # omit DOMAIN for plain http://<PUBLIC_IP>
```
`setup.sh` is idempotent (re-run it to deploy a new commit). It installs the packages (ffmpeg,
fonts-dejavu-core for the rupee glyph in PDFs, Caddy, Node 22), clones to `/opt/fourthmatch`,
builds the SPA, creates the venv, seeds + loads the demo data, and starts both services.
On first run it prints a random `DEMO_PASSCODE`.

## 3. Secrets
Everything secret lives in `/etc/fourthmatch.env` (root, `chmod 600`), never in the repo:
```bash
sudo nano /etc/fourthmatch.env     # set MODEL_API_KEY=... (model IDs are pre-filled from .env.example)
sudo systemctl restart fourthmatch
```
Without `MODEL_API_KEY` the seeded cases are fully browsable; live uploads fail with a 500.

## 4. Verify
```bash
curl -s http://<PUBLIC_IP>/api/health                      # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" http://<PUBLIC_IP>/cases/1     # 200 (SPA)
curl -s http://<PUBLIC_IP>/api/nope                        # JSON 404 error shape
curl -s -F po_id=1 -F video=@x.mp4 http://<PUBLIC_IP>/api/deliveries   # 403 without passcode
sudo journalctl -u fourthmatch -n 50 --no-pager
```

## Demo gate and rotating the passcode
`DEMO_MODE=true`: `POST /api/deliveries` needs header `X-Demo-Passcode: <DEMO_PASSCODE>` (403
otherwise; empty server passcode = live uploads off) and at most `LIVE_UPLOAD_LIMIT_PER_HOUR`
(default 10) accepted uploads per rolling hour (429). Replay of seeded cases is always open.
Rotate:
```bash
sudo sed -i "s/^DEMO_PASSCODE=.*/DEMO_PASSCODE=$(head -c 18 /dev/urandom | base64 | tr -dc A-Za-z0-9 | head -c 16)/" /etc/fourthmatch.env
sudo systemctl restart fourthmatch && sudo grep DEMO_PASSCODE /etc/fourthmatch.env
```
Note: the frontend must send that header from its upload dialog (passcode field); curl works today.

## Demo data without a model key
`python -m app.seed --demo` (run by setup.sh and before each service start) imports the perception
counts from the committed `data/eval_counts.json`. The **approved compiled rules** are model
output and are not committed: export them once on the Mac that ran the policy compile, and commit:
```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/export_demo_snapshot.py   # writes data/demo/snapshot.json
git add data/demo/snapshot.json && git commit -m "Add demo snapshot"
```
Until that file exists, the loader prints `NO APPROVED RULES LOADED`, setup skips evidence packs, and
case pages show perception counts but every verdict reads "approve" (no rules to fire). Do not
demo in that state.

## Zero-backend fallback (S3 static website)
`cd frontend && npm run build:demo` (MSW mocks, data baked from repo files), then:
```bash
aws s3 mb s3://<unique-bucket> --region ap-south-1
aws s3 website s3://<unique-bucket> --index-document index.html --error-document index.html
aws s3api put-public-access-block --bucket <unique-bucket> --public-access-block-configuration BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false
aws s3api put-bucket-policy --bucket <unique-bucket> --policy '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::<unique-bucket>/*"}]}'
aws s3 sync frontend/dist s3://<unique-bucket> --delete
# http://<unique-bucket>.s3-website.ap-south-1.amazonaws.com
```
`error-document index.html` makes client-side routes survive a reload (the 404 page is the SPA;
S3 serves it with status 404, fine for a demo). Delete the bucket afterwards.

## Cleanup
```bash
aws lightsail delete-instance --instance-name fourthmatch
```
