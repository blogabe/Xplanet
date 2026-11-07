#!/bin/zsh
emulate -R zsh

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
script_dir=$(CDPATH= cd -- "$(dirname -- "${0:A}")" && pwd -P)
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
Usage: scripts/xplanet.sh [COMMAND [OPTIONS]]

With no command, an interactive terminal opens management.
Redirected input or output prints usage instead.

Explore and configure
  config       Open the scene studio; save and selection are separate
  preview      Render one custom Earth frame at 1920x1080
               Output: dev/preview/earth-manual.png
  render       Render one custom Earth frame at the configured size
               Output: dev/preview/earth-render.png

Install and maintain
  bootstrap    Clone into ~/.xplanet, then run install (Homebrew required)
  install      Install Xplanet and Python, offer approval run, then setup
  setup        Prepare files, refresh markers and register optional automation
  update       Fast-forward Git, then check the blogabe Xplanet tap formula

Control the desktop
  start        Start the launchd-owned foreground display
  stop         Stop ALL this user's Xplanet processes
               Includes finite renders
  restart      Stop, wait for exit, then start one display
  earth        Select the current month's configured Earth map link

Refresh data (Python TotalMarker)
  clouds       Fetch the live cloud image
  quake        Fetch USGS earthquake GeoJSON
  storm        Fetch worldwide tropical-cyclone markers and tracks
  volcano      Refresh markers from configured CAP or GVP weekly HTML
  norad        Update optional, explicitly selected NORAD satellite files
  eclipse      Update optional NASA central eclipse markers and arcs
  label        Refresh update labels without fetching (alias: labels)

Inspect and troubleshoot
  log-view     Read stderr; count repeat resize notices without changing logs
               --file PATH selects another text log within this checkout
  health       Read saved health; --live probes without updating outputs
               --verbose shows details; --json returns structured results
  diagnostics  Capture selected renderer support; --show reads saved evidence
               --renderer /absolute/path/to/xplanet works before setup

Housekeeping and development
  log-trim     Trim recognized logs older than 30 days; --dry-run, --days N
  test         Run the offline Python regression suite

Unavailable
  santa        STUB: invocation-time Santa on/off is pending

Detailed help: config --help, config --guide, setup --help, health --help,
               diagnostics --help, log-view --help, log-trim --help
Use config --prepare to prepare the isolated scene-studio UI environment.

Workflow notes (macOS)
  Install may request macOS security approvals. Setup installs no packages
  or virtual environment; it delegates to xp-setup.sh and prompts before
  file preparation, live marker refresh and launchd activation.
  setup --dry-run and setup --check inspect directory preparation only.
  setup --check-handoff DIR checks a scene bundle without preparing files
  or changing jobs.

  Update uses only the current branch's upstream. It refuses tracked changes
  and untracked/ignored collisions, then updates Homebrew tap metadata. It
  rebuilds only when this tap's formula recipe changes; no setup runs. A
  formula reinstall restarts the display only if Xplanet was already
  running.

  Without a selector, start uses custom configuration. An invalid selected
  revision fails instead of falling back. Apply never restarts; start uses
  one job with no automatic respawn. Stop removes it and stops ALL this
  user's Xplanet processes. Restart waits for exit before starting one
  display.
USAGE
}

if (( $# > 1 )) && [[ "$1" != setup && "$1" != health && "$1" != log-trim && "$1" != log-view && "$1" != config && "$1" != diagnostics ]]; then
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
if (( $# == 0 )) && [[ -t 0 && -t 1 ]]; then
    load_helpers management
    manage_xplanet
    exit $?
fi
case "$switch" in
    config) load_helpers configurator ;;
    diagnostics) load_helpers diagnostics ;;
    install) load_helpers install ;;
    update) load_helpers display update ;;
    preview|render|start|restart|stop|earth) load_helpers display ;;
esac

case "$switch" in
    help|-h|--help)
        usage
        ;;
    diagnostics)
        shift
        renderer_diagnostics "$@"
        ;;
    config)
        shift
        configure_xplanet "$@"
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
    log-view|log-trim)
        shift
        "$script_dir/run-totalmarker" "$switch" "$@"
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
