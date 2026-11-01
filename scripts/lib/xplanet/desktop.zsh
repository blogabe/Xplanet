#!/bin/zsh
# Private foreground entrypoint owned by launchd; never call public start here.
set -u
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P) || exit 2
script_dir="$project_root/scripts"
fail() { print -u2 -- "xplanet desktop: $1"; exit 2; }
source "$script_dir/lib/xplanet/display.zsh" || exit 2
local -a desktop_args
desktop_command
if [[ -n "${EARTH_MAP_PRE:-}" ]]; then
    select_earth_map || exit $?
fi
exec "$XPLANET_BIN" "${desktop_args[@]}"
