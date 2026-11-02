# Private terminal orchestration. Commands remain the source of operational behavior.
management_read() {
    read -r "management_reply?$1" || return 1
}

management_confirm() {
    management_read "$1 [y/N] " && [[ "$management_reply" == [Yy] ]]
}

management_state() {
    local name count=0
    for name in xp.def xp.conf earth totalmarker.toml; do
        [[ -f "$project_root/config/$name" ]] && (( count += 1 ))
    done
    case $count in
        0) print -- new ;;
        4) print -- existing ;;
        *) print -- partial ;;
    esac
}

management_prerequisites() {
    local brew_bin renderer='' python='' line value configured=false installed='' setup_result
    management_section "Prerequisites"
    # Treat shell-style definitions as configured but unverified. Only setup
    # interprets them, after the user has requested that workflow.
    if [[ -f "$project_root/config/xp.def" ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            if [[ "$line" =~ '^[[:space:]]*(export[[:space:]]+)?XPLANET_BIN=(.+)$' ]]; then
                value=$match[2]
                if [[ "$value" != '""' && "$value" != "''" ]]; then
                    configured=true
                    renderer='configured executable (setup will validate)'
                fi
            fi
        done < "$project_root/config/xp.def"
    fi
    [[ -n "$renderer" ]] || renderer=$(command -v xplanet 2>/dev/null)
    brew_bin=$(command -v brew 2>/dev/null)
    if [[ -n "$brew_bin" && ( "$brew_bin" != /* || ! -x "$brew_bin" ) ]]; then
        print -u2 -- "Homebrew must be an absolute executable on PATH."
        return 1
    fi
    if [[ -z "$renderer" && -n "$brew_bin" ]]; then
        value=$("$brew_bin" --prefix blogabe/xplanet/xplanet 2>/dev/null)
        [[ "$value" == /* && -x "$value/bin/xplanet" ]] && renderer="$value/bin/xplanet"
    fi
    python=$("$script_dir/run-totalmarker" --python-path 2>/dev/null)
    print -- "  Xplanet: ${renderer:-missing}"
    print -- "  Python 3.11+: ${python:-missing}"
    if [[ -z "$renderer" || -z "$python" ]]; then
        if [[ -z "$brew_bin" && -z "$renderer" ]]; then
            print -- "Homebrew is required to install the missing renderer. Install it separately, then return."
            management_set_result unavailable "Missing dependencies require Homebrew."
            return 1
        fi
        # An explicit override is authoritative; never conceal an invalid one.
        if [[ -z "$python" && ${+TOTALMARKER_PYTHON} == 1 ]]; then
            print -- "TOTALMARKER_PYTHON is unavailable or incompatible; correct it before continuing."
            return 1
        fi
        management_section "Missing dependencies"
        print -- "Proposed changes (Homebrew recommended):"
        [[ -n "$renderer" ]] || print -- "  Add/trust blogabe/xplanet and build its Xplanet formula. macOS approval may be needed."
        [[ -n "$python" ]] || print -- "  Choose Homebrew (recommended) or uv-managed Python."
        if ! management_confirm "Install these missing dependencies?"; then
            management_set_result cancelled "Dependency installation was not started."
            return 3
        fi
        load_helpers install
        if [[ -z "$renderer" ]]; then
            (install_renderer) || return
            value=$("$brew_bin" --prefix blogabe/xplanet/xplanet) || return
            renderer="$value/bin/xplanet"
            installed=$renderer
            [[ -x "$renderer" ]] || { print -u2 -- "Installed Xplanet executable was not found."; return 1; }
        fi
        if [[ -z "$python" ]]; then
            load_helpers python-runtime
            python_choose_runtime || return
        fi
        "$script_dir/run-totalmarker" --python-path >/dev/null || return
    fi
    if [[ -n "$python" && ! -e "$project_root/config/totalmarker.python" &&
          ${+TOTALMARKER_PYTHON} == 0 && "$(management_state)" != existing ]]; then
        load_helpers python-runtime
        python_choose_runtime || return
    fi
    management_section "Configuration, data and schedules"
    # This handoff is scoped to setup, not a persistent parallel setting.
    if [[ "$configured" == true && -z "$installed" ]]; then
        "$script_dir/xp-setup.sh"
    else
        XPLANET_INSTALLED_BIN="$renderer" "$script_dir/xp-setup.sh"
    fi
    setup_result=$?
    (( setup_result == 0 )) || return "$setup_result"
    management_section "Desktop"
    print -- "Setup completed. Start validates the current files."
    if management_confirm "Start the desktop now?"; then
        "$script_dir/xplanet.sh" start
        setup_result=$?
        if (( setup_result == 0 )); then
            management_set_result success "Setup and desktop start completed."
        else
            management_set_result error "Setup completed; start exited $setup_result."
        fi
        return "$setup_result"
    fi
    management_set_result success "Setup completed; desktop start skipped."
}

management_update_available() {
    local branch upstream
    branch=$(git -C "$project_root" symbolic-ref --quiet HEAD 2>/dev/null) &&
        upstream=$(git -C "$project_root" for-each-ref --format='%(upstream)' "$branch" 2>/dev/null) &&
        [[ "$upstream" == refs/remotes/* ]] && return 0
    print -- "Update unavailable: this checkout has no remote-tracking upstream. No changes made."
    return 1
}

# Always handles normal returns; EXIT also covers fatal helper errors.
manage_xplanet() {
    local management_reply state command result confirmation management_details
    local management_alt_on management_alt_off management_clear management_reset
    local management_heading management_good management_attention management_problem management_screen_active
    local management_last_kind=info management_last_result=''
    local management_process management_job
    local management_key management_pending_key='' management_selected=1
    local management_save management_restore management_erase_line management_partial=false management_size=''
    local -a management_row_up management_labels management_styles
    load_helpers management-view
    load_helpers management-input
    management_view_init
    trap 'management_screen_close' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    {
    while true; do
        state=$(management_state)
        management_screen_open
        management_draw "$state"
        management_choose || return 0
        case "$management_reply" in
            q|Q) return 0 ;;
            '') continue ;; # Navigation changes the highlight without activating an action.
        esac
        management_screen_reset
        management_details=false
        case "$management_reply" in
            1) management_last_result=''
               management_section "Guided setup"
               management_prerequisites
               result=$?
               if [[ -z "$management_last_result" ]]; then
                   case "$result" in
                       3) management_set_result cancelled "Setup stopped; prior preparation may remain." ;;
                       *) management_set_result error "Setup exited $result; completion was not confirmed." ;;
                   esac
               fi
               if (( result == 0 )) || [[ "$management_last_kind" == error ]]; then
                   management_details=true
               fi
               if (( result == 0 )) && [[ "$state" != existing ]]; then
                   management_pause
                   return 0
               fi ;;
            2) management_section "Configurator"
               load_helpers configurator
               configure_xplanet
               management_set_result unavailable "Configurator pending; no settings saved or applied." ;;
            3|4|5|6)
                case "$management_reply" in
                    3) command=start ;;
                    4) command=stop ;;
                    5) command=restart ;;
                    6) command=''
                       if management_update_available; then
                           command=update
                       else
                           management_set_result unavailable "Update has no remote-tracking upstream."
                       fi ;;
                esac
                if [[ -n "$command" ]]; then
                    management_section "${(C)command}"
                    case "$command" in
                        stop) confirmation="Stop ALL your Xplanet processes, including finite renders?" ;;
                        restart) confirmation="Restart: stop ALL your Xplanet processes, then start one desktop?" ;;
                        *) confirmation="Run $command?" ;;
                    esac
                    if management_confirm "$confirmation"; then
                        [[ "$command" == update ]] && management_details=true
                        "$script_dir/xplanet.sh" "$command"
                        result=$?
                        if (( result == 0 )); then
                            management_set_result success "${(C)command} completed."
                        else
                            management_details=true
                            management_set_result error "${(C)command} exited $result."
                        fi
                    else
                        management_set_result cancelled "${(C)command} was not run."
                    fi
                fi ;;
            7) management_section "Saved health"
               if [[ -f "$project_root/config/totalmarker.toml" ]]; then
                   management_details=true
                   "$script_dir/xplanet.sh" health
                   result=$?
                   if (( result == 0 )); then
                       management_set_result success "Saved health completed."
                   else
                       if (( result == 1 )); then
                           management_set_result warning "Health check completed; source issues reported."
                       else
                           management_set_result error "Health inspection failed (exit $result); review details above."
                       fi
                   fi
               else
                   print -- "Health is unavailable until setup creates your configuration. Choose 1 for guided setup."
                   management_set_result unavailable "Health needs configuration; choose Guided setup (1)."
               fi ;;
            8) management_details=true
               management_section "Advanced Python"
               load_helpers python-runtime
               python_choose_runtime change
               result=$?
               case "$result" in
                   0) management_set_result success "Python interpreter selected." ;;
                   3) management_details=false
                      management_set_result cancelled "Python selection cancelled; prior choice retained." ;;
                   *) management_set_result error "Python selection failed; prior choice retained." ;;
               esac ;;
            *) management_set_result info "Choose a listed option or q to exit." ;;
        esac
        if [[ "$management_details" == true ]]; then
            management_pause || return 0
        fi
    done
    } always {
        management_screen_close
        trap - EXIT INT TERM HUP
    }
}
