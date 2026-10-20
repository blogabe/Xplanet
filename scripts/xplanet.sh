#!/bin/zsh

set -u
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)

fail() {
    print -u2 -- "xplanet.sh: $1"
    exit 2
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

usage() {
    cat <<'USAGE'
Usage: scripts/xplanet.sh COMMAND [SETUP_OPTION]

  install    Install Xplanet and Python, offer approval run, then run setup
  setup      Prompt for preparation, marker refresh and optional automation
  update     Fast-forward the configured Git upstream if local files allow

  start      Launch the configured Xplanet display with -fork
  stop       Stop Xplanet processes with killall
  preview    Render one 1920x1080 Earth frame to dev/preview/earth-manual.png
  render     Render one configured-size Earth frame to dev/preview/earth-render.png

  earth      Select the current month's configured Earth map link
  clouds     Fetch the live cloud image through Python TotalMarker
  quake      Fetch USGS GeoJSON through Python TotalMarker
  volcano    Fetch the live GVP CAP feed through Python TotalMarker
  storm      Fetch worldwide tropical-cyclone markers and tracks
  label      Refresh the cloud update label offline (alias: labels)

  norad      Update optional, explicitly selected NORAD satellite files
  eclipse    Update optional NASA central eclipse markers and arcs

  santa      STUB: Santa foundation; Xplanet invocation-time on/off is pending

  test       Run the offline Python regression suite

Install runs before the interactive setup and may request macOS security approvals.
Update fetches only the current branch's configured upstream and refuses local
tracked changes or untracked/ignored file collisions. It runs no setup steps.
Setup delegates to xp-setup.sh. Use setup --dry-run or setup --check to inspect;
these modes inspect working-directory preparation only. Without an option,
setup prompts before preparation, live marker refresh and launchd activation.
Setup installs no packages or virtual environment.
Start detaches Xplanet; stop runs killall xplanet for all permitted matches.
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
        load_render_config
        [[ "$XPLANET_CONFIG" == "$project_root/config" ]] ||
            fail "xp.def XPLANET_CONFIG must match this project's config directory"
        "$XPLANET_BIN" \
            "-searchdir=$XPLANET_HOME" \
            "-config=$XPLANET_CONFIG/xp.conf" \
            "-projection=$XPLANET_PROJECTION" \
            "-longitude=$XPLANET_LONGITUDE" \
            -labelpos=+10-45 \
            '-date_format=%D at %r' \
            -color=green2 \
            -fork
        ;;
    stop)
        killall xplanet
        ;;
    earth)
        select_earth_map
        ;;
    label|labels)
        "$script_dir/run-totalmarker" labels
        ;;
    clouds)
        print -- "Fetching the live cloud image with Python TotalMarker."
        "$script_dir/run-totalmarker" clouds
        ;;
    quake)
        print -- "Fetching live USGS earthquake data with Python TotalMarker."
        "$script_dir/run-totalmarker" quake
        ;;
    storm)
        print -- "Fetching worldwide storm positions and tracks with Python TotalMarker."
        "$script_dir/run-totalmarker" storm
        ;;
    volcano)
        print -- "Fetching the live weekly volcano feed with Python TotalMarker."
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
