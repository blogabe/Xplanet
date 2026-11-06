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
    install_renderer
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
    "$brew_bin" install --formula --build-from-source blogabe/xplanet/xplanet \
        --without-giflib --with-cspice ||
        install_failed "Could not build Xplanet from the tap source."
}

install_python() {
    "$brew_bin" install python || install_failed "Could not install Homebrew Python."
}
