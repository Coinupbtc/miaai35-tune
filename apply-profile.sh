#!/usr/bin/env bash
# Apply a llama-miaai35 systemd profile unit and restart safely.
# Usage: ./apply-profile.sh ORIGINAL|PASS1_parallel1|...|MAX_SPEED|BALANCED|MAX_QUALITY
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROFILES="${ROOT}/profiles"
UNIT_DST="${HOME}/.config/systemd/user/llama-miaai35.service"
NAME="${1:-}"
HEALTH_URL="http://127.0.0.1:8889/health"
MAX_WAIT="${MAX_WAIT:-300}"

if [[ -z "${NAME}" ]]; then
  echo "Usage: $0 <profile-name>" >&2
  echo "Available:" >&2
  ls -1 "${PROFILES}"/*.service 2>/dev/null | xargs -n1 basename | sed 's/\.service$//' >&2
  exit 1
fi

SRC="${PROFILES}/${NAME}.service"
if [[ ! -f "${SRC}" ]]; then
  echo "error: missing profile ${SRC}" >&2
  exit 1
fi

# Always keep a rolling backup of whatever is live before overwrite
stamp="$(date +%Y%m%d-%H%M%S)"
if [[ -f "${UNIT_DST}" ]]; then
  cp -a "${UNIT_DST}" "${ROOT}/backups/llama-miaai35.service.pre-apply-${stamp}"
fi

cp -a "${SRC}" "${UNIT_DST}"
systemctl --user daemon-reload
# Rapid profile swaps can hit StartLimitBurst=5 — clear before restart.
systemctl --user reset-failed llama-miaai35.service 2>/dev/null || true
echo "Restarting llama-miaai35 with profile: ${NAME}"
t0=$(date +%s)
systemctl --user restart llama-miaai35.service

elapsed=0
while (( elapsed < MAX_WAIT )); do
  if curl -fsS -m 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    t1=$(date +%s)
    echo "READY profile=${NAME} load_wait=$((t1 - t0))s"
    systemctl --user is-active llama-miaai35.service
    # show active cmdline snippet
    pid="$(systemctl --user show -p MainPID --value llama-miaai35.service)"
    if [[ -n "${pid}" && "${pid}" != "0" ]]; then
      echo "pid=${pid}"
      tr '\0' ' ' < "/proc/${pid}/cmdline"; echo
    fi
    exit 0
  fi
  if ! systemctl --user is-active --quiet llama-miaai35.service; then
    # still starting?
    st=$(systemctl --user is-active llama-miaai35.service || true)
    if [[ "${st}" == "failed" || "${st}" == "inactive" ]]; then
      echo "service state=${st} — recent journal:" >&2
      journalctl --user -u llama-miaai35.service -n 40 --no-pager >&2 || true
      exit 1
    fi
  fi
  sleep 2
  elapsed=$((elapsed + 2))
  printf '\rwaiting health %ds/%ds' "${elapsed}" "${MAX_WAIT}"
done
echo
echo "error: health not ready within ${MAX_WAIT}s" >&2
journalctl --user -u llama-miaai35.service -n 60 --no-pager >&2 || true
exit 1
