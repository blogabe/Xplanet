# TotalMarker interpreter choices only. Providers own installation and upgrades.
python_brew() {
    local brew
    brew=$(command -v brew 2>/dev/null)
    if [[ -n "$brew" ]]; then
        [[ "$brew" == /* && -x "$brew" ]] || return 1
        print -r -- "$brew"
        return 0
    fi
    # Fresh shells may not yet include an installed Homebrew in PATH.
    for brew in /opt/homebrew/bin/brew /usr/local/bin/brew "$HOME/.homebrew/bin/brew"; do
        if [[ -x "$brew" && -f "$brew" ]]; then
            print -r -- "$brew"
            return 0
        fi
    done
    return 1
}

python_uv() {
    local uv brew prefix
    uv=$(command -v uv 2>/dev/null)
    if [[ "$uv" == /* && -x "$uv" ]]; then
        print -r -- "$uv"
        return 0
    fi
    brew=$(python_brew) || return 1
    prefix=$("$brew" --prefix uv 2>/dev/null) || return 1
    [[ "$prefix" == /* && -x "$prefix/bin/uv" ]] || return 1
    print -r -- "$prefix/bin/uv"
}

python_provider_find() {
    local candidate prefix brew uv
    case "$1" in
        homebrew)
            brew=$(python_brew) || return 1
            prefix=$("$brew" --prefix python 2>/dev/null) || return 1
            [[ "$prefix" == /* ]] || return 1
            candidate="$prefix/bin/python3" ;;
        uv)
            uv=$(python_uv) || return 1
            candidate=$("$uv" --no-config --offline --no-python-downloads python find \
                --managed-python --system --no-project '>=3.11' 2>/dev/null) || return 1 ;;
        *) return 2 ;;
    esac
    [[ "$candidate" == /* ]] || return 1
    TOTALMARKER_PYTHON="$candidate" "$script_dir/run-totalmarker" --python-path
}

python_provider_install() {
    local brew uv
    case "$1" in
        homebrew)
            brew=$(python_brew) || { print -u2 -- 'Homebrew is required to install Python.'; return 1; }
            "$brew" install python || return 1 ;;
        uv)
            uv=$(python_uv) || {
                brew=$(python_brew) || { print -u2 -- 'Install uv separately or make Homebrew available.'; return 1; }
                "$brew" install uv || return 1
                uv=$(python_uv) || return 1
            }
            # No versioned executable links or shell/PATH modifications.
            "$uv" --no-config python install --no-bin '>=3.11' || return 1 ;;
        *) return 2 ;;
    esac
    python_provider_find "$1" >/dev/null
}

python_save_selection() {
    local candidate=$1 temporary selection="$project_root/config/totalmarker.python"
    [[ "${2:-}" == '' || "${2:-}" == --if-missing ]] || return 2
    [[ "$candidate" == /* && "$candidate" != *$'\n'* && "$candidate" != *$'\r'* ]] || return 2
    # An explicit environment override remains authoritative; never hide it.
    if (( ${+TOTALMARKER_PYTHON} )); then
        print -u2 -- 'TOTALMARKER_PYTHON is set. Unset it before changing the project selection.'
        return 2
    fi
    TOTALMARKER_PYTHON="$candidate" "$script_dir/run-totalmarker" --python-path >/dev/null || return 1
    [[ ! -L "$selection" && ( ! -e "$selection" || -f "$selection" ) ]] || return 1
    mkdir -p -- "$project_root/config" || return 1
    [[ -d "$project_root/config" && ! -L "$project_root/config" ]] || return 1
    temporary=$(mktemp "$project_root/config/.totalmarker.python.XXXXXXXX") || return 1
    {
        print -r -- "$candidate" > "$temporary" || return 1
        if [[ "${2:-}" == --if-missing ]]; then
            ln -- "$temporary" "$selection"
        else
            mv -f -- "$temporary" "$selection"
        fi
    } always {
        [[ ! -f "$temporary" ]] || rm -f -- "$temporary"
    }
}

# Interactive selection is explicit; discovery and merely opening management never install.
python_choose_runtime() {
    local reply provider candidate='' current
    if (( ${+TOTALMARKER_PYTHON} )); then
        print -- "TOTALMARKER_PYTHON overrides this installation. Unset it before selecting a provider."
        return 2
    fi
    current=$("$script_dir/run-totalmarker" --python-path 2>/dev/null)
    if [[ -n "$current" ]]; then
        print -r -- "Current compatible interpreter: $current"
    else
        print -- 'No compatible interpreter selected or found (Python 3.11+ required).'
        print -- 'An installed older Python, including Apple Python 3.9, is not eligible.'
    fi
    if [[ "${1:-}" == change ]]; then
        print -- 'Change this only when your runtime needs change. Normal updates preserve the selection.'
        read -r 'reply?Change the TotalMarker interpreter/provider? [y/N] ' || return 3
        [[ "$reply" == [Yy] ]] || return 3
    fi
    print -- '  1) Homebrew (recommended)'
    print -- '  2) uv-managed Python'
    [[ -n "$current" && "${1:-}" != change ]] && print -- '  k) Keep current compatible interpreter'
    print -- '  q) Cancel'
    read -r 'reply?Python provider [1]: ' || return 3
    case "$reply" in
        1|'') provider=homebrew ;;
        2) provider=uv ;;
        k|K) [[ -n "$current" && "${1:-}" != change ]] || return 3
             candidate=$current ;;
        *) return 3 ;;
    esac
    [[ -n "$candidate" ]] || candidate=$(python_provider_find "$provider" 2>/dev/null)
    if [[ -z "$candidate" ]]; then
        print
        print -- 'No compatible interpreter found. Proposed provider commands:'
        if [[ "$provider" == homebrew ]]; then
            print -- '  brew install python'
        else
            python_uv >/dev/null || print -- '  brew install uv'
            print -- "  uv --no-config python install --no-bin '>=3.11'"
        fi
        print -- 'Providers own these installations. No packages, shell changes or other Python installations are managed.'
        read -r 'reply?Run these commands? [y/N] ' || return 3
        [[ "$reply" == [Yy] ]] || return 3
        python_provider_install "$provider" || return 1
        candidate=$(python_provider_find "$provider") || return 1
    fi
    print
    print -r -- "Use for this installation: $candidate"
    print -- 'Scheduled TotalMarker uses this shared selection unless a job or environment explicitly overrides it.'
    local plist pinned
    for plist in "$script_dir"/launchd/*.plist(N); do
        pinned=$(/usr/bin/plutil -extract EnvironmentVariables.TOTALMARKER_PYTHON raw -o - -- "$plist" 2>/dev/null) || continue
        if [[ "$pinned" != "$candidate" ]]; then
            print -r -- "WARNING: ${plist:t} still pins another interpreter: $pinned"
            print -- 'This selection does not change that job. Review its override and explicitly re-register it to follow the shared choice.'
        fi
    done
    read -r 'reply?Save this interpreter choice? [y/N] ' || return 3
    [[ "$reply" == [Yy] ]] || return 3
    python_save_selection "$candidate" || return
    print -- 'Interpreter selection saved. Other Python installations were left alone.'
}
