#!/usr/bin/env bash
set -euo pipefail

directory=$(cd -- "$(dirname -- "$0")" && pwd)
url=http://127.0.0.1:8787
page="$url/"
if [[ ${1:-} == watch ]]; then page="$url/watch"; fi

(
  flock 9
  if ! curl -fsS --max-time 1 "$url/api/status" >/dev/null; then
    nohup python3 "$directory/server.py" >"$directory/server.log" 2>&1 </dev/null 9>&- &
  fi
  for ((attempt=0; attempt<20; attempt++)); do
    if curl -fsS --max-time 1 "$url/api/status" >/dev/null; then exit 0; fi
    sleep .15
  done
  exit 1
) 9>"$directory/server.lock"

if [[ ${1:-} == terminal ]]; then
  printf -v terminal_command '%q ' python3 -u "$directory/trace_terminal.py"
  exec lxterminal --title="星闪传输日志" --geometry=110x28 -e "$terminal_command"
fi

exec chromium-browser --user-data-dir="$directory/chromium-profile" --no-first-run \
  --start-fullscreen --app="$page" >>"$directory/browser.log" 2>&1
