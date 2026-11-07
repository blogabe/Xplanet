# Read-only metadata and bounded saved-health snapshots; no live refresh.
management_selection_facts() {
    management_selection='custom configuration (xp.def / xp.conf)'
    local selector="$project_root/config/desktop.scene" description
    [[ -e "$selector" || -L "$selector" ]] || return 0
    # Lifecycle validation stays authoritative. Inspect only bounded, hash-bound
    # deployment metadata here; do not scan textures or claim actual runtime use.
    description=$(
        load_helpers scene
        scene_revision_id || exit 1
        local identity="$REPLY" manifest="$project_root/.state/xplanet/scenes/$REPLY/deployment.plist" scene dimensions
        scene_hash "$manifest" "$identity" 262144
        [[ "$(/usr/bin/plutil -extract schema raw -expect integer -o - "$manifest")" == 1 ]] || exit 1
        [[ "$(/usr/bin/plutil -extract review.root raw -expect string -o - "$manifest")" == "$project_root" ]] || exit 1
        scene=$(/usr/bin/plutil -extract review.scene raw -expect string -o - "$manifest") || exit 1
        dimensions=$(/usr/bin/plutil -extract review.geometry raw -expect string -o - "$manifest") || exit 1
        [[ "$scene" =~ '^config/scenes/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.conf$' && "$dimensions" =~ '^[0-9]{1,5}x[0-9]{1,5}$' ]] || exit 1
        scene_hash "$manifest" "$identity" 262144
        scene_revision_id && [[ "$REPLY" == "$identity" ]] || exit 1
        print -r -- "${scene:t:r} ($dimensions); metadata verified, resources unchecked"
    ) 2>/dev/null
    if [[ $? == 0 && -n "$description" ]]; then management_selection="$description"
    else management_selection='invalid or unavailable selector; inspect before starting'
    fi
}

# A private job group bounds UI latency, including interpreter discovery. Only
# this read-only worker group is signalled; direct health commands are unchanged.
management_health_records() (
    setopt monitor || return 2
    unsetopt notify
    local capture result attempt worker=''
    capture=$(mktemp "${TMPDIR:-/tmp}/xplanet-health.XXXXXXXX") || return 2
    trap '[[ "$worker" == <-> ]] && { kill -TERM -- -"$worker" 2>/dev/null; kill -KILL -- -"$worker" 2>/dev/null; wait "$worker" 2>/dev/null; }; rm -f -- "$capture"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    (ulimit -f 32 || exit 2; exec "$script_dir/run-totalmarker" health --dashboard) >|"$capture" 2>&1 &
    worker=$!
    unsetopt monitor
    for attempt in {1..50}; do
        kill -0 "$worker" 2>/dev/null || break
        sleep 0.1
    done
    if kill -0 "$worker" 2>/dev/null; then
        print -- "Saved health exceeded the five-second menu budget; data remains unknown. Choose Saved health (7) to retry."
        return 124
    fi
    wait "$worker"
    result=$?
    cat -- "$capture"
    return "$result"
)

management_initial_health() {
    if [[ ! -f "$project_root/config/totalmarker.toml" ]]; then
        management_health='[?] Health needs configuration; choose Guided setup (1)'
        return 0
    fi
    management_screen_open
    print -- "Reading saved health (local only; up to five seconds)..."
    management_saved_health >/dev/null 2>&1
    local result=$?
    if (( result > 1 )); then
        management_last_kind=error
        management_last_result="Saved health inspection unavailable (exit $result); choose Saved health (7) for details."
    fi
    management_screen_reset
}

management_saved_health() {
    local records result kind title summary detail style badge count=0 header=false compact='' note='' snapshot_time=''
    records=$(management_health_records 2>/dev/null)
    result=$?
    management_health='[?] Inspection failed; no verified snapshot'
    management_health_time=''
    if (( result == 124 )); then
        management_health='[?] Saved health timed out; choose Saved health (7) to retry'
    fi
    # An exit 2 is a real inspection/storage error, even if rows were returned.
    # Keep its details visible, and never keep an earlier green snapshot.
    if (( result > 2 )) || [[ "$records" != snapshot$'\t'* ]]; then
        print -r -- "$records"
        (( result > 1 )) && return "$result"
        return 2
    fi
    while IFS=$'\t' read -r kind title summary detail; do
        if [[ "$kind" == snapshot && "$header" == false && "$title" != *[[:cntrl:]]* ]]; then
            snapshot_time="$title";header=true;continue
        fi
        if [[ "$kind" == note && "$header" == true && -z "$note" && "$title" != *[[:cntrl:]]* ]]; then
            note='[!] Status warning; review health details'
            print -r -- "$management_attention$title$management_reset"
            continue
        fi
        [[ "$header" == true && "$title" != *[[:cntrl:]]* && "$summary" != *[[:cntrl:]]* && "$detail" != *[[:cntrl:]]* && -n "$title" && -n "$summary" ]] || return 2
        (( ++count <= 7 )) || return 2
        style='' badge='[?]'
        case "$kind" in
            good) style=$management_good;badge='[+]' ;;
            warning) style=$management_attention;badge='[!]' ;;
            error) style=$management_problem;badge='[x]' ;;
            disabled) badge='[-]' ;;
            unknown) ;;
            *) return 2 ;;
        esac
        print -r -- "$style$title: $summary${detail:+ — $detail}$management_reset"
        if (( count == 5 )); then compact+=$'\n'
        elif [[ -n "$compact" ]]; then compact+='  '
        fi
        compact+="$style$badge $title$management_reset"
    done <<< "$records"
    [[ "$header" == true && "$count" == 7 ]] || return 2
    if (( result == 2 )); then management_health_time='';return 2;fi
    management_health_time="$snapshot_time"
    management_health="$compact${note:+ $note}"
    return "$result"
}

# Xplanet build is historical: this reader does not probe an executable or
# execute definitions. The explicit diagnostic validates current identity.
management_binary_facts() {
    management_binary='Build features not checked; choose Troubleshooting (9)'
    local evidence="$project_root/.state/configurator/binary-evidence.json" folder size stamp outcome schema
    for folder in "$project_root/.state" "$project_root/.state/configurator"; do
        [[ -d "$folder" && ! -L "$folder" && "${folder:A}" == "$folder" ]] || return 0
    done
    [[ -f "$evidence" && ! -L "$evidence" ]] || return 0
    size=$(/usr/bin/stat -f %z "$evidence" 2>/dev/null) || return 0
    [[ "$size" == <-> && "$size" -le 262144 ]] || return 0
    schema=$(/usr/bin/plutil -extract schema raw -expect integer -o - "$evidence" 2>/dev/null) || return 0
    [[ "$schema" == 1 ]] || return 0
    stamp=$(/usr/bin/plutil -extract report.completed_utc raw -expect string -o - "$evidence" 2>/dev/null) || return 0
    [[ "$stamp" =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$' ]] || return 0
    outcome=$(/usr/bin/plutil -extract report.status raw -expect string -o - "$evidence" 2>/dev/null) || return 0
    [[ "$outcome" == reported ]] || outcome=unknown
    management_binary="Features $outcome ${stamp[1,19]}Z; not rechecked"
}
