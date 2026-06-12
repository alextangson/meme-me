#!/usr/bin/env bash
# Deploy to production server (meme-planet.com), now on the 香港 ECS.
# Requires SSH alias `memeplanet-hk` in ~/.ssh/config (local machine only).
# Old Seattle VDS (`memeplanet-vds`) kept as a cold standby — its tunnel is stopped.
# Override target with MEMEPLANET_DEPLOY_HOST=memeplanet-vds to push to the standby.
#
# NEVER add --delete: packs/custom/ and out/ on the server hold production
# user data. packs/custom/ is excluded for the same reason — local copies
# are dev fixtures and must not overwrite user-created packs.
set -euo pipefail
cd "$(dirname "$0")"

TARGET="${MEMEPLANET_DEPLOY_HOST:-memeplanet-hk}"

echo "==> rsync -> ${TARGET}:/opt/memeplanet/"
rsync -avz \
  --exclude '.git' \
  --exclude 'out' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude 'packs/custom' \
  --exclude '.env' \
  --exclude '.DS_Store' \
  ./ "${TARGET}:/opt/memeplanet/"

echo "==> restart memeplanet.service"
ssh "$TARGET" 'systemctl restart memeplanet && systemctl is-active memeplanet'

echo "==> wait for app startup"
sleep 5

echo "==> smoke checks"
curl -fsS -o /dev/null -w 'home            %{http_code}\n' https://meme-planet.com/
curl -fsS -o /dev/null -w 'api/packs       %{http_code}\n' https://meme-planet.com/api/packs
curl -fsS -o /dev/null -w 'logo.png        %{http_code}\n' https://meme-planet.com/logo.png

echo "==> deployed OK"
