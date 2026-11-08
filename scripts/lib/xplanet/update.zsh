# Private zsh helpers, sourced by xplanet.sh after root discovery.

update_repository() {
    local git_bin branch remote source_ref tracking_ref current_root dirty target starting_head
    git_bin=$(command -v git) || fail "Git is required for update"
    current_root=$("$git_bin" -C "$project_root" rev-parse --show-toplevel) ||
        fail "update requires a Git checkout"
    [[ "$current_root" == "$project_root" ]] ||
        fail "update must run from this project's checkout root"
    branch=$("$git_bin" -C "$project_root" symbolic-ref --quiet --short HEAD) ||
        fail "update requires a checked-out branch"
    starting_head=$("$git_bin" -C "$project_root" rev-parse --verify 'HEAD^{commit}') ||
        fail "could not inspect the current commit"
    remote=$("$git_bin" -C "$project_root" config --get "branch.$branch.remote") ||
        fail "branch $branch has no configured upstream remote"
    source_ref=$("$git_bin" -C "$project_root" config --get "branch.$branch.merge") ||
        fail "branch $branch has no configured upstream branch"
    [[ "$remote" != . && "$source_ref" == refs/heads/* ]] ||
        fail "update requires a remote branch upstream"
    "$git_bin" -C "$project_root" remote get-url "$remote" >/dev/null ||
        fail "configured upstream remote $remote is unavailable"
    dirty=$("$git_bin" -C "$project_root" status --porcelain=v1 --untracked-files=no) ||
        fail "could not inspect local changes"
    [[ -z "$dirty" ]] || fail "local tracked changes exist; commit or handle them before update"
    tracking_ref=$("$git_bin" -C "$project_root" for-each-ref --format='%(upstream)' "refs/heads/$branch") ||
        fail "could not inspect the configured upstream tracking ref"
    [[ "$tracking_ref" == refs/remotes/* ]] ||
        fail "update requires a remote-tracking upstream ref"
    print -- "Checking the configured Git upstream..."
    "$git_bin" -C "$project_root" fetch --no-tags --no-recurse-submodules \
        --refmap= "$remote" "$source_ref:$tracking_ref" || fail "could not fetch configured upstream"
    target=$("$git_bin" -C "$project_root" rev-parse --verify 'FETCH_HEAD^{commit}') ||
        fail "fetched upstream is not a commit"
    [[ "$("$git_bin" -C "$project_root" symbolic-ref --quiet --short HEAD)" == "$branch" &&
       "$("$git_bin" -C "$project_root" rev-parse --verify 'HEAD^{commit}')" == "$starting_head" ]] ||
        fail "checkout changed during fetch; update stopped"
    [[ "$("$git_bin" -C "$project_root" config --get "branch.$branch.remote")" == "$remote" &&
       "$("$git_bin" -C "$project_root" config --get "branch.$branch.merge")" == "$source_ref" &&
       "$("$git_bin" -C "$project_root" for-each-ref --format='%(upstream)' "refs/heads/$branch")" == "$tracking_ref" ]] ||
        fail "upstream changed during fetch; update stopped"
    dirty=$("$git_bin" -C "$project_root" status --porcelain=v1 --untracked-files=no) ||
        fail "could not recheck local changes"
    [[ -z "$dirty" ]] || fail "local tracked changes appeared during fetch; update stopped"
    "$git_bin" -C "$project_root" merge-base --is-ancestor "$starting_head" "$target" ||
        fail "upstream diverged; update requires a fast-forward"
    "$git_bin" -C "$project_root" -c core.hooksPath=/dev/null \
        merge --ff-only --no-autostash \
        --no-overwrite-ignore "$target" ||
        fail "fast-forward blocked by local files or another checkout change"
}

update_tap_formula() {
    local brew_bin git_bin tap_root prefix receipt formula_path installed_path
    local installed_commit installed_blob current_blob installed_rel current_rel
    local installed_tap count option index refreshed_prefix refreshed_receipt
    local refreshed_commit refreshed_blob tap_dirty running_before
    local -a options
    brew_bin=$(command -v brew) || fail "Git checkout updated, but Homebrew is unavailable; the Xplanet formula was not checked"
    [[ "$brew_bin" == /* && -x "$brew_bin" ]] || fail "Homebrew must be an executable on PATH"
    git_bin=$(command -v git) || fail "Git is required to compare the installed Xplanet formula"
    [[ -x /usr/bin/plutil ]] || fail "macOS plutil is required to read the installed Xplanet receipt"
    print -- "Checking the blogabe/xplanet Homebrew formula..."
    "$brew_bin" update || fail "Git checkout updated, but Homebrew could not update its taps; Xplanet was not reinstalled"
    tap_root=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --repository blogabe/xplanet) ||
        fail "the blogabe/xplanet tap is unavailable"
    prefix=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --prefix --installed blogabe/xplanet/xplanet) ||
        fail "the tap's Xplanet formula is not installed; use install"
    formula_path=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" formula blogabe/xplanet/xplanet) ||
        fail "the tap's Xplanet formula is unavailable"
    [[ "$tap_root" == /* && -d "$tap_root" && "$prefix" == /* &&
       "$formula_path" == "$tap_root/"* ]] || fail "Homebrew returned an unexpected tap or formula path"
    receipt="$prefix/INSTALL_RECEIPT.json"
    [[ -f "$receipt" ]] || fail "installed Xplanet has no Homebrew receipt; cannot verify its build"
    installed_tap=$(/usr/bin/plutil -extract source.tap raw -o - "$receipt") ||
        fail "installed Xplanet receipt has no tap identity"
    [[ "$installed_tap" == blogabe/xplanet ]] ||
        fail "installed Xplanet came from $installed_tap, not blogabe/xplanet; refusing to switch formula"
    installed_path=$(/usr/bin/plutil -extract source.path raw -o - "$receipt") ||
        fail "installed Xplanet receipt has no formula path"
    installed_commit=$(/usr/bin/plutil -extract source.tap_git_head raw -o - "$receipt") ||
        fail "installed Xplanet receipt has no tap commit; review its build options and reinstall manually"
    [[ "$installed_path" == "$tap_root/"* &&
       "$installed_commit" =~ '^[0-9a-f]{40,64}$' ]] ||
        fail "installed Xplanet formula provenance is not verifiable"
    installed_rel="${installed_path#$tap_root/}"
    current_rel="${formula_path#$tap_root/}"
    [[ "$installed_rel" == xplanet.rb || "$installed_rel" == Formula/xplanet.rb ]] ||
        fail "installed Xplanet receipt names an unexpected formula file"
    [[ "$current_rel" == xplanet.rb || "$current_rel" == Formula/xplanet.rb ]] ||
        fail "the tap names an unexpected Xplanet formula file"
    tap_dirty=$("$git_bin" -C "$tap_root" status --porcelain=v1 -- "$current_rel") ||
        fail "could not inspect the tap formula checkout"
    [[ -z "$tap_dirty" ]] ||
        fail "the tap formula has local changes; refusing to reinstall from an uncommitted recipe"
    # Tap HEAD can advance for unrelated commits; compare the committed formula bytes.
    installed_blob=$("$git_bin" -C "$tap_root" rev-parse --verify "$installed_commit:$installed_rel") ||
        fail "installed Xplanet formula commit is unavailable; review its build options and reinstall manually"
    current_blob=$("$git_bin" -C "$tap_root" rev-parse --verify "HEAD:$current_rel") ||
        fail "current tap formula is not committed; cannot compare recipes"
    local receipt_digest
    receipt_digest=$(shasum -a 256 "$receipt") || fail "could not snapshot the installed build choices"
    local build_options_changed=false
    local -a build_options
    load_helpers build-options
    if [[ "$installed_blob" == "$current_blob" ]]; then
        choose_build_options update "$receipt" --keep-options || return $?
    else
        choose_build_options update "$receipt" "$@" || return $?
    fi
    if [[ "$installed_blob" == "$current_blob" && "$build_options_changed" == false ]]; then
        print -- "Xplanet tap formula unchanged; no reinstall needed."
        return 0
    fi
    [[ "$(shasum -a 256 "$receipt")" == "$receipt_digest" ]] ||
        fail "the installed build changed during review; run update again"
    # Pin the reviewed recipe across the interactive choice screen.
    [[ "$("$git_bin" -C "$tap_root" rev-parse --verify "HEAD:$current_rel")" == "$current_blob" &&
       -z "$("$git_bin" -C "$tap_root" status --porcelain=v1 -- "$current_rel")" ]] ||
        fail "the tap formula changed during review; run update again"
    running_before=$(desktop_status) ||
        fail "could not inspect this user's Xplanet processes before reinstall"
    print -- "Xplanet tap formula changed; rebuilding from source with installed options."
    HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" reinstall --formula --build-from-source \
        blogabe/xplanet/xplanet "${build_options[@]}" ||
        fail "Xplanet formula reinstall failed; the Git checkout may already be updated"
    refreshed_prefix=$(HOMEBREW_NO_AUTO_UPDATE=1 "$brew_bin" --prefix --installed blogabe/xplanet/xplanet) ||
        fail "Xplanet reinstall returned success, but no installed formula was found"
    refreshed_receipt="$refreshed_prefix/INSTALL_RECEIPT.json"
    [[ -f "$refreshed_receipt" ]] ||
        fail "Xplanet reinstall returned success without an installed receipt"
    [[ "$(/usr/bin/plutil -extract source.tap raw -o - "$refreshed_receipt")" == blogabe/xplanet ]] ||
        fail "Xplanet reinstall did not retain the blogabe/xplanet tap"
    refreshed_commit=$(/usr/bin/plutil -extract source.tap_git_head raw -o - "$refreshed_receipt") ||
        fail "Xplanet reinstall did not record tap provenance"
    refreshed_blob=$("$git_bin" -C "$tap_root" rev-parse --verify "$refreshed_commit:$current_rel") ||
        fail "Xplanet reinstall provenance cannot be verified"
    [[ "$refreshed_blob" == "$current_blob" ]] ||
        fail "Xplanet reinstall did not record the updated formula; check Homebrew before retrying"
    verify_build_options "$refreshed_receipt" || fail "Xplanet rebuild options could not be verified; no automatic restart was attempted"
    print -- "Xplanet tap formula and build options verified."
    if [[ -n "$running_before" ]]; then
        print -- "Restarting the running Xplanet display with the updated formula..."
        restart_xplanet || fail "Xplanet was reinstalled, but the display could not be restarted"
    fi
}
