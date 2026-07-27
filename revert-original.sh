#!/usr/bin/env bash
# Instant revert to ORIGINAL measured baseline unit.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT}/apply-profile.sh" ORIGINAL
