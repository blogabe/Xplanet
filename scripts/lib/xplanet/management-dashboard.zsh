# Read-only metadata and explicit saved-health snapshots. No Python on entry.
management_selection_facts() {
    management_selection='legacy configuration (no selector)'
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

management_saved_health() {
    local records result kind title summary detail style badge count=0 header=false compact='' note='' snapshot_time=''
    records=$("$script_dir/xplanet.sh" health --dashboard)
    result=$?
    management_health='[?] Inspection failed; no verified snapshot'
    management_health_time=''
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
        compact+="${compact:+ }$style$badge $title$management_reset"
    done <<< "$records"
    [[ "$header" == true && "$count" == 7 ]] || return 2
    if (( result == 2 )); then management_health_time='';return 2;fi
    management_health_time="$snapshot_time"
    management_health="$compact${note:+ $note}"
    return "$result"
}

# Historical evidence only: no interpreter, executable, legacy definitions or
# providers run on menu entry. The explicit diagnostic validates current identity.
management_binary_facts() {
    management_binary='not checked; run diagnostics explicitly'
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
    management_binary="$outcome ${stamp[1,19]}Z; not revalidated for next start/running"
}
