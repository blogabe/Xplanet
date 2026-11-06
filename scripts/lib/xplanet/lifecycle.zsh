# Serialize this user's one desktop service across checkouts. No Python/PID DB.
# Keep the stable file: unlinking a held lock could create two independent locks.
desktop_lifecycle() (
    local runtime lock before after lifecycle_fd
    zmodload zsh/system && zsystem supports flock || fail "native zsh file locking is required for desktop lifecycle"
    runtime=$(getconf DARWIN_USER_TEMP_DIR) || fail "cannot locate this user's local runtime directory"
    [[ -n "$runtime" && "$runtime" == /* && "$runtime" != *[[:cntrl:]]* ]] || fail "invalid desktop runtime directory"
    runtime=${runtime:A}
    [[ -d "$runtime" && ! -L "$runtime" && -O "$runtime" && "$(/usr/bin/stat -f %Lp "$runtime")" == 700 ]] || fail "desktop runtime directory must be private and user-owned"
    lock="$runtime/local.xplanet.desktop.lock"
    if [[ ! -e "$lock" && ! -L "$lock" ]]; then
        (umask 077; setopt noclobber; : > "$lock") 2>/dev/null ||
            [[ -f "$lock" && ! -L "$lock" ]] || fail "cannot create desktop lifecycle lock"
    fi
    [[ -f "$lock" && ! -L "$lock" && -O "$lock" && "$(/usr/bin/stat -f %Lp "$lock")" == 600 ]] || fail "desktop lifecycle lock must be a private user-owned regular file"
    before=$(/usr/bin/stat -f '%d:%i:%u:%Lp' "$lock") || fail "cannot inspect desktop lifecycle lock"
    zsystem flock -t 10 -i 0.05 -f lifecycle_fd "$lock" || fail "another desktop lifecycle command is busy; retry after it completes"
    after=$(/usr/bin/stat -f '%d:%i:%u:%Lp' "$lock") || fail "cannot recheck desktop lifecycle lock"
    [[ "$before" == "$after" && ! -L "$lock" ]] || fail "desktop lifecycle lock changed; retry without removing lock files"
    # The subshell owns the kernel lock. Normal/fatal exit releases it, and exec
    # children do not retain it. Restart holds it across both stop and start.
    "$@"
)
