#!/bin/zsh

# Invoked by xplanet.sh bootstrap; no checkout-local files are available here.
set -u

fail() {
    print -u2 -- "xplanet.sh bootstrap: $1"
    exit 2
}

(( $# == 1 )) || fail "expected a repository branch or tag from xplanet.sh"
ref=$1
[[ "$ref" =~ '^[A-Za-z0-9][A-Za-z0-9._/-]*$' ]] || fail "invalid repository ref"
[[ "${HOME:-}" == /* && -d "$HOME" ]] || fail "HOME must be an existing absolute directory"
destination="$HOME/.xplanet"
[[ ! -e "$destination" && ! -L "$destination" ]] ||
    fail "$destination already exists; use its install command or choose the manual installation path"
brew_bin=$(command -v brew) || fail "Homebrew is required; install it from https://brew.sh first"
[[ "$brew_bin" == /* && -x "$brew_bin" ]] || fail "Homebrew must be an executable on PATH"
git_bin=$(command -v git) || fail "Git is required"
"$git_bin" check-ref-format --branch "$ref" >/dev/null || fail "invalid repository branch or tag"

# Reserve the destination first; even an empty directory or dangling symlink
# belonging to the user must not be accepted by git clone.
mkdir -- "$destination" || fail "could not reserve $destination; nothing was installed"
print -- "Cloning Xplanet ($ref) into $destination..."
"$git_bin" clone --single-branch --branch "$ref" -- \
    https://github.com/blogabe/Xplanet.git "$destination" ||
    fail "clone failed; inspect $destination before removing it and retrying"
[[ -f "$destination/scripts/xplanet.sh" && -x "$destination/scripts/xplanet.sh" ]] ||
    fail "checkout has no executable scripts/xplanet.sh; inspect $destination"
exec "$destination/scripts/xplanet.sh" install
