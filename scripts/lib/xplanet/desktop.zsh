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
if [[ -n "${XPLANET_SCENE_DIRECTORY:-}" ]]; then
    # Current-directory lookup must resolve frozen native resources, not a
    # colliding checkout file. Writable renderer scratch stays outside revisions.
    if [[ ! -e "$XPLANET_SCENE_TMPDIR" && ! -L "$XPLANET_SCENE_TMPDIR" ]]; then
        mkdir -m 700 -- "$XPLANET_SCENE_TMPDIR" || fail "cannot create selected scene scratch directory"
    fi
    [[ -d "$XPLANET_SCENE_TMPDIR" && ! -L "$XPLANET_SCENE_TMPDIR" && "${XPLANET_SCENE_TMPDIR:A}" == "$XPLANET_SCENE_TMPDIR" ]] || fail "selected scene scratch directory must be real"
    cd -- "$XPLANET_SCENE_DIRECTORY" || fail "selected scene revision moved"
    desktop_args+=(-tmpdir "$XPLANET_SCENE_TMPDIR")
fi
exec "$XPLANET_BIN" "${desktop_args[@]}"
