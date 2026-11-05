# Explicit support inspection only. Never sourced by start/restart.
renderer_diagnostics() (
    local renderer='' show=false python_bin
    if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
        (( $# == 1 )) || fail "diagnostics --help takes no other arguments"
        print -- 'Usage: scripts/xplanet.sh diagnostics [--renderer /absolute/path/to/xplanet] [--show]'
        print -- 'Capture bounded version/support evidence explicitly; --show reads prior evidence only.'
        print -- 'No renderer or Python is invoked by this help. See docs/configurator/diagnostics.md.'
        return 0
    fi
    while (( $# )); do
        case "$1" in
            --renderer) (( $# >= 2 )) || fail "--renderer needs an absolute executable path"
                renderer=$2
                [[ -n "$renderer" ]] || fail "--renderer needs an absolute executable path"
                shift 2 ;;
            --show) show=true; shift ;;
            *) fail "diagnostics accepts --show and --renderer /absolute/path/to/xplanet" ;;
        esac
    done
    if [[ -z "$renderer" ]]; then
        if [[ -e "$project_root/config/desktop.scene" || -L "$project_root/config/desktop.scene" || -e "$project_root/config/xp.def" ]]; then
            load_helpers display
            local -a desktop_args
            desktop_command
            renderer=$XPLANET_BIN
            print -- "Resolved the renderer configured for next start; running-process identity is not inspected."
        else
            renderer=$(command -v xplanet) || fail "no configured renderer; use diagnostics --renderer /absolute/path/to/xplanet"
            print -- "No desktop configuration: inspecting the Xplanet found on PATH, not an installed desktop selection."
        fi
    fi
    [[ "$renderer" == /* ]] || fail "diagnostic renderer must be an absolute path"
    python_bin=$("$script_dir/run-totalmarker" --python-path) || return $?
    if [[ "$show" == true ]]; then
        PYTHONPATH="$script_dir" PYTHONDONTWRITEBYTECODE=1 "$python_bin" -P -s -B -m configurator.binary_diagnostics --root "$project_root" --renderer "$renderer" --show
    else
        PYTHONPATH="$script_dir" PYTHONDONTWRITEBYTECODE=1 "$python_bin" -P -s -B -m configurator.binary_diagnostics --root "$project_root" --renderer "$renderer"
    fi
)
