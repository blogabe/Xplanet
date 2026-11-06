# Private presentation only: no config execution, Python, network or lifecycle actions.
management_view_init() {
    local cursor_home erase_from_cursor offset movement
    # Distances from the prompt to rows 1..10 in the grouped menu below.
    local -a offsets=(16 15 12 11 10 7 6 5 4 3)
    management_alt_on='' management_alt_off='' management_clear=''
    management_reset='' management_heading='' management_good='' management_attention='' management_problem=''
    management_screen_active=false
    management_save='' management_restore='' management_erase_line=''
    if [[ -t 0 && -t 1 && -n "${TERM:-}" && "$TERM" != dumb ]] && command -v tput >/dev/null; then
        management_alt_on=$(tput smcup 2>/dev/null)
        management_alt_off=$(tput rmcup 2>/dev/null)
        cursor_home=$(tput cup 0 0 2>/dev/null)
        erase_from_cursor=$(tput ed 2>/dev/null)
        if [[ -n "$cursor_home" && -n "$erase_from_cursor" ]]; then
            management_clear="$cursor_home$erase_from_cursor"
        fi
        management_save=$(tput sc 2>/dev/null)
        management_restore=$(tput rc 2>/dev/null)
        management_erase_line=$(tput el 2>/dev/null)
        for offset in $offsets; do
            movement=$(tput cuu $offset 2>/dev/null)
            [[ -n "$movement" ]] || { management_row_up=(); break; }
            management_row_up+=("$movement")
        done
        # Deliberately avoid clear/scrollback-erase capabilities.
        if [[ -z "$management_alt_off" || -z "$management_clear" ]]; then
            management_alt_on=''
        fi
        if (( ! ${+NO_COLOR} )); then
            management_reset=$(tput sgr0 2>/dev/null)
            if [[ -n "$management_reset" ]]; then
                management_heading=$(tput setaf 4 2>/dev/null)
                management_good=$(tput setaf 2 2>/dev/null)
                management_attention=$(tput setaf 3 2>/dev/null)
                management_problem=$(tput setaf 1 2>/dev/null)
            fi
        fi
    fi
}

management_screen_open() {
    if [[ -n "$management_alt_on" ]]; then
        local rows cols
        management_size=$(stty size < /dev/tty 2>/dev/null)
        read -r rows cols <<< "$management_size"
        if [[ "$rows" != <-> || "$cols" != <-> ]] || (( rows < 34 || cols < 100 )); then
            management_screen_close
            management_alt_on=''
            management_partial=false
            print -- "Compact terminal: numbered input; full status remains in scrollback. Reopen at 100x34 or larger for arrows."
            return 0
        fi
        if [[ "$management_screen_active" != true ]]; then
            management_screen_active=true
            print -rn -- "$management_alt_on"
        fi
        management_screen_reset
        management_partial=false
        if [[ "$rows" == <-> && "$cols" == <-> ]] && (( rows >= 34 && cols >= 100 )) &&
            [[ -n "$management_save" && -n "$management_restore" && -n "$management_erase_line" && ${#management_row_up} == 10 ]]; then
            management_partial=true
        fi
    fi
}

management_screen_reset() {
    [[ "$management_screen_active" == true ]] && print -rn -- "$management_clear"
    return 0
}

management_screen_close() {
    if [[ "${management_screen_active:-false}" == true ]]; then
        print -rn -- "${management_reset:-}${management_alt_off:-}"
        management_screen_active=false
    fi
}

management_desktop_facts() {
    local result listing pid last label
    management_process='unknown'
    management_job='unknown'
    if command -v pgrep >/dev/null; then
        pgrep -u "$EUID" -x xplanet >/dev/null 2>&1
        result=$?
        case "$result" in
            0) management_process=running ;;
            1) management_process='not detected' ;;
        esac
    fi
    # A registered job is not necessarily a running process. Read only the
    # current user's registration table, never plist/config contents.
    if command -v launchctl >/dev/null && listing=$(launchctl list 2>/dev/null); then
        management_job='not registered'
        while read -r pid last label; do
            [[ "$label" == local.xplanet.desktop ]] && management_job=registered
        done <<< "$listing"
    fi
}

# Single-key acknowledgement, with queued submission newlines kept out of it.
management_pause() {
    [[ -t 0 && -t 1 ]] || return 0
    management_discard_newlines
    print -rn -- "
Press any key to continue (Ctrl-D exits): "
    management_key_read || { print; return 1; }
    print
    management_discard_newlines
}

management_section() {
    print -r -- "
${management_heading}$1${management_reset}
"
}

# In-memory UI feedback only; no persistent log or parallel operational state.
management_result_line() {
    local badge='[i] Info' style=$management_heading
    case "$management_last_kind" in
        success) badge='[+] Done' style=$management_good ;;
        cancelled) badge='[-] Cancelled' style='' ;;
        unavailable) badge='[i] Unavailable' style=$management_attention ;;
        warning) badge='[!] Issues' style=$management_attention ;;
        error) badge='[!] Problem' style=$management_problem ;;
    esac
    print -r -- "$style${1:-Last action}: $badge - $management_last_result$management_reset"
}

management_set_result() {
    management_last_kind=$1
    management_last_result=$2
    print
    management_result_line Result
}

management_item() {
    local marker=' ' style=${3:-} number=$1
    [[ "$number" == 10 ]] && number=h
    management_labels[$1]=$2
    management_styles[$1]=$style
    if [[ -n "$management_alt_on" && "$management_selected" == "$1" ]]; then
        marker='>'
        style=$management_heading
    fi
    print -r -- "$marker ${style}$number) $2${management_reset}"
}

management_rehighlight() {
    local item
    if [[ "$management_partial" == true ]]; then
        print -rn -- "$management_save"
        for item in "$1" "$management_selected"; do
            print -rn -- "$management_restore${management_row_up[$item]}"$'\r'"$management_erase_line"
            management_item "$item" "$management_labels[$item]" "$management_styles[$item]"
        done
        print -rn -- "$management_restore"
    else
        # Only cached header facts: navigation never repeats process/job probes.
        management_screen_reset
        management_draw "$state" cached
        management_prompt
    fi
}

# Align values on roomy screens; keep all text and compact spacing when narrow.
management_fact() {
    local rows cols line label="$1"
    read -r rows cols <<< "$management_size"
    for line in "${(@f)2}"; do
        if [[ "$cols" == <-> ]] && (( cols >= 100 )); then
            printf '  %-15s  %s\n' "$label" "$line"
        elif [[ -n "$label" ]]; then
            print -r -- "  $label  $line"
        else
            print -r -- "    $line"
        fi
        label=''
    done
}

management_draw() {
    local state="$1" process_icon='[-]' process_style='' setup_style='' recommendation=''
    if [[ "${2:-}" != cached ]]; then
        management_desktop_facts
        management_selection_facts
        management_binary_facts
    fi
    case "$management_process" in
        running) process_icon='[+]' process_style=$management_good ;;
        unknown) process_icon='[?]' process_style=$management_attention ;;
    esac
    if [[ "$state" != existing ]]; then
        setup_style=$management_attention
        recommendation=' [recommended]'
    fi
    local rows cols
    read -r rows cols <<< "$management_size"
    # Health contains only our own color escapes; measure its visible rows so a
    # populated snapshot does not unnecessarily disable smooth navigation.
    local health_width=0 plain line style
    for line in "${(@f)management_health}"; do
        plain=$line
        for style in "$management_good" "$management_attention" "$management_problem" "$management_reset"; do
            [[ -z "$style" ]] || plain=${plain//"$style"/}
        done
        (( ${#plain} > health_width )) && health_width=${#plain}
    done
    if (( ${#management_binary} + 19 > ${cols:-0} || ${#management_selection} + 19 > ${cols:-0} || health_width + 19 > ${cols:-0} || ${#management_last_result} + 40 > ${cols:-0} )); then management_partial=false; fi
    print -r -- "${management_heading}Xplanet management${management_reset}"
    management_fact Desktop "$process_style$process_icon xplanet: $management_process$management_reset | Job: $management_job"
    # Keep the menu reachable in short terminals; roomy screens separate facts
    # by ownership: desktop, saved evidence, then setup and last action.
    (( ${rows:-0} >= 35 )) && print
    management_fact "Next start" "$management_selection"
    management_fact "Running scene" "[?] Not identified"
    management_fact "Xplanet build" "$management_binary"
    print
    management_fact "Saved data" "$management_health"
    if [[ -n "$management_health_time" ]]; then
        management_fact Snapshot "$management_health_time (saved evidence, not a live access check; 7 products)"
        management_fact Key "[+] current  [!] stale/unverified  [x] failed  [?] unassessed  [-] disabled"
    fi
    (( ${rows:-0} >= 35 )) && print
    management_fact "Custom setup" "$state; Configurator: option 2"
    if [[ -n "$management_last_result" ]]; then
        management_result_line
    fi
    print -r -- "
${management_heading}Setup${management_reset}"
    management_item 1 "Guided setup$recommendation" "$setup_style"
    management_item 2 "Configurator"
    print -r -- "
${management_heading}Desktop${management_reset}"
    management_item 3 "Start"
    management_item 4 "Stop"
    management_item 5 "Restart"
    print -r -- "
${management_heading}Maintenance${management_reset}"
    management_item 6 "Update"
    management_item 7 "Saved health"
    management_item 8 "Advanced Python"
    management_item 9 "Diagnostics"
    management_item 10 "Help"
    print -r -- "  q) Exit"
    print
}
