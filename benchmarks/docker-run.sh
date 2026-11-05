#!/usr/bin/env bash
set -euo pipefail

# Reuse one immutable local image ID or registry digest for both revisions.
image=${SPOTLIGHT_BENCH_IMAGE:-a6e34c598f24}
if [[ ! $image =~ ^(sha256:)?[a-f0-9]{12,64}$ && ! $image =~ @sha256:[a-f0-9]{64}$ ]]; then
  printf 'Set SPOTLIGHT_BENCH_IMAGE to an immutable image ID or name@sha256:digest.\n' >&2
  exit 2
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir=$(cd -- "${1:-$script_dir/..}" && pwd)
if (( $# )); then shift; fi
exec docker run --rm --pull=never --network=none --read-only --cpus=1 --memory=256m --memory-swap=256m --pids-limit=128 --cap-drop=ALL --security-opt=no-new-privileges --tmpfs /tmp:rw,exec,nosuid,size=128m --mount "type=bind,src=$source_dir,dst=/source,readonly" --mount "type=bind,src=$script_dir,dst=/bench,readonly" --env "SPOTLIGHT_BENCH_IMAGE=$image" --env PYTHONDONTWRITEBYTECODE=1 "$image" python3 /bench/run.py --source /source "$@"
