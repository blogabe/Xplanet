# Intent-based navigation only; named commands own all diagnostic behavior.
management_troubleshooting_draw() {
    management_section "Troubleshooting"
    print -- "Read existing logs/evidence, or explicitly check the selected renderer."
    print -- "Scene-resource diagnosis remains in Configurator: Diagnose resources."
    if [[ -n "$management_last_result" ]]; then
        management_result_line
    fi
    print
    management_item 1 "View renderer log"
    management_item 2 "View saved renderer support"
    management_item 3 "Check renderer support now"
    management_item 4 "Back to management"
    print -- "  b) Back   q) Exit"
    print
}

management_troubleshooting_choose() {
    if [[ -z "$management_alt_on" ]]; then
        local prefix=$management_pending_key
        management_pending_key=''
        case "$prefix" in
            $'\003') exit 130 ;;
            $'\004') return 1 ;;
            b|B|q|Q) management_reply=$prefix; return 0 ;;
            up|down|escape) prefix='' ;;
        esac
        management_read "Troubleshooting choice (1-4, b back, q exit): " || return 1
        management_reply="$prefix$management_reply"
        return 0
    fi
    print -rn -- "Up/Down or 1-4: highlight; Enter: select; b: back; q: exit. Troubleshooting choice: "
    local previous
    while true; do
        management_key_read || return 1
        if [[ "$(stty size < /dev/tty 2>/dev/null)" != "$management_size" ]]; then
            [[ -n "$management_pending_key" ]] || management_pending_key=$management_key
            management_reply=''
            return 0
        fi
        previous=$management_selected
        case "$management_key" in
            up) (( management_selected > 1 )) && (( management_selected -= 1 )) ;;
            down) (( management_selected < 4 )) && (( management_selected += 1 )) ;;
            [1-4]) management_selected=$management_key ;;
            $'\n'|$'\r') management_reply=$management_selected; return 0 ;;
            b|B|q|Q) management_reply=$management_key; return 0 ;;
        esac
        if [[ "$previous" != "$management_selected" ]]; then
            management_reply=''
            return 0
        fi
    done
}

# Return 1 only to request exit from management (q/EOF). Keep selection local so
# returning to the main screen restores its highlight and fixed row geometry.
management_troubleshooting() {
    local management_selected=1 management_reply='' result
    local -a management_labels management_styles
    while true; do
        management_screen_open
        management_troubleshooting_draw
        management_troubleshooting_choose || return 1
        case "$management_reply" in
            q|Q) return 1 ;;
            4|b|B) return 0 ;;
            '') continue ;;
        esac
        management_screen_reset
        case "$management_reply" in
            1) management_section "Renderer log"
               print -- "Read-only view of logs/xplanet-error.log; exact repeat resize notices are counted."
               if [[ ! -e "$project_root/logs/xplanet-error.log" && ! -L "$project_root/logs/xplanet-error.log" ]]; then
                   print -- "No renderer log exists at logs/xplanet-error.log. Nothing was created."
                   management_set_result unavailable "Renderer log is absent; no log to display."
               else
                   "$script_dir/xplanet.sh" log-view
                   result=$?
                   case "$result" in
                       0) management_set_result success "Renderer log displayed; original log unchanged." ;;
                       1) management_set_result warning "Renderer log changed during reading; this view may be incomplete." ;;
                       *) management_set_result error "Renderer log inspection failed (exit $result); review details above." ;;
                   esac
               fi ;;
            2) management_section "Saved renderer support"
               print -- "Read existing evidence without running Xplanet; it may be missing, stale or unknown."
               "$script_dir/xplanet.sh" diagnostics --show
               result=$?
               case "$result" in
                   0) management_set_result success "Saved renderer support displayed; running process not identified." ;;
                   1) management_set_result warning "Saved renderer support is missing, stale or unknown; no probe was run." ;;
                   *) management_set_result error "Saved renderer support inspection failed (exit $result); review details above." ;;
               esac ;;
            3) management_section "Check renderer support"
               print -- 'Explicitly run the selected renderer version probe and record private support evidence.'
               print -- 'No provider refresh, desktop start or service changes. Use Help for diagnostic switches.'
               management_read "Capture renderer support now? [y/N] " || return 1
               if [[ "$management_reply" != [Yy] ]]; then
                   management_set_result cancelled "Renderer diagnostic was not run."
                   continue
               fi
               "$script_dir/xplanet.sh" diagnostics
               result=$?
               case "$result" in
                   0) management_set_result success "Renderer support captured; running process not identified." ;;
                   1) management_set_result warning "Diagnostic completed; renderer support remains unknown." ;;
                   *) management_set_result error "Renderer inspection failed (exit $result); review details above." ;;
               esac ;;
            *) management_set_result info "Choose a listed option, b to return or q to exit."
               continue ;;
        esac
        # In particular, never clear the filtered log until an actual keypress.
        # The shared pause ignores queued submission newlines and restores modes.
        management_pause || return 1
    done
}
