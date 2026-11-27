wallpaper_cleanup_help() {
    cat <<'HELP'
Usage: xplanet.sh cleanup [--dry-run|--help]
       xplanet.sh restart --cleanup

Preview and interactively remove old, positively identified Xplanet PNG and BMP
wallpaper cache files. Your Photos entries and active frames are not removed.
Run cleanup in Terminal after stopping Xplanet, or use
restart --cleanup to confirm first, then stop, clean and start.
--dry-run only reports candidates and does not require Xplanet to stop.
Plain restart never cleans wallpaper files. Do not run through launchd or sudo.
HELP
}

wallpaper_cleanup_python() {
    local python
    python=$("$script_dir/run-totalmarker" --python-path) || return $?
    "$python" -I -B "$script_dir/lib/xplanet/wallpaper-cleanup.py" "$@"
}

wallpaper_cleanup_require_terminal() {
    [[ -t 0 && -t 2 ]] || fail "wallpaper cleanup requires Terminal; use cleanup --dry-run for a report"
}

wallpaper_cleanup_assert_stopped() {
    local listing
    desktop_agent_paths read
    launchctl print "$desktop_domain" >/dev/null 2>&1 ||
        fail "cannot verify the current GUI launchd session"
    if launchctl print "$desktop_domain/$desktop_label" >/dev/null 2>&1; then
        fail "stop the desktop first, or use restart --cleanup"
    fi
    listing=$(xplanet_pids) || fail "could not inspect this user's Xplanet processes"
    [[ -z "$listing" ]] || fail "stop Xplanet first, or use restart --cleanup"
}

wallpaper_cleanup_transaction() (
    local mode=$1 workspace result runtime
    wallpaper_cleanup_require_terminal
    runtime=$(/usr/bin/getconf DARWIN_USER_TEMP_DIR) || return 1
    runtime=${runtime:A}
    [[ "$runtime" == /private/var/folders/*/T && -d "$runtime" && -O "$runtime" ]] ||
        fail "cannot verify the private runtime directory for cleanup"
    workspace=$(/usr/bin/mktemp -d "$runtime/xplanet-cleanup.XXXXXXXX") || return 1
    trap '/bin/rm -f -- "$workspace/plan"; /bin/rmdir -- "$workspace"' EXIT
    if [[ "$mode" == standalone ]]; then
        wallpaper_cleanup_assert_stopped
    fi
    wallpaper_cleanup_python prepare "$workspace/plan"
    result=$?
    case "$result" in
        0) ;;
        3) [[ "$mode" != restart ]] || _restart_xplanet; return $? ;;
        4) return 0 ;;
        *) return "$result" ;;
    esac
    if [[ "$mode" == standalone ]]; then
        wallpaper_cleanup_assert_stopped
        wallpaper_cleanup_python apply "$workspace/plan"
    else
        _restart_xplanet "$workspace/plan"
    fi
)

cleanup_xplanet() {
    case "${1:-}" in
        --help|-h) (( $# == 1 )) || fail "cleanup accepts only --dry-run or --help"; wallpaper_cleanup_help ;;
        --dry-run) (( $# == 1 )) || fail "cleanup accepts only --dry-run or --help"; wallpaper_cleanup_python preview ;;
        '') (( $# == 0 )) || fail "cleanup accepts only --dry-run or --help"; desktop_lifecycle wallpaper_cleanup_transaction standalone ;;
        *) fail "cleanup accepts only --dry-run or --help" ;;
    esac
}
