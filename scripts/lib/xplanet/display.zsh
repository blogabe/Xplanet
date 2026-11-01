# Private zsh helpers, sourced by xplanet.sh after root discovery.

select_earth_map() (
    [[ -f "$project_root/config/xp.def" && ! -L "$project_root/config/xp.def" ]] ||
        fail "missing real config/xp.def"
    XPLANET_HOME=''
    EARTH_MAP_PRE=''
    source "$project_root/config/xp.def"
    [[ "$XPLANET_HOME" == "$project_root" ]] || fail "xp.def XPLANET_HOME must match this project root"
    if [[ "$EARTH_MAP_PRE" == stock ]]; then
        print -- "Stock Xplanet maps selected; no monthly Earth link to change."
        exit 0
    fi
    [[ "$EARTH_MAP_PRE" =~ '^([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)$' ]] ||
        fail "EARTH_MAP_PRE must be stock or a safe folder/name pattern"
    local folder="$match[1]" stem="$match[2]" month source target previous='' lockdir temporary
    month=$(date +%m)
    [[ "$month" == <-> && "$month" -ge 1 && "$month" -le 12 ]] || fail "Cannot determine Earth map month"
    source="assets/maps/$folder/$stem.2004${month}.3x5400x2700.png"
    target="../$source"
    for directory in assets assets/maps "assets/maps/$folder" images; do
        [[ -d "$project_root/$directory" && ! -L "$project_root/$directory" ]] ||
            fail "$directory must be a real directory"
    done
    [[ -f "$project_root/$source" && ! -L "$project_root/$source" ]] ||
        fail "Monthly map is absent or not a regular file: $source"
    for directory in .state .state/totalmarker; do
        if [[ ! -e "$project_root/$directory" && ! -L "$project_root/$directory" ]]; then
            mkdir -- "$project_root/$directory" || fail "Cannot create $directory"
        fi
        [[ -d "$project_root/$directory" && ! -L "$project_root/$directory" ]] ||
            fail "$directory must be a real directory"
    done
    lockdir="$project_root/.state/totalmarker/map.lock.d"
    mkdir -- "$lockdir" 2>/dev/null || fail "Earth map selection is locked"
    trap 'rmdir -- "$lockdir"' EXIT
    cd "$project_root/images" || fail "Cannot enter images directory"
    if [[ -e earth.png || -L earth.png ]]; then
        [[ -L earth.png ]] || fail "images/earth.png is not a symlink; refusing to replace it"
        previous=$(readlink earth.png) || fail "Cannot read images/earth.png"
        [[ "$previous" =~ '^\.\./assets/maps/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\.png$' ]] ||
            fail "images/earth.png is not an internal map link"
        if [[ "$previous" == "$target" ]]; then
            print -- "Earth map unchanged: $source"
            exit 0
        fi
    fi
    temporary=".earth-$$-$RANDOM.tmp"
    ln -s -- "$target" "$temporary" || fail "Cannot prepare Earth map link"
    trap 'rm -f -- "$temporary"; rmdir -- "$lockdir"' EXIT
    if [[ -n "$previous" ]]; then
        [[ -L earth.png && "$(readlink earth.png)" == "$previous" ]] ||
            fail "images/earth.png changed during selection"
    else
        [[ ! -e earth.png && ! -L earth.png ]] || fail "images/earth.png changed during selection"
    fi
    mv -f -- "$temporary" earth.png || fail "Contained Earth map link update failed"
    print -- "Earth map changed: $source"
)

load_render_config() {
    [[ -f "$project_root/config/xp.def" ]] || fail "missing config/xp.def"
    # Clear inherited values so xp.def must supply each render setting.
    XPLANET_BIN=''
    XPLANET_HOME=''
    XPLANET_CONFIG=''
    XPLANET_PROJECTION=''
    XPLANET_LONGITUDE=''
    XPLANET_LATITUDE=''
    XPLANET_GEOMETRY=''
    source "$project_root/config/xp.def"
    [[ "$XPLANET_HOME" == "$project_root" ]] || fail "xp.def XPLANET_HOME must match this project root"
    [[ -x "$XPLANET_BIN" ]] || fail "xp.def XPLANET_BIN must be executable"
    [[ -n "$XPLANET_PROJECTION" ]] || fail "xp.def XPLANET_PROJECTION is required"
    [[ -n "$XPLANET_LONGITUDE" ]] || fail "xp.def XPLANET_LONGITUDE is required"
    [[ -f "$project_root/config/xp.conf" ]] || fail "missing config/xp.conf"
    latitude_args=()
    if [[ -n "$XPLANET_LATITUDE" ]]; then
        latitude_args=(-latitude "$XPLANET_LATITUDE")
    fi
}

render_frame() {
    local geometry="$1" output="$2" temporary="$3"
    "$XPLANET_BIN" -body earth \
        -searchdir "$project_root" \
        -config "$project_root/config/xp.conf" \
        -projection "$XPLANET_PROJECTION" \
        "${latitude_args[@]}" \
        -longitude "$XPLANET_LONGITUDE" \
        -labelpos +10-45 \
        -date_format "%D at %r" \
        -color green2 \
        -geometry "$geometry" \
        -output "$output" \
        -tmpdir "$temporary" \
        -num_times 1
}

start_xplanet() {
    local -a geometry_args
    load_render_config
    [[ "$XPLANET_CONFIG" == "$project_root/config" ]] ||
        fail "xp.def XPLANET_CONFIG must match this project's config directory"
    geometry_args=()
    if [[ -n "$XPLANET_GEOMETRY" ]]; then
        geometry_args=("-geometry=$XPLANET_GEOMETRY")
    fi
    "$XPLANET_BIN" \
        "-searchdir=$XPLANET_HOME" \
        "-config=$XPLANET_CONFIG/xp.conf" \
        "-projection=$XPLANET_PROJECTION" \
        "${latitude_args[@]}" \
        "-longitude=$XPLANET_LONGITUDE" \
        -labelpos=+10-45 \
        '-date_format=%D at %r' \
        -color=green2 \
        "${geometry_args[@]}" \
        -fork || return $?
    [[ "${1:-}" == quiet ]] || interactive_note "Xplanet display started."
}

xplanet_pids() {
    local listing result pid
    listing=$(pgrep -u "$EUID" -x xplanet)
    result=$?
    (( result == 1 )) && return 0
    (( result == 0 )) || return 2
    for pid in ${(f)listing}; do
        [[ "$pid" == <-> ]] || return 2
        print -- "$pid"
    done
}

stop_xplanet() {
    local listing pid remaining attempt kill_bin
    kill_bin=$(whence -p kill) || fail "cannot locate the PID-specific kill command"
    [[ "$kill_bin" == /* && -x "$kill_bin" ]] ||
        fail "cannot use the PID-specific kill command"
    listing=$(xplanet_pids) || fail "could not inspect this user's Xplanet processes"
    if [[ -z "$listing" ]]; then
        [[ "${1:-}" == quiet ]] ||
            interactive_note "No Xplanet display for this user is running."
        return 0
    fi
    for pid in ${(f)listing}; do
        if ! "$kill_bin" -TERM "$pid"; then
            "$kill_bin" -0 "$pid" 2>/dev/null &&
                fail "could not stop Xplanet process $pid"
        fi
    done
    for ((attempt = 0; attempt < 20; attempt++)); do
        remaining=$(xplanet_pids) || fail "could not verify that Xplanet stopped"
        [[ -z "$remaining" ]] && break
        sleep 0.25
    done
    [[ -z "$remaining" ]] || fail "Xplanet is still running after stop"
    [[ "${1:-}" == quiet ]] || interactive_note "Xplanet display stopped."
}

restart_xplanet() {
    stop_xplanet quiet || return $?
    start_xplanet quiet || return $?
    interactive_note "Xplanet display running."
}
