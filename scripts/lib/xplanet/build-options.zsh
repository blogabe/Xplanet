# Build choices belong to Homebrew receipts, not a second saved configuration.
build_option_error() {
    print -u2 -r -- "xplanet.sh: $1"
    return 2
}

build_option_json() {
    local -a expectation
    [[ -z "${3:-}" ]] || expectation=(-expect "$3")
    /usr/bin/plutil -extract "$2" raw "${expectation[@]}" -o - "$1" 2>/dev/null
}

# Preserve embedded/trailing whitespace rather than trimming it into a valid flag.
build_option_flag() {
    local value
    value=$(/usr/bin/plutil -extract "$2" raw -expect string -o - "$1" 2>/dev/null && print -rn -- '.') || return 2
    value=${value%.}
    value=${value%$'\n'}
    [[ "$value" =~ '^--(with|without)-[A-Za-z0-9-]+$' ]] || return 2
    REPLY=$value
}

build_option_normalize() {
    REPLY=$1
    [[ "$REPLY" != --without-jpeg ]] || REPLY=--without-jpeg-turbo
}

build_option_metadata() {
    local file=$1 count index flag key description
    [[ "$(build_option_json "$file" formulae array)" == 1 &&
       "$(build_option_json "$file" formulae.0.full_name)" == blogabe/xplanet/xplanet ]] ||
        { build_option_error 'Homebrew did not return the expected Xplanet formula.'; return 2; }
    count=$(build_option_json "$file" formulae.0.options array) || return 2
    [[ "$count" == <-> && "$count" -gt 0 && "$count" -le 32 ]] ||
        { build_option_error 'Homebrew returned an unsupported build-options list.'; return 2; }
    build_flags=() build_labels=() build_descriptions=() build_defaults=()
    for ((index = 0; index < count; index++)); do
        build_option_flag "$file" "formulae.0.options.$index.option" || return 2
        flag=$REPLY
        [[ "$flag" =~ '^--(with|without)-[a-z0-9][a-z0-9-]*$' ]] ||
            { build_option_error 'The formula contains an unsupported build option; use Homebrew directly.'; return 2; }
        [[ "${build_flags[(Ie)$flag]}" == 0 ]] || return 2
        [[ "$flag" != --with-all ]] || { build_has_all=true; continue; }
        key=${flag#--with-}; key=${key#--without-}
        description=$(build_option_json "$file" "formulae.0.options.$index.description" string) || return 2
        # Formula text is display data, never terminal control or shell syntax.
        description=${description//[^[:print:]]/ }
        case "$key" in
            jpeg|jpeg-turbo) key=JPEG; description='Read and write JPEG images' ;;
            libpng) key=PNG; description='Required for macOS wallpaper' ;;
            giflib) key=GIF; description='Read and write GIF images' ;;
            libtiff) key=TIFF; description='Read and write TIFF images' ;;
            cspice) key=CSPICE; description='JPL SPICE astronomy support' ;;
            pango) key=Pango; description='International text rendering (extra dependencies)' ;;
            netpbm) key=PNM; description='Netpbm image formats (extra dependencies)' ;;
            *) build_option_error "No Xplanet capability mapping for $flag; review the formula before building."; return 2 ;;
        esac
        build_flags+=("$flag") build_labels+=("$key") build_descriptions+=("${description[1,100]}")
        if [[ "$flag" == --without-* ]]; then build_defaults+=(1); else build_defaults+=(0); fi
    done
    (( ${#build_flags} > 0 )) || return 2
    # Keep the feature groups familiar even if Homebrew changes option order.
    local label item
    local -a order flags labels descriptions defaults
    for label in JPEG PNG GIF TIFF CSPICE Pango PNM; do
        item=${build_labels[(Ie)$label]}
        (( item == 0 )) || order+=("$item")
    done
    for item in {1..${#build_flags}}; do
        (( ${order[(Ie)$item]} > 0 )) || order+=("$item")
    done
    for item in "${order[@]}"; do
        flags+=("$build_flags[$item]") labels+=("$build_labels[$item]")
        descriptions+=("$build_descriptions[$item]") defaults+=("$build_defaults[$item]")
    done
    build_flags=("${flags[@]}") build_labels=("${labels[@]}")
    build_descriptions=("${descriptions[@]}") build_defaults=("${defaults[@]}")
    build_selected=("${build_defaults[@]}")
}

build_option_apply() {
    local flag index
    for flag in "$@"; do
        build_option_normalize "$flag"; flag=$REPLY
        if [[ "$flag" == --with-all && "$build_has_all" == true ]]; then
            for index in {1..${#build_flags}}; do
                case "$build_flags[$index]" in
                    --with-cspice|--with-netpbm|--with-pango) build_selected[$index]=1 ;;
                esac
            done
            continue
        fi
        index=${build_flags[(Ie)$flag]}
        (( index > 0 )) || { build_option_error "Build option is no longer supported: $flag. Review it with Homebrew before continuing."; return 2; }
        build_selected[$index]=$((1 - build_defaults[$index]))
    done
}

build_option_read_receipt() {
    local file=$1 count index flag
    [[ "$(build_option_json "$file" source.tap)" == blogabe/xplanet ]] ||
        { build_option_error 'The installed renderer is not from blogabe/xplanet; use setup to keep it, or review migration manually.'; return 2; }
    count=$(build_option_json "$file" used_options array) || return 2
    [[ "$count" == <-> && "$count" -le 32 ]] || return 2
    build_installed=()
    for ((index = 0; index < count; index++)); do
        build_option_flag "$file" "used_options.$index" ||
            { build_option_error 'Installed Xplanet has an unsupported build option; review it with Homebrew.'; return 2; }
        flag=$REPLY
        [[ "$flag" =~ '^--(with|without)-[A-Za-z0-9-]+$' ]] ||
            { build_option_error 'Installed Xplanet has an unsupported build option; review it with Homebrew.'; return 2; }
        build_option_normalize "$flag"
        build_installed+=("$REPLY")
    done
    build_option_apply "${build_installed[@]}"
}

build_option_generate() {
    local index
    build_options=()
    for index in {1..${#build_flags}}; do
        [[ "$build_selected[$index]" == "$build_defaults[$index]" ]] || build_options+=("$build_flags[$index]")
    done
}

build_option_summary() {
    local index enabled='' disabled=''
    for index in {1..${#build_flags}}; do
        if [[ "$build_selected[$index]" == 1 ]]; then
            enabled+="${enabled:+, }$build_labels[$index]"
        else
            disabled+="${disabled:+, }$build_labels[$index]"
        fi
    done
    print -r -- "  Enabled:  ${enabled:-none}"
    print -r -- "  Disabled: ${disabled:-none}"
}

build_option_menu() {
    setopt localtraps
    local management_key='' management_pending_key='' selected=$((${#build_flags}+1)) index mark box
    local heading='' reset='' alt='' end='' clear='' rows cols reply details=false
    source "$script_dir/lib/xplanet/management-input.zsh" || return 2
    if [[ -n "${TERM:-}" && "$TERM" != dumb ]] && command -v tput >/dev/null; then
        read -r rows cols <<< "$(stty size < /dev/tty 2>/dev/null)"
        if [[ "$rows" == <-> && "$cols" == <-> ]] && (( rows >= ${#build_flags}+16 && cols >= 80 )); then
            alt=$(tput smcup 2>/dev/null); end=$(tput rmcup 2>/dev/null)
            clear="$(tput cup 0 0 2>/dev/null)$(tput ed 2>/dev/null)"
            [[ -n "$end" && -n "$clear" ]] || alt=''
        fi
        if (( ! ${+NO_COLOR} )); then heading=$(tput setaf 4 2>/dev/null); reset=$(tput sgr0 2>/dev/null); fi
    fi
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    {
        [[ -z "$alt" ]] || print -rn -- "$alt"
        while true; do
            [[ -z "$alt" ]] || print -rn -- "$clear"
            print -r -- "${heading}Xplanet build options${reset}"
            print -r -- "$build_origin"
            print -- 'Space toggles a feature. Continue uses the choices shown.'
            print
            for index in {1..${#build_flags}}; do
                [[ "$index" != 1 ]] || print -r -- "${heading}Image formats${reset}"
                [[ "$build_labels[$index]" != CSPICE ]] || print -r -- "${heading}Additional capabilities${reset}"
                box=' '; [[ "$build_selected[$index]" != 1 ]] || box=x
                [[ "$build_labels[$index]" != PNG ]] || box='*'
                mark=' '; (( index != selected )) || mark='>'
                [[ "$mark" != ">" ]] || print -rn -- "$heading"
                printf '%s %2d) [%s] %-8s %s\n' "$mark" "$index" "$box" "$build_labels[$index]" "$build_descriptions[$index]"
                print -rn -- "$reset"
            done
            print -- '      [*] Required: PNG for macOS wallpaper; FreeType is included'
            print
            for index in $((${#build_flags}+1)) $((${#build_flags}+2)); do
                mark=' '; (( index != selected )) || mark='>'
                if (( index == ${#build_flags}+1 )); then reply='Continue with these choices'; else reply='Reset recommended choices'; fi
                print -r -- "$mark $index) $reply"
            done
            print -- '  d) Details    q) Cancel'
            if [[ "$details" == true ]]; then
                build_option_generate
                if (( ${#build_options} )); then
                    print -r -- "Homebrew options: ${(j: :)build_options}"
                else
                    print -- "Homebrew options: (formula defaults)"
                fi
                print -- 'A changed choice requires a source rebuild. macOS approval may be needed.'
            fi
            if [[ -n "$alt" ]]; then
                print -rn -- 'Up/Down: move; Space: toggle; Enter: select; q: cancel: '
                management_key_read || return 3
                reply=$management_key
            else
                read -r "reply?Number to toggle, Enter to continue, d for details, q to cancel: " || return 3
                [[ -n "$reply" ]] || reply=$((${#build_flags}+1))
            fi
            case "$reply" in
                q|Q|escape) return 3 ;;
                d|D) [[ "$details" == false ]] && details=true || details=false ;;
                up) (( selected > 1 )) && (( selected -= 1 )) ;;
                down) (( selected < ${#build_flags}+2 )) && (( selected += 1 )) ;;
                ' '|$'\n'|$'\r') reply=$selected ;;
            esac
            if [[ "$reply" == <-> ]]; then
                index=$reply
                if (( index >= 1 && index <= ${#build_flags} )); then
                    [[ "$build_labels[$index]" == PNG ]] || build_selected[$index]=$((1 - build_selected[$index]))
                    selected=$index
                elif (( index == ${#build_flags}+1 )); then
                    return 0
                elif (( index == ${#build_flags}+2 )); then
                    build_selected=("${build_defaults[@]}")
                fi
            fi
        done
    } always {
        [[ -z "$alt" ]] || print -rn -- "$reset$end"
    }
}

# The caller owns build_options; all UI state is temporary.
choose_build_options() {
    setopt localtraps
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    local mode=$1 receipt=$2; shift 2
    local metadata result flag index REPLY build_has_all=false build_origin='Formula defaults (no personal preferences)'
    local -a build_flags build_labels build_descriptions build_defaults build_selected build_installed prior
    metadata=$(mktemp "${TMPDIR:-/tmp}/xplanet-build-options.XXXXXXXX") || return 2
    {
        HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" info --json=v2 --formula blogabe/xplanet/xplanet > "$metadata" ||
            { build_option_error 'Could not read Xplanet build options from Homebrew.'; return 2; }
        build_option_metadata "$metadata" || return 2
        if [[ -n "$receipt" ]]; then
            build_option_read_receipt "$receipt" || return 2
            build_origin='Installed choices (from the Homebrew receipt)'
        fi
        prior=("${build_selected[@]}")
        if [[ "$mode" == update ]]; then
            if (( $# )) && [[ "$1" != --keep-options || $# != 1 ]]; then
                build_option_error 'Update preserves installed build choices; use install --help for build-option guidance.'
                return 2
            fi
            if [[ -t 0 && -t 1 && $# == 0 ]]; then
                print -- 'Xplanet update keeps your saved Homebrew build choices:'
                build_option_summary
                print -- 'Features left at defaults follow the current formula.'
                local answer
                read -r "answer?Continue with these choices? [Y/n] " || return 3
                case "$answer" in ''|[Yy]) ;; *) return 3 ;; esac
            fi
        elif (( $# )); then
            case "$1" in
                --defaults) (( $# == 1 )) || return 2; build_selected=("${build_defaults[@]}") ;;
                --keep-options) (( $# == 1 )) && [[ -n "$receipt" ]] || return 2 ;;
                *) build_selected=("${build_defaults[@]}"); build_option_apply "$@" || return 2 ;;
            esac
        elif [[ -t 0 && -t 1 ]]; then
            build_option_menu || return $?
        elif [[ -z "$receipt" ]]; then
            build_option_error 'Noninteractive install requires --defaults or explicit --with/--without options.'
            return 2
        fi
        index=${build_labels[(Ie)PNG]}
        if [[ "$mode" == install && ( "$index" == 0 || "$build_selected[$index]" != 1 ) ]]; then
            build_option_error 'PNG support is required for macOS wallpaper. Use Homebrew directly for a non-desktop build.'
            return 2
        fi
        build_option_generate
        # Homebrew reinstall adds options to the old receipt; it cannot remove
        # existing options. Never pretend deselection worked or alter receipts.
        if [[ -n "$receipt" ]]; then
            local -a requested=("${build_selected[@]}")
            build_selected=("${build_defaults[@]}")
            build_option_apply "${build_installed[@]}" "${build_options[@]}" || return 2
            if [[ "${(j: :)requested}" != "${(j: :)build_selected}" ]]; then
                build_option_error 'Homebrew cannot remove previously recorded build options during reinstall. Your installation is unchanged; keep the installed choices or change options manually with Homebrew.'
                return 2
            fi
            build_options_changed=false
            [[ "${(j: :)prior}" == "${(j: :)requested}" ]] || build_options_changed=true
        else
            build_options_changed=true
        fi
        print -- 'Xplanet build choices:'
        build_option_summary
    } always {
        rm -f -- "$metadata"
    }
}

verify_build_options() {
    local receipt=$1 expected actual REPLY flag count index
    local -a recorded wanted
    wanted=("${build_options[@]}")
    count=$(build_option_json "$receipt" used_options array) || return 2
    [[ "$count" == <-> && "$count" -le 32 ]] || return 2
    for ((index = 0; index < count; index++)); do
        build_option_flag "$receipt" "used_options.$index" || return 2
        flag=$REPLY
        build_option_normalize "$flag"; recorded+=("$REPLY")
    done
    # --with-all is equivalent to the three optional capabilities, not a fourth.
    if (( ${recorded[(Ie)--with-all]} )); then
        recorded=(${recorded:#--with-all} --with-cspice --with-netpbm --with-pango)
    fi
    expected="${(j: :)${(ou)wanted[@]}}" actual="${(j: :)${(ou)recorded[@]}}"
    [[ "$expected" == "$actual" ]] ||
        { build_option_error 'Homebrew returned different build options than requested; inspect the receipt before restarting.'; return 2; }
}


build_options_arguments() {
    local arg
    if [[ "${1:-}" == --help || "${1:-}" == --defaults || "${1:-}" == --keep-options ]]; then
        (( $# == 1 )) || { build_option_error 'Use one selection mode or explicit formula options, not both.'; return 2; }
        return 0
    fi
    for arg in "$@"; do
        [[ "$arg" =~ '^--(with|without)-[A-Za-z0-9-]+$' ]] ||
            { build_option_error 'Expected --defaults, --keep-options or exact formula --with/--without options; use install --help.'; return 2; }
    done
}

build_options_help() {
    cat <<'HELP'
Usage: scripts/xplanet.sh install [--defaults | --keep-options | FORMULA OPTIONS]
       scripts/xplanet.sh update [--keep-options]

Interactive: review preselected features; Space toggles, Enter continues.
Fresh installs show Xplanet capabilities with sensible defaults. PNG is required
for macOS wallpaper. Updates preserve choices from the installed Homebrew receipt.
--defaults      Explicitly select formula defaults (also for noninteractive install).
--keep-options  Keep the current Homebrew receipt choices without a menu.
FORMULA OPTIONS Exact --with/--without flags from brew options blogabe/xplanet/xplanet.
                These select from formula defaults, not from personal preferences.

Update rebuilds only if the recipe changes; --keep-options skips its review.
Homebrew reinstall retains old flags, so this workflow does not offer an option
reset. No receipt is edited or existing renderer uninstalled by this menu.
Noninteractive update preserves installed options. Feature flags apply to install.
No renderer is rebuilt on Cancel, Ctrl-C or Ctrl-D; earlier Git/tap updates may remain.
HELP
}
