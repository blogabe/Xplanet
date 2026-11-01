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
    bootstrap_git=$(command -v git) || {
        print -u2 -- "xplanet.sh: Git is required for bootstrap"
        exit 2
    }
    "$bootstrap_git" check-ref-format --branch "$bootstrap_ref" >/dev/null 2>&1 || {
        print -u2 -- "xplanet.sh: invalid repository branch or tag in XPLANET_BOOTSTRAP_REF"
        exit 2
    }
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

usage() {
    cat <<'USAGE'
Usage: scripts/xplanet.sh COMMAND [OPTIONS]

  bootstrap  Clone into ~/.xplanet, then run install (Homebrew required)
  install    Install Xplanet and Python, offer approval run, then run setup
  setup      Prompt for preparation, marker refresh and optional automation
  update     Fast-forward Git, then check the blogabe Xplanet tap formula

  start      Start the launchd-owned foreground Xplanet display
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
  log-trim   Trim recognized event logs older than 30 days; --dry-run, --days N
  health     Read saved source health; --live probes without updating outputs
             Use --verbose for details or --json for structured results

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
Start uses one desktop job without automatic respawn. Stop removes that job and
stops ALL this user's Xplanet processes, including finite renders; restart
waits for them to exit before starting one display. A formula reinstall restarts
the display only if Xplanet was running before the rebuild.
USAGE
}

if (( $# > 1 )) && [[ "$1" != setup && "$1" != health && "$1" != log-trim ]]; then
    fail "expected exactly one command; use --help"
fi
if (( $# == 0 )); then
    switch=help
else
    switch=$1
fi

# Load only the macOS workflow needed by this command. Bootstrap above must
# remain standalone: its downloaded entry has no checkout-local helper files.
load_helpers() {
    local helper
    for helper in "$@"; do
        [[ -f "$script_dir/lib/xplanet/$helper.zsh" ]] ||
            fail "missing $helper helpers; restore the complete checkout"
        source "$script_dir/lib/xplanet/$helper.zsh" ||
            fail "could not load $helper helpers"
    done
}
case "$switch" in
    install) load_helpers install ;;
    update) load_helpers display update ;;
    preview|render|start|restart|stop|earth) load_helpers display ;;
esac

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
        mkdir -p "$project_root/dev/preview/tmp" "$project_root/dev/preview/cache" ||
            fail "cannot create project-local preview directories"
        TMPDIR="$project_root/dev/preview/tmp" \
        XDG_CACHE_HOME="$project_root/dev/preview/cache" \
        render_frame 1920x1080 "$project_root/dev/preview/earth-manual.png" \
            "$project_root/dev/preview/tmp"
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
    log-trim)
        shift
        "$script_dir/run-totalmarker" log-trim "$@"
        ;;
    health)
        shift
        "$script_dir/run-totalmarker" health "$@"
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
