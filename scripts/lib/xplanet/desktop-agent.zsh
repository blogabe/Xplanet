# The desktop plist lives in the standard per-user LaunchAgents directory so
# macOS Background Task Management recognizes it, even for an explicit bootstrap
# from a terminal. It is never a login trigger and never respawns the renderer.
desktop_agent_paths() {
    [[ -n "${HOME:-}" && "$HOME" == /* && "$HOME" != *[[:cntrl:]]* && "${HOME:A}" == "$HOME" ]] ||
        fail "desktop HOME must be an absolute real directory"
    desktop_agents="$HOME/Library/LaunchAgents"
    desktop_plist="$desktop_agents/$desktop_label.plist"
    local directory mode
    for directory in "$HOME" "$HOME/Library" "$desktop_agents"; do
        if [[ -e "$directory" || -L "$directory" ]]; then
            [[ -d "$directory" && ! -L "$directory" && -O "$directory" ]] ||
                fail "desktop LaunchAgents parents must be real user-owned directories: $directory"
            mode=$(/usr/bin/stat -f %Lp "$directory") || fail "cannot inspect desktop directory"
            (( (8#$mode & 8#22) == 0 )) || fail "desktop directory must not be writable by other users: $directory"
            [[ -x "$directory" && ( "${1:-}" == read || -w "$directory" ) ]] || fail "desktop directory must be writable and searchable: $directory"
        fi
    done
}

# Accept only the complete generated schema, not a matching Label in a foreign
# plist (which could hide KeepAlive, RunAtLoad or another launch trigger).
# REPLY is the owning checkout; this never sources that checkout's configuration.
desktop_plist_owner() {
    local file="$1" root keys mode before after
    [[ -f "$file" && ! -L "$file" && -O "$file" && "${file:A}" == "$file" ]] || return 1
    mode=$(/usr/bin/stat -f %Lp "$file") || return 1
    (( (8#$mode & 8#22) == 0 )) || return 1
    before=$(/usr/bin/stat -f '%d:%i:%u:%p:%z:%m:%c:%l' "$file") || return 1
    # plutil cannot extract an empty root keypath on every supported macOS.
    # Remove the complete expected schema on stdout, then require an empty
    # dictionary. Extra keys (including launch triggers) cannot be hidden.
    setopt localoptions pipefail
    keys=$(/usr/bin/plutil -remove Label -o - "$file" 2>/dev/null |
        /usr/bin/plutil -remove ProgramArguments -o - - 2>/dev/null |
        /usr/bin/plutil -remove StandardErrorPath -o - - 2>/dev/null |
        /usr/bin/plutil -remove StandardOutPath -o - - 2>/dev/null |
        /usr/bin/plutil -remove WorkingDirectory -o - - 2>/dev/null |
        /usr/bin/plutil -convert json -o - - 2>/dev/null) || return 1
    [[ "$keys" == '{}' ]] || return 1
    [[ "$(/usr/bin/plutil -extract Label raw -expect string -o - "$file")" == "$desktop_label" &&
       "$(/usr/bin/plutil -extract ProgramArguments raw -expect array -o - "$file")" == 2 &&
       "$(/usr/bin/plutil -extract ProgramArguments.0 raw -expect string -o - "$file")" == /bin/zsh ]] || return 1
    root=$(/usr/bin/plutil -extract WorkingDirectory raw -expect string -o - "$file") || return 1
    [[ -n "$root" && "$root" == /* && "$root" != *[[:cntrl:]]* && "${root:A}" == "$root" && -d "$root" && -O "$root" ]] || return 1
    [[ "$(/usr/bin/plutil -extract ProgramArguments.1 raw -expect string -o - "$file")" == "$root/scripts/lib/xplanet/desktop.zsh" &&
       "$(/usr/bin/plutil -extract StandardOutPath raw -expect string -o - "$file")" == "$root/logs/xplanet.log" &&
       "$(/usr/bin/plutil -extract StandardErrorPath raw -expect string -o - "$file")" == "$root/logs/xplanet-error.log" ]] || return 1
    after=$(/usr/bin/stat -f '%d:%i:%u:%p:%z:%m:%c:%l' "$file") || return 1
    [[ "$before" == "$after" && ! -L "$file" ]] || return 1
    REPLY="$root"
}

# Do not infer an active job merely from an installed or registered plist.
desktop_job_reports_running() {
    [[ $'\n'"$1"$'\n' == *$'\n\tstate = running\n'* ]]
}

# launchctl print is a text interface. Fail closed on missing/duplicate identity
# fields, and require the loaded pathname, not just a file newly moved on disk.
# REPLY is the owning checkout; desktop_job_path identifies old registrations.
desktop_job_owned() {
    local line value program='' working='' path_value='' in_arguments=false seen_arguments=false
    local -a arguments
    while IFS= read -r line; do
        value="${line#"${line%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ "$in_arguments" == true ]]; then
            if [[ "$value" == '}' ]]; then in_arguments=false
            else arguments+=("$value")
            fi
        elif [[ "$value" == 'program = '* ]]; then
            [[ -z "$program" ]] || return 1
            program="${value#program = }"
        elif [[ "$value" == 'working directory = '* ]]; then
            [[ -z "$working" ]] || return 1
            working="${value#working directory = }"
        elif [[ "$value" == 'path = '* ]]; then
            [[ -z "$path_value" ]] || return 1
            path_value="${value#path = }"
        elif [[ "$value" == 'arguments = {' ]]; then
            [[ "$seen_arguments" == false ]] || return 1
            seen_arguments=true
            in_arguments=true
        fi
    done <<< "$1"
    [[ "$in_arguments" == false && "$program" == /bin/zsh &&
       -n "$working" && "$working" == /* && "$working" != *[[:cntrl:]]* && "${working:A}" == "$working" &&
       ${#arguments} == 2 && "$arguments[1]" == /bin/zsh && "$arguments[2]" == "$working/scripts/lib/xplanet/desktop.zsh" &&
       ( "$path_value" == "$desktop_plist" || "$path_value" == "$working/.state/xplanet/desktop.plist" ) ]] || return 1
    desktop_plist_owner "$path_value" && [[ "$REPLY" == "$working" ]] || return 1
    desktop_job_path="$path_value"
    REPLY="$working"
}

# With the plist gone there is no on-disk proof of ownership. Only repair the
# current checkout's standard registration when launchd reports the exact
# managed command, paths and job properties and no extra configuration blocks.
# Unknown top-level fields fail closed because launchctl print is not a stable API.
desktop_job_matches_missing_plist() {
    XP_DESKTOP_PLIST="$desktop_plist" XP_DESKTOP_ROOT="$project_root" \
        XP_DESKTOP_TARGET="$desktop_domain/$desktop_label" /usr/bin/awk '
    BEGIN {
        p = ENVIRON["XP_DESKTOP_PLIST"]
        root = ENVIRON["XP_DESKTOP_ROOT"]
        target = ENVIRON["XP_DESKTOP_TARGET"]
    }
    NR == 1 { if ($0 != target " = {") exit 1; next }
    closed { exit 1 }
    $0 == "}" { closed = 1; next }
    /^$/ { next }
    /^\t\t/ { if (!block) exit 1; next }
    /^\t}$/ { if (!block) exit 1; block = 0; next }
    block { exit 1 }
    !/^\t[^\t]/ || !/ = / { exit 1 }
    {
        split_at = index($0, " = ")
        key = substr($0, 2, split_at - 2)
        value = substr($0, split_at + 3)
        if (seen[key]++) exit 1
        if (key == "path") { if (value != p) exit 1 }
        else if (key == "type") { if (value != "LaunchAgent") exit 1 }
        else if (key == "program") { if (value != "/bin/zsh") exit 1 }
        else if (key == "working directory") { if (value != root) exit 1 }
        else if (key == "stdout path") { if (value != root "/logs/xplanet.log") exit 1 }
        else if (key == "stderr path") { if (value != root "/logs/xplanet-error.log") exit 1 }
        else if (key == "properties") { if (value != "inferred program") exit 1 }
        else if (key == "arguments") {
            if (value != "{" || getline <= 0 || $0 != "\t\t/bin/zsh" ||
                getline <= 0 || $0 != "\t\t" root "/scripts/lib/xplanet/desktop.zsh" ||
                getline <= 0 || $0 != "\t}") exit 1
        }
        else if (key == "environment") {
            if (value != "{") exit 1
            while ((getline) > 0 && $0 != "\t}") {
                if ($0 == "\t\tXPC_SERVICE_NAME => " substr(target, index(target, "/local.") + 1))
                    continue
                if ($0 ~ /^\t\tOSLogRateLimit => [0-9]+$/) continue
                exit 1
            }
            if ($0 != "\t}") exit 1
        }
        else if (key ~ /^(inherited environment|default environment|pid-local endpoints|resource coalition|jetsam coalition)$/) {
            if (value != "{") exit 1
            block = 1
        }
        else if (value == "{" ||
            key !~ /^(active count|state|domain|asid|minimum runtime|exit timeout|runs|pid|immediate reason|forks|execs|initialized|trampolined|started suspended|proxy started suspended|checked allocations|checked allocations reason|checked allocations flags|last exit code|spawn type|jetsam priority|jetsam memory limit \(active\)|jetsam memory limit \(inactive\)|jetsamproperties category|jetsam thread limit|cpumon|job state|sanitizer flags)$/) exit 1
    }
    END {
        if (!closed || !seen["path"] || !seen["type"] || !seen["program"] ||
            !seen["arguments"] || !seen["working directory"] || !seen["stdout path"] ||
            !seen["stderr path"] || !seen["properties"]) exit 1
    }' <<< "$1"
}

desktop_agent_recover_missing() {
    local info
    [[ ! -e "$desktop_plist" && ! -L "$desktop_plist" ]] || return 0
    desktop_job_matches_missing_plist "$1" || return 1
    info=$(launchctl print "$desktop_domain/$desktop_label" 2>/dev/null) || return 1
    desktop_job_matches_missing_plist "$info" || return 1
    # Use the normal atomic, no-clobber publication path; never copy a legacy
    # plist or stop a job to make recovery possible.
    desktop_agent_prepare recover || return 1
    info=$(launchctl print "$desktop_domain/$desktop_label" 2>/dev/null) || return 1
    desktop_job_matches_missing_plist "$info" || return 1
    desktop_job_owned "$info" && [[ "$REPLY" == "$project_root" ]]
}

# Check without mutation for restart preflight. A managed file from a different
# checkout can be replaced only by the explicit restart's serialized handover.
desktop_agent_preflight() {
    desktop_agent_paths
    if [[ -e "$desktop_plist" || -L "$desktop_plist" ]]; then
        desktop_plist_owner "$desktop_plist" || fail "desktop plist is foreign, linked, unsafe or modified; refusing to replace $desktop_plist"
        [[ "$REPLY" == "$project_root" || "${1:-}" == restart ]] ||
            fail "desktop plist belongs to another checkout; use explicit restart to replace it"
    fi
    local directory
    for directory in "$project_root/logs"; do
        [[ ! -L "$directory" && ( ! -e "$directory" || ( -d "$directory" && -w "$directory" && -x "$directory" ) ) ]] ||
            fail "desktop log directory must be a writable real directory"
        [[ -e "$directory" || ( -w "${directory:h}" && -x "${directory:h}" ) ]] ||
            fail "desktop log parent must be writable and searchable"
    done
    local file
    for file in "$project_root/logs/xplanet.log" "$project_root/logs/xplanet-error.log"; do
        [[ ! -L "$file" && ( ! -e "$file" || ( -f "$file" && -O "$file" && -w "$file" ) ) ]] ||
            fail "desktop log must be a writable user-owned regular file: $file"
    done
}

desktop_agent_prepare() (
    desktop_agent_preflight "${1:-}"
    local temporary before='' after mode=600 directory
    if [[ -e "$desktop_plist" ]]; then
        [[ "${1:-}" != recover ]] || fail "desktop plist appeared during recovery"
        local reuse=false
        [[ "$REPLY" != "$project_root" ]] || reuse=true
        before=$(/usr/bin/stat -f '%d:%i:%u:%p:%z:%m:%c:%l' "$desktop_plist") || fail "cannot inspect desktop plist"
        mode=$(/usr/bin/stat -f %Lp "$desktop_plist") || fail "cannot inspect desktop plist permissions"
    fi
    for directory in "$HOME/Library" "$desktop_agents" "$project_root/logs"; do
        if [[ ! -e "$directory" && ! -L "$directory" ]]; then
            mkdir -m 700 -- "$directory" || fail "cannot create desktop directory: $directory"
        fi
    done
    desktop_agent_preflight "${1:-}"
    [[ "${reuse:-false}" != true ]] || return 0
    temporary=$(mktemp "$desktop_agents/.xplanet-desktop.XXXXXXXX") || fail "cannot prepare desktop plist"
    trap 'rm -f -- "$temporary"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    local template="$script_dir/launchd/local.xplanet.desktop.plist.template"
    [[ -f "$template" && ! -L "$template" ]] || fail "managed desktop plist template is missing or linked"
    cat -- "$template" > "$temporary" &&
    /usr/bin/plutil -remove ProgramArguments.1 "$temporary" &&
    /usr/bin/plutil -insert ProgramArguments.1 -string "$script_dir/lib/xplanet/desktop.zsh" "$temporary" &&
    /usr/bin/plutil -replace WorkingDirectory -string "$project_root" "$temporary" &&
    /usr/bin/plutil -replace StandardOutPath -string "$project_root/logs/xplanet.log" "$temporary" &&
    /usr/bin/plutil -replace StandardErrorPath -string "$project_root/logs/xplanet-error.log" "$temporary" &&
    chmod "$mode" "$temporary" || fail "cannot write desktop plist"
    desktop_plist_owner "$temporary" && [[ "$REPLY" == "$project_root" ]] || fail "generated desktop plist did not validate"
    if [[ -n "$before" ]]; then
        desktop_plist_owner "$desktop_plist" || fail "desktop plist changed during preparation"
        after=$(/usr/bin/stat -f '%d:%i:%u:%p:%z:%m:%c:%l' "$desktop_plist") || fail "cannot recheck desktop plist"
        [[ "$before" == "$after" ]] || fail "desktop plist changed during preparation"
        # The per-user lifecycle lock serializes all CLI handovers. Revalidate
        # immediately before replacing the recognized other-checkout file.
        mv -f -- "$temporary" "$desktop_plist" || fail "cannot replace managed desktop plist"
    else
        if [[ "${1:-}" == recover ]]; then
            local info
            info=$(launchctl print "$desktop_domain/$desktop_label" 2>/dev/null) &&
                desktop_job_matches_missing_plist "$info" ||
                fail "loaded desktop job changed during recovery"
        fi
        # Atomic no-clobber publication, even if an unrelated writer races us.
        /bin/link "$temporary" "$desktop_plist" || fail "desktop plist appeared during preparation; retry after reviewing it"
        [[ -f "$desktop_plist" && ! -L "$desktop_plist" && "$temporary" -ef "$desktop_plist" ]] ||
            fail "desktop plist changed during publication; no start was requested"
    fi
)
