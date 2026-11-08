# Private zsh helpers, sourced by xplanet.sh after root discovery.

install_failed() {
    print -u2 -- "xplanet.sh install: $1"
    exit 1
}

ask_install() {
    local answer
    read -r "answer?$1 [y/N] " || return 1
    [[ "$answer" == [Yy] ]]
}

install_xplanet() {
    local brew_bin prefix installed
    brew_bin=$(command -v brew) || fail "Homebrew is required for install"
    [[ "$brew_bin" == /* && -x "$brew_bin" ]] || fail "Homebrew must be an executable on PATH"
    install_renderer "$@" || return $?
    if [[ -t 0 && -t 1 ]]; then
        load_helpers python-runtime
        if (( ${+TOTALMARKER_PYTHON} )); then
            "$script_dir/run-totalmarker" --python-path || return
            print -- 'Using explicit TOTALMARKER_PYTHON; no provider selection changed.'
        else
            python_choose_runtime || return
        fi
    else
        install_python
    fi
    prefix=$("$brew_bin" --prefix blogabe/xplanet/xplanet) ||
        install_failed "Could not locate the installed Xplanet formula."
    [[ "$prefix" == /* ]] || install_failed "Homebrew returned a non-absolute Xplanet prefix."
    installed="$prefix/bin/xplanet"
    [[ -x "$installed" ]] || install_failed "Homebrew Xplanet binary is not executable at $installed."
    print -- "macOS may request security approval during a finite Xplanet launch. Review any prompts yourself."
    if ask_install "Render one frame to the desktop background to request macOS approvals?"; then
        (cd "$project_root" && "$installed" "-searchdir=$project_root" -num_times=1) ||
            install_failed "The one-frame Xplanet launch failed."
    else
        print -- "Skipped the approval launch; macOS permissions still need manual review."
    fi
    print -- "Xplanet and Python installation steps finished. Continuing to setup."
    XPLANET_INSTALLED_BIN="$installed" "$script_dir/xp-setup.sh"
}

install_renderer() {
    "$brew_bin" tap blogabe/xplanet || install_failed "Could not add the Xplanet tap."
    "$brew_bin" trust blogabe/xplanet ||
        install_failed "Could not trust the Xplanet tap; this Homebrew may not support 'brew trust'."
    local prefix='' receipt='' formula_path='' formula_hash='' build_options_changed=false
    local -a build_options
    load_helpers build-options
    prefix=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --prefix --installed blogabe/xplanet/xplanet 2>/dev/null)
    if [[ -n "$prefix" ]]; then
        [[ "$prefix" == /* && -f "$prefix/INSTALL_RECEIPT.json" ]] ||
            install_failed 'Existing Xplanet has no readable Homebrew receipt; use setup to keep it or review migration manually.'
        receipt="$prefix/INSTALL_RECEIPT.json"
    fi
    if [[ -z "$receipt" ]]; then
        formula_path=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" formula blogabe/xplanet/xplanet) ||
            install_failed 'Could not locate the formula being reviewed.'
        [[ "$formula_path" == /* && -f "$formula_path" ]] || install_failed 'Homebrew returned an invalid formula path.'
        formula_hash=$(shasum -a 256 < "$formula_path") || install_failed 'Could not read the formula being reviewed.'
    fi
    if [[ -n "$receipt" && $# == 0 ]]; then
        choose_build_options update "$receipt" || return $?
    else
        choose_build_options install "$receipt" "$@" || return $?
    fi
    if [[ -n "$receipt" ]]; then
        [[ "$build_options_changed" == false ]] ||
            { print -u2 -- 'Existing build choices are kept by this workflow. Use Homebrew directly to change them; no renderer was rebuilt.'; return 2; }
        print -- 'Keeping the installed renderer. Use update to check for a new formula.'
        return 0
    fi
    [[ -f "$formula_path" && "$(shasum -a 256 < "$formula_path")" == "$formula_hash" ]] ||
        install_failed 'The formula changed during review; run install again.'
    HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" install --formula --build-from-source blogabe/xplanet/xplanet \
        "${build_options[@]}" || install_failed "Could not build Xplanet from the tap source."
    prefix=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --prefix --installed blogabe/xplanet/xplanet) ||
        install_failed 'Could not find the new renderer receipt.'
    [[ -f "$prefix/.brew/xplanet.rb" && "$(shasum -a 256 < "$prefix/.brew/xplanet.rb")" == "$formula_hash" ]] ||
        install_failed 'The installed formula differs from the reviewed recipe; inspect Homebrew before continuing.'
    verify_build_options "$prefix/INSTALL_RECEIPT.json" || return 2
}

install_python() {
    "$brew_bin" install python || install_failed "Could not install Homebrew Python."
}
