#!/bin/zsh

set -u

# A downloaded entry point has no checkout-local dependencies yet.
if [[ "${1:-}" == bootstrap ]]; then
    if (( $# != 1 )); then
        print -u2 -- "xplanet.sh: bootstrap takes no arguments"
        exit 2
    fi
    bootstrap_ref=${XPLANET_BOOTSTRAP_REF:-main}
    if [[ ! "$bootstrap_ref" =~ '^[A-Za-z0-9][A-Za-z0-9._/-]*$' ]]; then
        print -u2 -- "xplanet.sh: invalid XPLANET_BOOTSTRAP_REF"
        exit 2
    fi
    bootstrap_tmp=$(mktemp -d "${TMPDIR:-/tmp}/xplanet-bootstrap.XXXXXXXX") || exit 1
    trap 'rm -rf -- "$bootstrap_tmp"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --output "$bootstrap_tmp/xp-bootstrap.sh" \
        "https://raw.githubusercontent.com/blogabe/Xplanet/$bootstrap_ref/scripts/xp-bootstrap.sh" || exit 1
    /bin/zsh "$bootstrap_tmp/xp-bootstrap.sh" "$bootstrap_ref"
    exit $?
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)

fail() {
    print -u2 -- "xplanet.sh: $1"
    exit 2
}

interactive_note() {
    if [[ -t 1 ]]; then
        print -- "$1"
    fi
}

install_failed() {
    print -u2 -- "xplanet.sh install: $1"
    exit 1
}

ask_install() {
    local answer
    read -r "answer?$1 [y/N] " || return 1
    [[ "$answer" == [Yy] ]]
}

install_xplanet() {
    local brew_bin prefix installed
    brew_bin=$(command -v brew) || fail "Homebrew is required for install"
    [[ "$brew_bin" == /* && -x "$brew_bin" ]] || fail "Homebrew must be an executable on PATH"
    "$brew_bin" tap blogabe/xplanet || install_failed "Could not add the Xplanet tap."
    "$brew_bin" trust blogabe/xplanet ||
        install_failed "Could not trust the Xplanet tap; this Homebrew may not support 'brew trust'."
    "$brew_bin" install --formula --build-from-source blogabe/xplanet/xplanet \
        --without-giflib --with-cspice ||
        install_failed "Could not build Xplanet from the tap source."
    "$brew_bin" install python || install_failed "Could not install Homebrew Python."
    prefix=$("$brew_bin" --prefix blogabe/xplanet/xplanet) ||
        install_failed "Could not locate the installed Xplanet formula."
    [[ "$prefix" == /* ]] || install_failed "Homebrew returned a non-absolute Xplanet prefix."
    installed="$prefix/bin/xplanet"
    [[ -x "$installed" ]] || install_failed "Homebrew Xplanet binary is not executable at $installed."
    print -- "macOS may request security approval during a finite Xplanet launch. Review any prompts yourself."
    if ask_install "Run one Xplanet frame now to request macOS approvals?"; then
        (cd "$project_root" && "$installed" "-searchdir=$project_root" -num_times=1) ||
            install_failed "The one-frame Xplanet launch failed."
    else
        print -- "Skipped the approval launch; macOS permissions still need manual review."
    fi
    print -- "Xplanet and Python installation steps finished. Continuing to setup."
    XPLANET_INSTALLED_BIN="$installed" "$script_dir/xp-setup.sh"
}

update_repository() {
    local git_bin branch remote source_ref current_root dirty target starting_head
    git_bin=$(command -v git) || fail "Git is required for update"
    current_root=$("$git_bin" -C "$project_root" rev-parse --show-toplevel) ||
        fail "update requires a Git checkout"
    [[ "$current_root" == "$project_root" ]] ||
        fail "update must run from this project's checkout root"
    branch=$("$git_bin" -C "$project_root" symbolic-ref --quiet --short HEAD) ||
        fail "update requires a checked-out branch"
    starting_head=$("$git_bin" -C "$project_root" rev-parse --verify 'HEAD^{commit}') ||
        fail "could not inspect the current commit"
    remote=$("$git_bin" -C "$project_root" config --get "branch.$branch.remote") ||
        fail "branch $branch has no configured upstream remote"
    source_ref=$("$git_bin" -C "$project_root" config --get "branch.$branch.merge") ||
        fail "branch $branch has no configured upstream branch"
    [[ "$remote" != . && "$source_ref" == refs/heads/* ]] ||
        fail "update requires a remote branch upstream"
    "$git_bin" -C "$project_root" remote get-url "$remote" >/dev/null ||
        fail "configured upstream remote $remote is unavailable"
    dirty=$("$git_bin" -C "$project_root" status --porcelain=v1 --untracked-files=no) ||
        fail "could not inspect local changes"
    [[ -z "$dirty" ]] || fail "local tracked changes exist; commit or handle them before update"
    print -- "Checking the configured Git upstream..."
    "$git_bin" -C "$project_root" fetch --no-tags --no-recurse-submodules \
        --refmap= "$remote" "$source_ref" || fail "could not fetch configured upstream"
    target=$("$git_bin" -C "$project_root" rev-parse --verify 'FETCH_HEAD^{commit}') ||
        fail "fetched upstream is not a commit"
    [[ "$("$git_bin" -C "$project_root" symbolic-ref --quiet --short HEAD)" == "$branch" &&
       "$("$git_bin" -C "$project_root" rev-parse --verify 'HEAD^{commit}')" == "$starting_head" ]] ||
        fail "checkout changed during fetch; update stopped"
    [[ "$("$git_bin" -C "$project_root" config --get "branch.$branch.remote")" == "$remote" &&
       "$("$git_bin" -C "$project_root" config --get "branch.$branch.merge")" == "$source_ref" ]] ||
        fail "upstream changed during fetch; update stopped"
    dirty=$("$git_bin" -C "$project_root" status --porcelain=v1 --untracked-files=no) ||
        fail "could not recheck local changes"
    [[ -z "$dirty" ]] || fail "local tracked changes appeared during fetch; update stopped"
    "$git_bin" -C "$project_root" merge-base --is-ancestor "$starting_head" "$target" ||
        fail "upstream diverged; update requires a fast-forward"
    "$git_bin" -C "$project_root" -c core.hooksPath=/dev/null \
        merge --ff-only --no-autostash \
        --no-overwrite-ignore "$target" ||
        fail "fast-forward blocked by local files or another checkout change"
}

update_tap_formula() {
    local brew_bin git_bin tap_root prefix receipt formula_path installed_path
    local installed_commit installed_blob current_blob installed_rel current_rel
    local installed_tap count option index refreshed_prefix refreshed_receipt
    local refreshed_commit refreshed_blob tap_dirty running_before
    local -a options
    brew_bin=$(command -v brew) || fail "Git checkout updated, but Homebrew is unavailable; the Xplanet formula was not checked"
    [[ "$brew_bin" == /* && -x "$brew_bin" ]] || fail "Homebrew must be an executable on PATH"
    git_bin=$(command -v git) || fail "Git is required to compare the installed Xplanet formula"
    command -v plutil >/dev/null || fail "macOS plutil is required to read the installed Xplanet receipt"
    print -- "Checking the blogabe/xplanet Homebrew formula..."
    "$brew_bin" update || fail "Git checkout updated, but Homebrew could not update its taps; Xplanet was not reinstalled"
    tap_root=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --repository blogabe/xplanet) ||
        fail "the blogabe/xplanet tap is unavailable"
    prefix=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --prefix --installed blogabe/xplanet/xplanet) ||
        fail "the tap's Xplanet formula is not installed; use install"
    formula_path=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" formula blogabe/xplanet/xplanet) ||
        fail "the tap's Xplanet formula is unavailable"
    [[ "$tap_root" == /* && -d "$tap_root" && "$prefix" == /* &&
       "$formula_path" == "$tap_root/"* ]] || fail "Homebrew returned an unexpected tap or formula path"
    receipt="$prefix/INSTALL_RECEIPT.json"
    [[ -f "$receipt" ]] || fail "installed Xplanet has no Homebrew receipt; cannot verify its build"
    installed_tap=$(plutil -extract source.tap raw -o - "$receipt") ||
        fail "installed Xplanet receipt has no tap identity"
    [[ "$installed_tap" == blogabe/xplanet ]] ||
        fail "installed Xplanet came from $installed_tap, not blogabe/xplanet; refusing to switch formula"
    installed_path=$(plutil -extract source.path raw -o - "$receipt") ||
        fail "installed Xplanet receipt has no formula path"
    installed_commit=$(plutil -extract source.tap_git_head raw -o - "$receipt") ||
        fail "installed Xplanet receipt has no tap commit; review its build options and reinstall manually"
    [[ "$installed_path" == "$tap_root/"* &&
       "$installed_commit" =~ '^[0-9a-f]{40,64}$' ]] ||
        fail "installed Xplanet formula provenance is not verifiable"
    installed_rel="${installed_path#$tap_root/}"
    current_rel="${formula_path#$tap_root/}"
    [[ "$installed_rel" == xplanet.rb || "$installed_rel" == Formula/xplanet.rb ]] ||
        fail "installed Xplanet receipt names an unexpected formula file"
    [[ "$current_rel" == xplanet.rb || "$current_rel" == Formula/xplanet.rb ]] ||
        fail "the tap names an unexpected Xplanet formula file"
    tap_dirty=$("$git_bin" -C "$tap_root" status --porcelain=v1 -- "$current_rel") ||
        fail "could not inspect the tap formula checkout"
    [[ -z "$tap_dirty" ]] ||
        fail "the tap formula has local changes; refusing to reinstall from an uncommitted recipe"
    # Tap HEAD can advance for unrelated commits; compare the committed formula bytes.
    installed_blob=$("$git_bin" -C "$tap_root" rev-parse --verify "$installed_commit:$installed_rel") ||
        fail "installed Xplanet formula commit is unavailable; review its build options and reinstall manually"
    current_blob=$("$git_bin" -C "$tap_root" rev-parse --verify "HEAD:$current_rel") ||
        fail "current tap formula is not committed; cannot compare recipes"
    if [[ "$installed_blob" == "$current_blob" ]]; then
        print -- "Xplanet tap formula unchanged; no reinstall needed."
        return 0
    fi
    count=$(plutil -extract used_options raw -o - "$receipt") ||
        fail "installed Xplanet build options are unavailable; refusing to lose them"
    [[ "$count" == <-> && "$count" -le 32 ]] ||
        fail "installed Xplanet build options are invalid"
    options=()
    for ((index = 0; index < count; index++)); do
        option=$(plutil -extract "used_options.$index" raw -o - "$receipt") ||
            fail "could not read installed Xplanet build option $index"
        [[ "$option" =~ '^--(with|without)-[A-Za-z0-9-]+$' ]] ||
            fail "installed Xplanet build option is not supported for automatic reinstall: $option"
        options+=("$option")
    done
    running_before=$(xplanet_pids) ||
        fail "could not inspect this user's Xplanet processes before reinstall"
    print -- "Xplanet tap formula changed; rebuilding from source with installed options."
    HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" reinstall --formula --build-from-source \
        blogabe/xplanet/xplanet "${options[@]}" ||
        fail "Xplanet formula reinstall failed; the Git checkout may already be updated"
    refreshed_prefix=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --prefix --installed blogabe/xplanet/xplanet) ||
        fail "Xplanet reinstall returned success, but no installed formula was found"
    refreshed_receipt="$refreshed_prefix/INSTALL_RECEIPT.json"
    [[ -f "$refreshed_receipt" ]] ||
        fail "Xplanet reinstall returned success without an installed receipt"
    [[ "$(plutil -extract source.tap raw -o - "$refreshed_receipt")" == blogabe/xplanet ]] ||
        fail "Xplanet reinstall did not retain the blogabe/xplanet tap"
    refreshed_commit=$(plutil -extract source.tap_git_head raw -o - "$refreshed_receipt") ||
        fail "Xplanet reinstall did not record tap provenance"
    refreshed_blob=$("$git_bin" -C "$tap_root" rev-parse --verify "$refreshed_commit:$current_rel") ||
        fail "Xplanet reinstall provenance cannot be verified"
    [[ "$refreshed_blob" == "$current_blob" ]] ||
        fail "Xplanet reinstall did not record the updated formula; check Homebrew before retrying"
    print -- "Xplanet tap formula reinstall verified."
    if [[ -n "$running_before" ]]; then
        print -- "Restarting the running Xplanet display with the updated formula..."
        restart_xplanet || fail "Xplanet was reinstalled, but the display could not be restarted"
    fi
}

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

usage() {
    cat <<'USAGE'
Usage: scripts/xplanet.sh COMMAND [SETUP_OPTION]

  bootstrap  Clone into ~/.xplanet, then run install (Homebrew required)
  install    Install Xplanet and Python, offer approval run, then run setup
  setup      Prompt for preparation, marker refresh and optional automation
  update     Fast-forward Git, then check the blogabe Xplanet tap formula

  start      Launch the configured Xplanet display with -fork
  stop       Stop this user's Xplanet processes
  restart    Stop and start Xplanet; start if it was not running
  preview    Render one 1920x1080 Earth frame to dev/preview/earth-manual.png
  render     Render one configured-size Earth frame to dev/preview/earth-render.png

  earth      Select the current month's configured Earth map link
  clouds     Fetch the live cloud image through Python TotalMarker
  quake      Fetch USGS GeoJSON through Python TotalMarker
  volcano    Refresh volcano markers from configured CAP or GVP weekly HTML
  storm      Fetch worldwide tropical-cyclone markers and tracks
  label      Refresh product update labels without fetching (alias: labels)

  norad      Update optional, explicitly selected NORAD satellite files
  eclipse    Update optional NASA central eclipse markers and arcs

  santa      STUB: Santa foundation; Xplanet invocation-time on/off is pending

  test       Run the offline Python regression suite

Install runs before the interactive setup and may request macOS security approvals.
Update fetches only the current branch's configured upstream and refuses local
tracked changes or untracked/ignored file collisions. It then updates Homebrew
tap metadata and rebuilds Xplanet only when this tap's formula recipe changed.
It runs no setup steps.
Setup delegates to xp-setup.sh. Use setup --dry-run or setup --check to inspect;
these modes inspect working-directory preparation only. Without an option,
setup prompts before preparation, live marker refresh and launchd activation.
Setup installs no packages or virtual environment.
Start detaches Xplanet. Stop targets this user's Xplanet processes; restart
waits for them to exit before starting one display. A formula reinstall restarts
the display only if Xplanet was running before the rebuild.
USAGE
}

if (( $# > 1 )) && [[ "$1" != setup ]]; then
    fail "expected exactly one command; use --help"
fi
if (( $# == 0 )); then
    switch=help
else
    switch=$1
fi

case "$switch" in
    help|-h|--help)
        usage
        ;;
    install)
        install_xplanet
        ;;
    update)
        update_repository
        update_tap_formula
        ;;
    test)
        "$script_dir/run-totalmarker" --test
        ;;
    preview)
        load_render_config
        mkdir -p "$project_root/dev/preview" "$project_root/.state/totalmarker" ||
            fail "cannot create project-local preview directories"
        render_frame 1920x1080 "$project_root/dev/preview/earth-manual.png" \
            "$project_root/.state/totalmarker"
        ;;
    render)
        load_render_config
        [[ -n "$XPLANET_GEOMETRY" ]] || fail "xp.def XPLANET_GEOMETRY is required for render"
        mkdir -p "$project_root/dev/preview/tmp" "$project_root/dev/preview/cache" ||
            fail "cannot create project-local render directories"
        TMPDIR="$project_root/dev/preview/tmp" \
        XDG_CACHE_HOME="$project_root/dev/preview/cache" \
        render_frame "$XPLANET_GEOMETRY" "$project_root/dev/preview/earth-render.png" \
            "$project_root/dev/preview/tmp"
        ;;
    start)
        start_xplanet
        ;;
    restart)
        restart_xplanet
        ;;
    stop)
        stop_xplanet
        ;;
    earth)
        select_earth_map
        ;;
    label|labels)
        "$script_dir/run-totalmarker" labels
        ;;
    clouds)
        interactive_note "Fetching the live cloud image with Python TotalMarker."
        "$script_dir/run-totalmarker" clouds
        ;;
    quake)
        interactive_note "Fetching live USGS earthquake data with Python TotalMarker."
        "$script_dir/run-totalmarker" quake
        ;;
    storm)
        interactive_note "Fetching worldwide storm positions and tracks with Python TotalMarker."
        "$script_dir/run-totalmarker" storm
        ;;
    volcano)
        interactive_note "Fetching the live weekly volcano feed with Python TotalMarker."
        "$script_dir/run-totalmarker" volcano
        ;;
    norad)
        "$script_dir/run-totalmarker" norad
        ;;
    eclipse)
        "$script_dir/run-totalmarker" eclipse
        ;;
    santa)
        # Stub only: Santa is intended as an on/off choice when Xplanet starts.
        # Invocation-time integration and a verified live provider are pending.
        "$script_dir/run-totalmarker" santa
        ;;
    setup)
        shift
        "$script_dir/xp-setup.sh" "$@"
        ;;
    *)
        usage >&2
        fail "unknown command: $switch"
        ;;
esac
