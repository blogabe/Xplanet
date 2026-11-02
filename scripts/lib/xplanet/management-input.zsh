# Private terminal input. The short timeout only assembles one escape sequence;
# ordinary menu input and continuation never advance on a timer.
management_key_read() {
    local part sequence='' count
    if [[ -n "$management_pending_key" ]]; then
        management_key=$management_pending_key
        management_pending_key=''
    else
        read -r -s -k1 management_key || return 1
    fi
    case "$management_key" in
        $'\003') exit 130 ;;
        $'\004') return 1 ;;
        $'\033')
            management_key=escape
            if read -r -s -k1 -t 0.05 part; then
                sequence=$part
                if [[ "$part" == '[' || "$part" == O ]]; then
                    for count in {1..32}; do
                        read -r -s -k1 -t 0.05 part || break
                        case "$part" in
                            $'\003') exit 130 ;;
                            $'\004') return 1 ;;
                            $'\n'|$'\r') break ;;
                        esac
                        sequence+=$part
                        [[ "$part" == [@-~] ]] && break
                    done
                    case "$sequence" in
                        '[A'|OA) management_key=up ;;
                        '[B'|OB) management_key=down ;;
                    esac
                else
                    # A standalone Escape must not consume the next menu key.
                    management_pending_key=$part
                fi
            fi ;;
    esac
}

# Ignore only already queued submission newlines, preserving the next actual key.
management_discard_newlines() {
    [[ -z "$management_pending_key" ]] || return 0
    local key
    while read -r -s -k1 -t 0 key; do
        case "$key" in
            $'\n'|$'\r') ;;
            *) management_pending_key=$key; break ;;
        esac
    done
    return 0
}

management_choose() {
    if [[ -z "$management_alt_on" ]]; then
        local prefix=$management_pending_key
        management_pending_key=''
        case "$prefix" in
            $'\003') exit 130 ;;
            $'\004') return 1 ;;
        esac
        management_read "Choose: " || return 1
        management_reply="$prefix$management_reply"
        return 0
    fi
    local previous
    management_prompt
    while true; do
        management_key_read || return 1
        # Check geometry before touching cached row positions. Preserve this key
        # across the full redraw; no status probing or idle polling is needed.
        if [[ "$(stty size < /dev/tty 2>/dev/null)" != "$management_size" ]]; then
            [[ -n "$management_pending_key" ]] || management_pending_key=$management_key
            management_reply=''
            return 0
        fi
        previous=$management_selected
        case "$management_key" in
            up) (( management_selected > 1 )) && (( management_selected -= 1 )) ;;
            down) (( management_selected < 8 )) && (( management_selected += 1 )) ;;
            [1-8]) management_selected=$management_key ;;
            $'\n'|$'\r') management_reply=$management_selected; return 0 ;;
            q|Q) management_reply=q; return 0 ;;
        esac
        [[ "$previous" == "$management_selected" ]] || management_rehighlight "$previous"
    done
}

management_prompt() {
    print -rn -- "Up/Down or 1-8: highlight; Enter: select; q: exit. Choose: "
}
