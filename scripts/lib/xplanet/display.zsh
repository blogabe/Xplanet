# Scene helpers contain literal data handling only; legacy mode stays the default.
source "$script_dir/lib/xplanet/scene.zsh" || return 2
source "$script_dir/lib/xplanet/lifecycle.zsh" || return 2

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
    mkdir -- "$lockdir" 2>/dev/null ||
        fail "Earth map selection is locked at $lockdir; another earth command may be running. If none is running after an interruption, remove that empty lock directory with rmdir and retry."
    trap 'rmdir -- "$lockdir"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
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
    EARTH_MAP_PRE=''
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

desktop_command() {
    XPLANET_SCENE_DIRECTORY=''
    XPLANET_SCENE_TMPDIR=''
    selected_scene_command && return 0
    load_render_config
    # Resolve configured symlinks once; execute the real binary rather than
    # introducing an arbitrary alias into the OS process name.
    XPLANET_BIN=${XPLANET_BIN:A}
    [[ "$XPLANET_CONFIG" == "$project_root/config" ]] ||
        fail "xp.def XPLANET_CONFIG must match this project's config directory"
    desktop_args=("-searchdir=$XPLANET_HOME" "-config=$XPLANET_CONFIG/xp.conf"
                  "-projection=$XPLANET_PROJECTION" "${latitude_args[@]}"
                  "-longitude=$XPLANET_LONGITUDE" -labelpos=+10-45
                  '-date_format=%D at %r' -color=green2)
    if [[ -n "$XPLANET_GEOMETRY" ]]; then
        desktop_args+=("-geometry=$XPLANET_GEOMETRY")
    fi
}

# One foreground desktop service per GUI user. The existing login trigger
# remains separate; it calls public start and must never kickstart itself.
desktop_label=local.xplanet.desktop
desktop_domain="gui/$EUID"

_start_xplanet() {
    local -a desktop_args
    local map_note state temporary
    desktop_command
    if [[ -n "${EARTH_MAP_PRE:-}" ]]; then
        map_note=$(select_earth_map) || return $?
    fi
    command -v launchctl >/dev/null || fail "launchctl is required for the desktop"
    if ! launchctl list "$desktop_label" >/dev/null 2>&1; then
        # Do not start a second desktop on top of the old -fork installation.
        # An explicit restart authorizes the same broad termination as stop.
        local existing
        existing=$(xplanet_pids) || fail "could not inspect Xplanet processes"
        [[ -z "$existing" ]] || fail "Xplanet is already running outside the desktop job; use restart to stop all instances and migrate"
        state="$project_root/.state/xplanet"
        local directory
        for directory in "$project_root/.state" "$state" "$project_root/logs"; do
            [[ ! -L "$directory" ]] || fail "desktop directories must not be symlinks"
            mkdir -p -- "$directory" || fail "cannot create desktop directories"
            [[ -d "$directory" ]] || fail "desktop directory is not a directory"
        done
        temporary=$(mktemp "$state/desktop.XXXXXXXX") || fail "cannot prepare desktop job"
        # Use macOS's plist writer, never interpolate paths into XML or shell text.
        (
            trap 'rm -f -- "$temporary"' EXIT
            /usr/bin/plutil -create xml1 "$temporary" &&
            /usr/bin/plutil -insert Label -string "$desktop_label" "$temporary" &&
            /usr/bin/plutil -insert ProgramArguments -xml '<array/>' "$temporary" &&
            /usr/bin/plutil -insert ProgramArguments.0 -string /bin/zsh "$temporary" &&
            /usr/bin/plutil -insert ProgramArguments.1 -string "$script_dir/lib/xplanet/desktop.zsh" "$temporary" &&
            /usr/bin/plutil -insert WorkingDirectory -string "$project_root" "$temporary" &&
            /usr/bin/plutil -insert StandardOutPath -string "$project_root/logs/xplanet.log" "$temporary" &&
            /usr/bin/plutil -insert StandardErrorPath -string "$project_root/logs/xplanet-error.log" "$temporary" &&
            mv -f -- "$temporary" "$state/desktop.plist"
        ) || fail "cannot prepare desktop plist"
        launchctl bootstrap "$desktop_domain" "$state/desktop.plist" || {
            launchctl list "$desktop_label" >/dev/null 2>&1 || fail "could not register desktop job"
        }
    fi
    launchctl kickstart "$desktop_domain/$desktop_label" || fail "could not start desktop job"
    interactive_note "Xplanet desktop start requested; launchd accepted the request. Rendering is asynchronous."
}

# Reinstall only needs to know whether this user has Xplanet processes to replace.
desktop_status() {
    xplanet_pids
}

xplanet_pids() {
    local listing result pid name pattern character
    local -a names=(xplanet)
    if [[ -f "$project_root/config/xp.def" ]]; then
        # Personal shell configuration is intentionally executable. Stop still
        # works without it; normal and configured binary names are sufficient.
        local XPLANET_BIN=''
        source "$project_root/config/xp.def"
        if [[ -n "$XPLANET_BIN" ]]; then
            names+=("${XPLANET_BIN:t}" "${XPLANET_BIN:A:t}")
        fi
    fi
    local scene_names
    scene_names=$(scene_renderer_names)
    [[ -z "$scene_names" ]] || names+=("${(@f)scene_names}")
    local -A seen
    for name in ${(u)names}; do
        # pgrep takes an ERE even with -x; configured names are literal.
        pattern=''
        for character in ${(s::)name}; do
            case "$character" in
                ('.'|'['|']'|'('|')'|'{'|'}'|'*'|'+'|'?'|'^'|'$'|'|'|'\')
                    pattern+="\\$character" ;;
                (*) pattern+="$character" ;;
            esac
        done
        listing=$(pgrep -u "$EUID" -x "$pattern")
        result=$?
        (( result == 1 )) && continue
        (( result == 0 )) || return 2
        for pid in ${(f)listing}; do
            [[ "$pid" == <-> ]] || return 2
            if [[ -z "${seen[$pid]:-}" ]]; then
                print -- "$pid"
                seen[$pid]=1
            fi
        done
    done
}

_stop_xplanet() {
    local listing pid remaining attempt kill_bin job_error=0
    kill_bin=$(whence -p kill) || fail "cannot locate the PID-specific kill command"
    [[ "$kill_bin" == /* && -x "$kill_bin" ]] ||
        fail "cannot use the PID-specific kill command"
    # Remove the managed job before broad termination so a queued start cannot
    # recreate it. No KeepAlive or background supervisor respawns the renderer.
    if launchctl list "$desktop_label" >/dev/null 2>&1; then
        launchctl bootout "$desktop_domain/$desktop_label" || job_error=1
    fi
    listing=$(xplanet_pids) || fail "could not inspect this user's Xplanet processes"
    if [[ -z "$listing" ]]; then
        (( job_error == 0 )) || fail "Xplanet processes stopped, but desktop job removal failed; review launchctl before starting again"
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
    (( job_error == 0 )) || fail "Xplanet processes stopped, but desktop job removal failed; review launchctl before starting again"
    [[ "${1:-}" == quiet ]] || interactive_note "Xplanet display stopped."
}

_restart_xplanet() {
    _stop_xplanet quiet || return $?
    _start_xplanet
}

start_xplanet() { desktop_lifecycle _start_xplanet "$@"; }
stop_xplanet() { desktop_lifecycle _stop_xplanet "$@"; }
restart_xplanet() { desktop_lifecycle _restart_xplanet "$@"; }
