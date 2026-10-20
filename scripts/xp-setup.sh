#!/bin/zsh
set -u
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)

# Launchd plan: inspect every job first, render only missing personal plists
# with plutil, then link missing LaunchAgents. Existing files are never replaced.
# The internal mode lets isolated tests exercise this without running setup.
prepare_launchd_files() (
    temporary=''
    trap '[[ -z "$temporary" ]] || rm -f -- "$temporary"' EXIT

    fail() { print -u2 -- "Launchd preparation refused: $1"; exit 2; }
    entry_exists() { [[ -e "$1" || -L "$1" ]]; }
    real_dir() { [[ -d "$1" && ! -L "$1" ]] || fail "$1 must be a real directory"; }
    regular() { [[ -f "$1" && ! -L "$1" ]] || fail "$1 must be a real regular file"; }
    plist_get() { /usr/bin/plutil -extract "$2" raw -o - -- "$1" 2>/dev/null; }
    plist_type() { /usr/bin/plutil -type "$2" -- "$1" 2>/dev/null; }
    plist_has() { plist_type "$1" "$2" >/dev/null; }
    plist_set() { /usr/bin/plutil -replace "$2" -string "$3" -- "$1" >/dev/null || fail "Cannot render $1"; }

    (( $# == 4 || $# == 5 )) || fail "expected --home PATH --python PATH [--include-clouds]"
    [[ "$1" == --home && "$3" == --python ]] || fail "expected --home PATH --python PATH"
    home="$2"
    python_bin="$4"
    if (( $# == 5 )); then
        [[ "$5" == --include-clouds ]] || fail "unknown option: $5"
    fi
    [[ "$home" == /* && "$home" == "${home:A}" ]] ||
        fail "HOME must be an absolute directory without symlink ancestors"
    real_dir "$home"
    [[ "$python_bin" == /* && -x "$python_bin" ]] || fail "Python must be an absolute executable path"
    real_dir "$project_root/scripts"
    real_dir "$project_root/scripts/launchd"
    real_dir "$project_root/logs"
    real_dir "$project_root/images"
    regular "$project_root/scripts/xplanet.sh"
    [[ -x "$project_root/scripts/xplanet.sh" ]] || fail "The Xplanet launcher must be executable"
    [[ -x /usr/bin/plutil ]] || fail "macOS plutil is unavailable"

    verify_log() {
        local value="$1" working="$2" path resolved
        path="$value"
        [[ "$path" == /* ]] || path="$working/$path"
        resolved="${path:A}"
        [[ "${resolved:h}" == "$project_root/logs" ]] ||
            fail "Review local launchd log path $value: it must resolve under $project_root/logs"
        if entry_exists "$path"; then
            regular "$path"
        fi
    }

    # The same structure is checked before preserving a personal plist and
    # after rendering a new one. Examples keep relative log paths; local jobs
    # may use absolute or WorkingDirectory-relative paths inside this root.
    verify_plist() {
        local path="$1" job="$2" command="$3" working="$4" kind="$5"
        local key value launcher
        regular "$path"
        /usr/bin/plutil -lint -- "$path" >/dev/null || fail "Invalid launchd plist: $path"
        [[ "$(plist_get "$path" Label)" == "local.xplanet.$job" &&
           "$(plist_type "$path" ProgramArguments)" == array &&
           "$(plist_get "$path" ProgramArguments)" == 2 &&
           "$(plist_get "$path" ProgramArguments.1)" == "$command" ]] || {
            [[ "$kind" == example ]] && fail "Unexpected launchd example structure: $path"
            fail "Review local launchd ProgramArguments or Label: $path"
        }
        if plist_has "$path" Program; then
            [[ "$kind" == example ]] && fail "Unexpected Program override in example: $path"
            fail "Review local launchd Program override: $path"
        fi
        if [[ "$kind" == local ]]; then
            [[ "$(plist_get "$path" WorkingDirectory)" == "$working" ]] ||
                fail "Review local launchd WorkingDirectory: $path"
            value=$(plist_get "$path" ProgramArguments.0)
            [[ "$value" == /* || "$value" == */* ]] ||
                fail "Review local launchd ProgramArguments.0: $path"
            launcher="$value"
            [[ "$launcher" == /* ]] || launcher="$working/$launcher"
            [[ "${launcher:A}" == "$project_root/scripts/xplanet.sh" ]] ||
                fail "Review local launchd ProgramArguments.0: $path"
        fi
        for key in StandardOutPath StandardErrorPath; do
            [[ "$(plist_type "$path" "$key")" == string ]] ||
                fail "Review launchd $key in $path"
            value=$(plist_get "$path" "$key")
            if [[ "$kind" == example && "$value" == /* ]]; then
                fail "Unexpected $key in $path"
            fi
            verify_log "$value" "$working"
        done
        if plist_has "$path" EnvironmentVariables; then
            [[ "$(plist_type "$path" EnvironmentVariables)" == dictionary ]] ||
                fail "Review launchd EnvironmentVariables in $path"
        fi
        if [[ "$kind" == local ]] && plist_has "$path" EnvironmentVariables.TOTALMARKER_PYTHON; then
            # An explicit override may differ from the interactive interpreter.
            [[ "$(plist_type "$path" EnvironmentVariables.TOTALMARKER_PYTHON)" == string ]] ||
                fail "Review local launchd TOTALMARKER_PYTHON: $path"
            value=$(plist_get "$path" EnvironmentVariables.TOTALMARKER_PYTHON)
            [[ "$value" == /* && -x "$value" ]] &&
                "$value" -B -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
                    >/dev/null 2>&1 ||
                fail "Review local launchd TOTALMARKER_PYTHON: $path"
        fi
    }

    job_paths() {
        job="$1"
        command="$job"
        working="$project_root"
        if [[ "$job" == earth-map ]]; then
            command=earth
            working="$project_root/images"
        fi
        local name="local.xplanet.$job.plist"
        example="$project_root/scripts/launchd/$name.example"
        local_plist="$project_root/scripts/launchd/$name"
        agent="$agents/$name"
    }

    render_local_plist() {
        local key value resolved
        temporary=$(mktemp "$project_root/scripts/launchd/.local.xplanet.$job.XXXXXX") ||
            fail "Stopped at $local_plist"
        cat -- "$example" > "$temporary" || fail "Stopped at $local_plist"
        plist_set "$temporary" WorkingDirectory "$working"
        # plutil -replace on an array index inserts instead of replacing it.
        /usr/bin/plutil -remove ProgramArguments.0 -- "$temporary" >/dev/null || fail "Stopped at $local_plist"
        /usr/bin/plutil -insert ProgramArguments.0 -string "$project_root/scripts/xplanet.sh" -- "$temporary" >/dev/null ||
            fail "Stopped at $local_plist"
        for key in StandardOutPath StandardErrorPath; do
            value=$(plist_get "$example" "$key")
            resolved="$working/$value"
            resolved="${resolved:A}"
            verify_log "$resolved" "$working"
            plist_set "$temporary" "$key" "$resolved"
        done
        if ! plist_has "$temporary" EnvironmentVariables; then
            /usr/bin/plutil -insert EnvironmentVariables -dictionary -- "$temporary" >/dev/null ||
                fail "Stopped at $local_plist"
        fi
        if plist_has "$temporary" EnvironmentVariables.TOTALMARKER_PYTHON; then
            plist_set "$temporary" EnvironmentVariables.TOTALMARKER_PYTHON "$python_bin"
        else
            /usr/bin/plutil -insert EnvironmentVariables.TOTALMARKER_PYTHON -string "$python_bin" -- "$temporary" >/dev/null ||
                fail "Stopped at $local_plist"
        fi
        verify_plist "$temporary" "$job" "$command" "$working" local
        (setopt noclobber; cat -- "$temporary" > "$local_plist") || fail "Stopped at $local_plist"
        rm -- "$temporary"
        temporary=''
        (( prepared += 1 ))
    }

    jobs=(start earth-map quake storm volcano)
    (( $# == 5 )) && jobs+=(clouds)
    agents="$home/Library/LaunchAgents"
    for directory in "$home/Library" "$agents"; do
        if entry_exists "$directory"; then real_dir "$directory"; fi
    done

    # Inspect every selected example, personal plist and LaunchAgent before writing.
    for job in "${jobs[@]}"; do
        job_paths "$job"
        verify_plist "$example" "$job" "$command" "$working" example
        if entry_exists "$local_plist"; then
            verify_plist "$local_plist" "$job" "$command" "$working" local
        fi
        if entry_exists "$agent"; then
            [[ -L "$agent" && "$(readlink "$agent")" == "$local_plist" ]] ||
                fail "Existing LaunchAgent needs review: $agent"
        fi
    done

    # Write only after the complete preflight has passed.
    if ! entry_exists "$home/Library"; then mkdir -- "$home/Library" || fail "Stopped at $home/Library"; fi
    if ! entry_exists "$agents"; then mkdir -- "$agents" || fail "Stopped at $agents"; fi
    real_dir "$home/Library"
    real_dir "$agents"
    prepared=0
    for job in "${jobs[@]}"; do
        job_paths "$job"
        if ! entry_exists "$local_plist"; then
            render_local_plist
        fi
        verify_plist "$local_plist" "$job" "$command" "$working" local
        real_dir "$agents"
        if ! entry_exists "$agent"; then
            ln -s -- "$local_plist" "$agent" || fail "Stopped at $agent"
            (( prepared += 1 ))
        elif [[ ! -L "$agent" || "$(readlink "$agent")" != "$local_plist" ]]; then
            fail "Existing LaunchAgent needs review: $agent"
        fi
    done
    print -- "Launchd files ready; $prepared new entries prepared"
)

if [[ "${1:-}" == --prepare-launchd ]]; then
    shift
    prepare_launchd_files "$@"
    exit $?
fi

fail() {
    print -u2 -- "xp-setup.sh: $1"
    exit 2
}

ask() {
    local answer
    read -r "answer?$1 [y/N] " || fail "input ended before setup was confirmed"
    [[ "$answer" == [Yy] ]]
}

if (( $# > 1 )); then
    fail "expected --dry-run, --check or no option"
fi
case "${1:-}" in
    --dry-run|--check|'') ;;
    *) fail "expected --dry-run, --check or no option" ;;
esac
setup_mode=${1:-apply}

entry_exists() { [[ -e "$1" || -L "$1" ]]; }
real_dir() {
    local current="$project_root" part
    for part in ${(s:/:)1}; do
        current="$current/$part"
        [[ -d "$current" && ! -L "$current" ]] || fail "$current must be a real directory"
    done
}
verify_target() {
    local name="$1" target="$2" candidate="$project_root/${1:h}/$2"
    [[ "$target" != /* ]] || fail "$name points outside the project"
    local resolved="${candidate:a}"
    [[ "$resolved" == "$project_root/"* ]] || fail "$name points outside the project"
    local relative="${resolved#$project_root/}"
    if [[ "$name" == images/solarsystem ]]; then
        [[ "$relative" == assets/maps/solarsystem || "$relative" == config/images/solarsystem ]] ||
            fail "$name must point to retained solar-system imagery"
        real_dir "$relative"
    elif [[ "$name" == markers/earth ]]; then
        [[ "$relative" == config/earth ]] || fail "$name must point to config/earth"
        real_dir config
        if ! entry_exists "$resolved"; then
            [[ -f "$project_root/config/earth.example" && ! -L "$project_root/config/earth.example" ]] ||
                fail "config/earth.example must be a real regular file"
        else
            [[ -f "$resolved" && ! -L "$resolved" ]] || fail "$name has an invalid target"
        fi
    else
        [[ "$relative" == assets/maps/* ]] || fail "$name must point to an internal map asset"
        real_dir "${relative:h}"
        [[ -f "$resolved" && ! -L "$resolved" ]] || fail "$name has an invalid target"
    fi
}

real_dir config
personal_names=(config/xp.conf config/xp.def config/totalmarker.toml config/earth)
personal_examples=(config/xp.conf.example config/xp.def.example
                   config/totalmarker.example.toml config/earth.example)
missing_personal=()
existing_personal=()
for (( index=1; index<=${#personal_names}; index++ )); do
    example="$project_root/$personal_examples[index]"
    entry="$project_root/$personal_names[index]"
    if ! entry_exists "$entry"; then
        [[ -f "$example" && ! -L "$example" ]] ||
            fail "$personal_names[index] is missing; restore the shipped $personal_examples[index] before setup"
        missing_personal+=("$index")
    else
        [[ -f "$entry" && ! -L "$entry" ]] ||
            fail "$personal_names[index] must be a real regular file; review it before setup"
        existing_personal+=("$index")
    fi
done

definition="$project_root/config/xp.def"
if ! entry_exists "$definition"; then
    definition="$project_root/config/xp.def.example"
    [[ "$(grep -c '^XPLANET_BIN=' "$definition")" == 1 &&
       "$(grep -c '^XPLANET_BIN=$' "$definition")" == 1 ]] ||
        fail "config/xp.def.example needs one blank XPLANET_BIN= line; restore the shipped example"
fi
map_count=0
stock_maps=false
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ '^[[:space:]]*#' ]] && continue
    if [[ "$line" =~ '^[[:space:]]*EARTH_MAP_PRE[[:space:]]*=' ]]; then
        (( map_count += 1 ))
        if [[ "$line" =~ '^[[:space:]]*EARTH_MAP_PRE[[:space:]]*=[[:space:]]*stock[[:space:]]*$' ]]; then
            stock_maps=true
        elif [[ "$line" =~ '^[[:space:]]*EARTH_MAP_PRE[[:space:]]*=[[:space:]]*([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)[[:space:]]*$' ]]; then
            stock_maps=false
            map_folder="$match[1]"
            map_name="$match[2]"
        else
            fail "EARTH_MAP_PRE must be stock or one literal safe folder/name"
        fi
    fi
done < "$definition"
(( map_count == 1 )) || fail "$definition needs one literal EARTH_MAP_PRE=stock or folder/name setting"

directories=(arcs images logs markers satellites logs/totalmarker .state .state/totalmarker)
missing_dirs=()
for directory in "${directories[@]}"; do
    entry="$project_root/$directory"
    if ! entry_exists "$entry"; then
        missing_dirs+=("$directory")
    elif [[ ! -d "$entry" || -L "$entry" ]]; then
        fail "$directory must be a real directory"
    fi
done

link_names=(markers/earth)
link_targets=(../config/earth)
if [[ "$stock_maps" == false ]]; then
    month=$(date +%m)
    [[ "$month" == <-> && "$month" -ge 1 && "$month" -le 12 ]] || fail "Cannot determine Earth map month"
    # Legacy links for personal high-resolution seasonal maps.
    link_names=(images/earth.png images/lights.tiff images/bump.png images/specular.png markers/earth)
    link_targets=("../assets/maps/$map_folder/$map_name.2004${month}.3x5400x2700.png"
                  ../assets/maps/lights/earth_lights_4800.tiff
                  ../assets/maps/bump/gebco_08_rev_elev_21600x10800.png
                  ../assets/maps/specular/specular.png ../config/earth)
fi
solar_notice=''
if [[ -d "$project_root/assets/maps/solarsystem" && ! -L "$project_root/assets/maps/solarsystem" ]] ||
   entry_exists "$project_root/images/solarsystem"; then
    link_names+=(images/solarsystem)
    link_targets+=(../assets/maps/solarsystem)
else
    solar_notice='No images/solarsystem link planned: assets/maps/solarsystem is absent.'
fi
missing_links=()
for (( index=1; index<=${#link_names}; index++ )); do
    name="$link_names[index]"
    entry="$project_root/$name"
    if ! entry_exists "$entry"; then
        verify_target "$name" "$link_targets[index]"
        missing_links+=("$index")
    elif [[ -L "$entry" ]]; then
        verify_target "$name" "$(readlink "$entry")"
    elif [[ "$name" == images/solarsystem ]]; then
        [[ -d "$entry" ]] || fail "$name must be a real directory or safe internal link"
    else
        [[ -f "$entry" ]] || fail "$name must be a regular file or safe internal link"
    fi
done

if [[ "$setup_mode" == --dry-run ]]; then
    for directory in "${missing_dirs[@]}"; do print -- "Would mkdir $directory"; done
    for index in "${missing_links[@]}"; do
        print -- "Would link $link_names[index] <- $link_targets[index]"
    done
    [[ -z "$solar_notice" ]] || print -- "$solar_notice"
    for index in "${missing_personal[@]}"; do
        print -- "Would copy $personal_names[index] <- $personal_examples[index]"
    done
    exit 0
elif [[ "$setup_mode" == --check ]]; then
    if (( ${#missing_dirs} || ${#missing_links} || ${#missing_personal} )); then
        print -- "Preparation needed: $((${#missing_dirs} + ${#missing_links} + ${#missing_personal})) entries"
        [[ -z "$solar_notice" ]] || print -- "$solar_notice"
        exit 1
    fi
    print -- "Directory/link preparation ready"
    [[ -z "$solar_notice" ]] || print -- "$solar_notice"
    exit 0
fi

python_bin=$("$script_dir/run-totalmarker" --python-path) || {
    print -u2 -- "TotalMarker needs Python 3.11+; check Homebrew's prefix or set TOTALMARKER_PYTHON to its absolute path."
    exit 2
}
XPLANET_BIN=''
XPLANET_HOME=''
XPLANET_CONFIG=''
source "$definition"
configured_bin="$XPLANET_BIN"
installed_bin="${XPLANET_INSTALLED_BIN:-}"
if [[ -n "$installed_bin" && "$definition" != "$project_root/config/xp.def.example" ]]; then
    [[ "$(grep -c '^[[:space:]]*XPLANET_BIN=' "$definition")" == 1 ]] ||
        fail "config/xp.def needs exactly one XPLANET_BIN assignment; review it before setup"
fi
if [[ -n "$installed_bin" ]]; then
    # Install hands off its exact binary; setup owns the personal config edit.
    XPLANET_BIN="$installed_bin"
elif [[ "$definition" == "$project_root/config/xp.def.example" ]]; then
    XPLANET_BIN=$(command -v xplanet) ||
        fail "No Xplanet executable found; run scripts/xplanet.sh install or put xplanet on PATH before setup"
fi
[[ "$XPLANET_HOME" == "$project_root" ]] || fail "$definition: XPLANET_HOME must equal this project root"
[[ "$XPLANET_CONFIG" == "$project_root/config" ]] || fail "$definition: XPLANET_CONFIG must equal this project's config directory"
[[ "$XPLANET_BIN" == /* && -x "$XPLANET_BIN" ]] ||
    fail "$definition: XPLANET_BIN must name an absolute installed executable; edit that setting or run scripts/xplanet.sh install"

print -- "Xplanet is expected to be installed. TotalMarker will use $python_bin."
print -- "Step 1: create missing personal configs, directories, map links and Earth marker,"
print -- "        then choose which earthquake, storm and volcano markers to refresh."
print -- "        Review $project_root/config/totalmarker.toml before any refresh."
print -- "Step 2: optionally update the cloud image through your configured Xeric or custom provider."
print -- "Step 3: optionally install and register Xplanet launchd jobs; this may start Xplanet."
print -- "No Python package or virtual environment will be installed."
if ! ask "Step 1) Continue with Xplanet preparation?"; then
    print -- "Setup cancelled without preparing files."
    exit 0
fi

real_dir config
for index in "${existing_personal[@]}"; do
    entry="$project_root/$personal_names[index]"
    [[ -f "$entry" && ! -L "$entry" ]] ||
        fail "Preparation stopped: $personal_names[index] changed during confirmation"
done
if [[ -n "$installed_bin" && "$definition" != "$project_root/config/xp.def.example" &&
      "$configured_bin" != "$installed_bin" ]]; then
    print -- "Installed Xplanet differs from config/xp.def; review the proposed binary change."
    if ! ask "Set XPLANET_BIN in config/xp.def to $installed_bin?"; then
        fail "Kept config/xp.def unchanged; set XPLANET_BIN before setup"
    fi
    real_dir config
    [[ -f "$definition" && ! -L "$definition" ]] ||
        fail "config/xp.def changed during confirmation; stopped before writing"
    replacement=$(printf 'XPLANET_BIN=%q' "$installed_bin")
    temporary=$(mktemp "$project_root/config/.xp.def.XXXXXX") ||
        fail "Could not prepare config/xp.def update"
    if ! {
        while IFS= read -r line || [[ -n "$line" ]]; do
            if [[ "$line" =~ '^[[:space:]]*XPLANET_BIN=' ]]; then
                print -r -- "$replacement"
            else
                print -r -- "$line"
            fi
        done < "$definition"
    } > "$temporary"; then
        rm -f -- "$temporary"
        fail "Could not prepare config/xp.def update"
    fi
    real_dir config
    [[ -f "$definition" && ! -L "$definition" ]] || {
        rm -f -- "$temporary"
        fail "config/xp.def changed during confirmation; stopped before writing"
    }
    mv -f -- "$temporary" "$definition" || {
        rm -f -- "$temporary"
        fail "Could not update config/xp.def"
    }
    print -- "Set XPLANET_BIN in config/xp.def to $installed_bin."
fi
for index in "${missing_personal[@]}"; do
    real_dir config
    example="$project_root/$personal_examples[index]"
    entry="$project_root/$personal_names[index]"
    [[ -f "$example" && ! -L "$example" ]] || fail "Preparation stopped: restore $personal_examples[index]"
    if [[ "$personal_names[index]" == config/xp.def ]]; then
        replacement=$(printf 'XPLANET_BIN=%q' "$XPLANET_BIN")
        (
            setopt noclobber
            while IFS= read -r line || [[ -n "$line" ]]; do
                if [[ "$line" == XPLANET_BIN= ]]; then
                    print -r -- "$replacement"
                else
                    print -r -- "$line"
                fi
            done < "$example" > "$entry"
        ) || fail "Preparation stopped at $personal_names[index]; existing files are never replaced"
    else
        (setopt noclobber; cat -- "$example" > "$entry") ||
            fail "Preparation stopped at $personal_names[index]; existing files are never replaced"
    fi
    print -- "Prepare copy $personal_names[index] <- $personal_examples[index]"
done
for directory in "${missing_dirs[@]}"; do
    parent="${directory:h}"
    [[ "$parent" == . ]] || real_dir "$parent"
    entry="$project_root/$directory"
    entry_exists "$entry" && fail "Preparation stopped at $directory: destination changed"
    mkdir -- "$entry" || fail "Preparation stopped at $directory"
    print -- "Prepare mkdir $directory"
done
for index in "${missing_links[@]}"; do
    name="$link_names[index]"
    target="$link_targets[index]"
    real_dir "${name:h}"
    verify_target "$name" "$target"
    entry="$project_root/$name"
    entry_exists "$entry" && fail "Preparation stopped at $name: destination changed"
    ln -s -- "$target" "$entry" || fail "Preparation stopped at $name"
    print -- "Prepare link $name <- $target"
done
[[ -z "$solar_notice" ]] || print -- "$solar_notice"
print -- "Review or edit $project_root/config/totalmarker.toml now."
print -- "The file controls feed sources, styling and cloud credentials."
print -- "Existing personal settings are preserved; no credentials are collected here."
local_reply=''
read -r "local_reply?Press Enter after reviewing the TOML, or type q to stop: " ||
    fail "input ended before marker refresh"
if [[ "$local_reply" == [Qq] ]]; then
    print -- "Setup stopped before live marker refresh."
    exit 0
fi

failures=()
refresh_products=()
refresh_reasons=()
launcher="$project_root/scripts/xplanet.sh"
record_refresh_result() {
    local product="$1" exit_code="$2" output="$3" reason='' message='' outcome=''
    # Require JSON object shape; plutil validates syntax and field types.
    # An exit-1 warning must be a failed TotalMarker result, not a broken
    # interpreter or launcher. plutil alone also accepts XML plists.
    if [[ "$output" == \{*\} && "$output" == *'"outcome"'* &&
          "$output" == *'"message"'* ]]; then
        message=$(/usr/bin/plutil -extract message raw -expect string -o - - \
            <<< "$output" 2>/dev/null) || message=''
    fi
    if (( exit_code == 1 )) && [[ -n "$message" ]]; then
        outcome=$(/usr/bin/plutil -extract outcome raw -expect string -o - - \
            <<< "$output" 2>/dev/null) || outcome=''
    fi
    if (( exit_code == 1 )) && [[ "$outcome" == failed ]]; then
        refresh_products+=("$product")
        refresh_reasons+=("$message")
        print -u2 -- "$product refresh failed; continuing setup with a warning."
    else
        if (( exit_code == 1 )); then
            reason="command exited with status 1 without a valid failed TotalMarker result"
        elif [[ -n "$message" ]]; then
            reason="$message"
        elif [[ -z "$output" ]]; then
            reason="command exited with status $exit_code without a result"
        else
            reason="command exited with status $exit_code; see detailed result above"
        fi
        failures+=("$product refresh: $reason (exit $exit_code). Fix the cause, then retry: ${(q)launcher} $product")
        print -u2 -- "$product refresh could not complete; setup will report a core failure."
    fi
}

for product in quake storm volcano; do
    if ask "Refresh $product markers now?"; then
        product_output=$("$script_dir/run-totalmarker" "$product")
        product_status=$?
        [[ -z "$product_output" ]] || print -r -- "$product_output"
        if (( product_status != 0 )); then
            record_refresh_result "$product" "$product_status" "$product_output"
        fi
    fi
done

cloud_selected=false
if ask "Step 2) Update the cloud image using the configured provider?"; then
    cloud_selected=true
    product_output=$("$script_dir/run-totalmarker" clouds)
    product_status=$?
    [[ -z "$product_output" ]] || print -r -- "$product_output"
    if (( product_status != 0 )); then
        record_refresh_result clouds "$product_status" "$product_output"
    fi
fi

automation_requested=false
if ask "Step 3) Install and register Xplanet automation?"; then
    automation_requested=true
    arguments=(--home "${HOME:-}" --python "$python_bin")
    jobs=(start earth-map quake storm volcano)
    if [[ "$cloud_selected" == true ]]; then
        arguments+=(--include-clouds)
        jobs+=(clouds)
    fi
    if ! command -v launchctl >/dev/null 2>&1; then
        print -u2 -- "launchctl is unavailable; no jobs were registered."
        failures+=("launchd unavailable")
    elif [[ -z "${HOME:-}" || "$HOME" != /* ]]; then
        print -u2 -- "HOME must be an absolute path; no jobs were registered."
        failures+=("launchd home")
    elif ! prepare_launchd_files "${arguments[@]}"; then
        print -u2 -- "launchd file preparation failed; no jobs were registered."
        failures+=("launchd preparation")
    else
        for job in "${jobs[@]}"; do
            agent="$HOME/Library/LaunchAgents/local.xplanet.$job.plist"
            if ! launchctl load -w "$agent"; then
                print -u2 -- "launchd could not load $job; review installed job status."
                failures+=("launchd $job load")
            elif ! launchctl list "local.xplanet.$job" >/dev/null 2>&1; then
                print -u2 -- "launchd did not confirm registration of $job."
                failures+=("launchd $job registration")
            fi
        done
        print -- "Xplanet automation file preparation and registration checks finished."
    fi
fi

if (( ${#refresh_products} )); then
    print -u2 -- "Optional refresh warning(s):"
    for (( index=1; index<=${#refresh_products}; index++ )); do
        print -r -u2 -- "  $refresh_products[index]: $refresh_reasons[index]"
        print -r -u2 -- "    Retry: ${(q)launcher} $refresh_products[index]"
    done
    print -u2 -- "Setup did not remove prior product output. If present, it may be stale."
    print -u2 -- "If no previous output exists, that layer is unavailable until a successful refresh."
fi
if (( ${#failures} )); then
    print -u2 -- "Setup finished with ${#failures} failed core step(s):"
    for failure in "${failures[@]}"; do
        print -r -u2 -- "  $failure"
    done
    exit 1
fi
if (( ${#refresh_products} )); then
    print -- "Setup complete with refresh warnings."
else
    print -- "Setup complete."
fi
if [[ "$automation_requested" == true ]]; then
    print -- "If macOS asks to let Xplanet control Finder, choose Allow for desktop updates."
    print -- "Allow a few minutes for the first desktop update to appear."
fi
