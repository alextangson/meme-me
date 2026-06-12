#!/usr/bin/env bash
# 备份生产用户数据，按价值/体积分三类独立备份+轮转：
#   - state：钱与权益（out/devices 设备账本 + out/codes.json 兑换码 + events/leads/drafts）
#            极小、不可重建、丢了等于丢钱 → 留最多
#   - custom：用户定制剧本（YAML，极小、不可重建、曾被误清空丢失过）→ 多留
#   - web：生成的表情图（大、可部分重建、历史展示）→ 少留几份够回滚近期
# 备份目录独立于 SRC，所以"清空/误重置"不会连累备份。
#
# 装到生产（在服务器上跑，非本地）:
#   scp scripts/backup-userdata.sh memeplanet-hk:/opt/memeplanet/scripts/
#   ssh memeplanet-hk 'chmod +x /opt/memeplanet/scripts/backup-userdata.sh \
#     && ( crontab -l 2>/dev/null; echo "17 4 * * * /opt/memeplanet/scripts/backup-userdata.sh >> /var/log/mp-backup.log 2>&1" ) | crontab -'
# 手动验证一次: ssh memeplanet-hk /opt/memeplanet/scripts/backup-userdata.sh
set -euo pipefail

SRC="${MEMEME_BACKUP_SRC:-/opt/memeplanet}"
DEST="${MEMEME_BACKUP_DEST:-/opt/memeplanet-backups}"
KEEP_STATE="${MEMEME_BACKUP_KEEP_STATE:-60}"    # 钱与权益：极小，留两个月
KEEP_CUSTOM="${MEMEME_BACKUP_KEEP_CUSTOM:-30}"  # 定制剧本：小且珍贵，留一个月
KEEP_WEB="${MEMEME_BACKUP_KEEP_WEB:-4}"          # 生成图：大，留近 4 份够回滚

mkdir -p "$DEST"

_rotate() {  # 按时间倒序，删掉第 keep 份之后的（仅同前缀）
  local name="$1" keep="$2"
  ls -1t "$DEST/$name-"*.tar.gz 2>/dev/null | tail -n +"$((keep + 1))" | xargs -r rm -f
  echo "  $name ok: $(du -h "$DEST/$name-"*.tar.gz 2>/dev/null | tail -1 | cut -f1), kept $(ls -1 "$DEST/$name-"*.tar.gz 2>/dev/null | wc -l | tr -d ' ')"
}

backup_dir() {  # 备份单个目录
  local name="$1" path="$2" keep="$3"
  [ -d "$SRC/$path" ] || { echo "  skip $name ($path 不存在)"; return 0; }
  tar -czf "$DEST/$name-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$SRC" "$path"
  _rotate "$name" "$keep"
}

backup_state() {  # 打包多个小而珍贵的路径（存在的才进）
  local name="state" keep="$KEEP_STATE" paths=()
  for p in out/devices out/codes.json out/events.jsonl out/leads.jsonl out/drafts; do
    [ -e "$SRC/$p" ] && paths+=("$p")
  done
  [ ${#paths[@]} -gt 0 ] || { echo "  skip state (无数据)"; return 0; }
  tar -czf "$DEST/$name-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$SRC" "${paths[@]}"
  _rotate "$name" "$keep"
}

echo "backup @ $(date +%F\ %T)"
backup_state
backup_dir custom packs/custom "$KEEP_CUSTOM"
backup_dir web out/web "$KEEP_WEB"
