#!/bin/sh
# Install for the current Codex user; run from any working directory.
set -eu
umask 077
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$repo"

case "$#" in
  0) local_service=yes; url="http://127.0.0.1:${LIGHTEN012_PORT:-8765}/mcp" ;;
  2) [ "$1" = --client-only ] || { echo "usage: $0 [--client-only MCP_URL]" >&2; exit 2; }
     local_service=no; url=$2 ;;
  *) echo "usage: $0 [--client-only MCP_URL]" >&2; exit 2 ;;
esac

command -v uv >/dev/null || { echo '缺少 uv，请先按 README 安装。' >&2; exit 1; }
command -v codex >/dev/null || { echo '缺少 Codex CLI，请先按 README 安装。' >&2; exit 1; }
uv sync --locked
python=$(uv run --no-sync python -c 'import sys; print(sys.executable)')
name=lighten012-memory
src="$repo/skills/$name"
skills_dir=${LIGHTEN012_SKILLS_DIR:-"$HOME/.agents/skills"}
dest="$skills_dir/$name"
mkdir -p "$skills_dir"
if [ -e "$dest" ] || [ -L "$dest" ]; then
    [ "$dest" -ef "$src" ] || { echo "已有同名 skill，请先核对 $dest" >&2; exit 1; }
fi
registered=no
if current=$(codex mcp get "$name" --json 2>/dev/null); then
    printf '%s' "$current" | "$python" -c '
import json, sys
record = json.load(sys.stdin)
if record["transport"].get("url") != sys.argv[1] or not record.get("enabled", True):
    sys.exit("已有同名 MCP 配置且地址或启用状态不同，请先核对")
' "$url"
    registered=yes
fi

if [ "$local_service" = yes ]; then
    settings_dir="${XDG_CONFIG_HOME:-$HOME/.config}/$name"
    state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/$name"
    mkdir -p "$settings_dir" "$state_dir"
    settings="$settings_dir/service.env"
    if [ ! -e "$settings" ]; then cp service.env.example "$settings"; fi
    if ! "$python" tools/check.py "$url" >/dev/null 2>&1; then
        nohup uv run --no-sync --env-file "$settings" python "$repo/tools/server.py" \
            </dev/null >>"$state_dir/service.log" 2>&1 &
        launcher=$!
        ready=no
        for _ in 1 2 3 4 5 6 7 8; do
            if "$python" tools/check.py "$url" >/dev/null 2>&1; then ready=yes; break; fi
            kill -0 "$launcher" 2>/dev/null || break
            sleep 1
        done
        [ "$ready" = yes ] || { echo "服务启动失败，见 $state_dir/service.log" >&2; exit 1; }
    fi
fi
"$python" tools/check.py "$url"
if [ ! -e "$dest" ]; then ln -s "$src" "$dest"; fi
if [ "$registered" = no ]; then codex mcp add "$name" --url "$url"; fi
echo "skill 已安装到 $dest。打开新的 Codex 会话验证工具调用。"
