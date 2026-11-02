# Private presentation only: no config execution, Python, network or lifecycle actions.
management_view_init() {
    local cursor_home erase_from_cursor offset movement
    # Distances from the prompt to rows 1..8 in the grouped menu below.
    local -a offsets=(14 13 10 9 8 5 4 3)
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
        if [[ "$management_screen_active" != true ]]; then
            management_screen_active=true
            print -rn -- "$management_alt_on"
        fi
        management_screen_reset
        local rows cols
        management_size=$(stty size < /dev/tty 2>/dev/null)
        read -r rows cols <<< "$management_size"
        management_partial=false
        if [[ "$rows" == <-> && "$cols" == <-> ]] && (( rows >= 24 && cols >= 60 )) &&
            [[ -n "$management_save" && -n "$management_restore" && -n "$management_erase_line" && ${#management_row_up} == 8 ]]; then
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
    local marker=' ' style=${3:-}
    management_labels[$1]=$2
    management_styles[$1]=$style
    if [[ -n "$management_alt_on" && "$management_selected" == "$1" ]]; then
        marker='>'
        style=$management_heading
    fi
    print -r -- "$marker ${style}$1) $2${management_reset}"
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

management_draw() {
    local state="$1" process_icon='[-]' process_style='' setup_style='' recommendation=''
    [[ "${2:-}" == cached ]] || management_desktop_facts
    case "$management_process" in
        running) process_icon='[+]' process_style=$management_good ;;
        unknown) process_icon='[?]' process_style=$management_attention ;;
    esac
    if [[ "$state" != existing ]]; then
        setup_style=$management_attention
        recommendation=' [recommended]'
    fi
    print -r -- "${management_heading}Xplanet management${management_reset}"
    print -r -- "Desktop  $process_style$process_icon xplanet: $management_process$management_reset | Job: $management_job"
    print -r -- "Data health  [?] Dashboard pending; saved health (7)"
    print -r -- "Config  [i] $state configuration; editor placeholder (2)"
    if [[ -n "$management_last_result" ]]; then
        management_result_line
    fi
    print -r -- "
${management_heading}Setup${management_reset}"
    management_item 1 "Guided setup$recommendation" "$setup_style"
    management_item 2 "Configurator (placeholder)"
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
    print -r -- "  q) Exit"
    print
}
