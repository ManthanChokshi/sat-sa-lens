#!/usr/bin/env bash
# Build the images, save them to a tar, and write load instructions next to it.
# Carry the resulting folder to an air-gapped machine on a USB drive.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="${1:-dist/offline-bundle}"
mkdir -p "$OUT"

echo "==> Building images"
docker compose build

echo "==> Saving images to $OUT/satsa-lens-images.tar"
docker save satsa-lens-backend:1.0.0 satsa-lens-frontend:1.0.0 \
  -o "$OUT/satsa-lens-images.tar"

cp docker-compose.yml docker-compose.offline.yml "$OUT/"

cat > "$OUT/LOAD.md" <<'MD'
# SAT-SA Lens - offline bundle

Everything needed to run the tool on a machine with no internet connection.

## Contents
- `satsa-lens-images.tar` - the backend and frontend container images
- `docker-compose.yml`, `docker-compose.offline.yml` - the stack definition

## Install on the air-gapped machine

```bash
docker load -i satsa-lens-images.tar
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
```

Open http://localhost:8080.

On first start the backend generates the sample corpus (seed 42), ingests it and
runs the first analysis; that takes one to two minutes. After that the app is
immediately usable, and you can upload real submissions from the Upload page.

`docker-compose.offline.yml` puts the containers on an internal-only network, so
they cannot reach anything outside the host even if the host itself is online.
That is the configuration to use when demonstrating air-gapped operation.

## Verify it really is offline

```bash
docker compose exec backend python -c "import socket; socket.create_connection(('1.1.1.1',53),3)"
```
This must fail with a network-unreachable error.
MD

SIZE=$(du -sh "$OUT" | cut -f1)
echo "==> Bundle ready in $OUT ($SIZE). See $OUT/LOAD.md"
