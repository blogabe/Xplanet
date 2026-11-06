# Literal named-scene runtime. Never source a generated definition or use Python.
scene_revision_id() {
    local selector="$project_root/config/desktop.scene" value
    [[ -e "$selector" || -L "$selector" ]] || return 1
    [[ -f "$selector" && ! -L "$selector" && "${selector:A}" == "$selector" ]] || fail "invalid desktop scene selector; no custom configuration fallback"
    [[ "$(/usr/bin/stat -f %z "$selector")" == 68 ]] || fail "invalid desktop scene selector size; no custom configuration fallback"
    value=$(<"$selector")
    [[ "$value" =~ '^v1 ([0-9a-f]{64})$' ]] || fail "invalid desktop scene selector; no custom configuration fallback"
    REPLY="$match[1]"
}

scene_hash() {
    local scene_path="$1" expected="$2" limit="$3" before after actual size
    [[ -f "$scene_path" && ! -L "$scene_path" && "${scene_path:A}" == "$scene_path" ]] || fail "selected scene file absent or linked: $scene_path"
    size=$(/usr/bin/stat -f %z "$scene_path") || fail "cannot inspect scene file"
    [[ "$size" == <-> && "$size" -le "$limit" ]] || fail "selected scene file exceeds its bound"
    before=$(/usr/bin/stat -f '%d:%i:%p:%z:%m:%c' "$scene_path") || fail "cannot inspect scene file"
    actual=$(/usr/bin/shasum -a 256 -- "$scene_path") || fail "cannot hash selected scene file"
    after=$(/usr/bin/stat -f '%d:%i:%p:%z:%m:%c' "$scene_path") || fail "cannot recheck scene file"
    [[ "$before" == "$after" && "${actual%% *}" == "$expected" ]] || fail "selected scene file changed: $scene_path; re-review before starting"
}

selected_scene_command() {
    local identity revision manifest expected args_hash checks_hash args checks kind sha size name scene_path line total=0 count=0
    local -a values
    scene_revision_id || return 1
    identity="$REPLY";revision="$project_root/.state/xplanet/scenes/$identity";manifest="$revision/deployment.plist"
    [[ -d "$revision" && "${revision:A}" == "$revision" ]] || fail "selected scene revision missing or linked; no custom configuration fallback"
    scene_hash "$manifest" "$identity" 262144
    /usr/bin/plutil -lint "$manifest" >/dev/null || fail "invalid scene deployment manifest"
    [[ "$(/usr/bin/plutil -extract schema raw -expect integer -o - "$manifest")" == 1 ]] || fail "unsupported scene deployment schema"
    [[ "$(/usr/bin/plutil -extract review.root raw -expect string -o - "$manifest")" == "$project_root" ]] || fail "scene belongs to a different checkout; re-review here"
    expected=$(/usr/bin/plutil -extract args_sha256 raw -expect string -o - "$manifest") || fail "missing scene argument hash"
    [[ "$expected" =~ '^[0-9a-f]{64}$' ]] || fail "invalid scene argument hash"
    args_hash="$expected";args="$revision/desktop.args";scene_hash "$args" "$args_hash" 16384
    expected=$(/usr/bin/plutil -extract checks_sha256 raw -expect string -o - "$manifest") || fail "missing scene resource hash"
    [[ "$expected" =~ '^[0-9a-f]{64}$' ]] || fail "invalid scene resource hash"
    checks_hash="$expected";checks="$revision/checks.tsv";scene_hash "$checks" "$checks_hash" 32768
    while IFS=$'\t' read -r kind sha size name; do
        (( ++count <= 128 )) || fail "too many scene resources"
        [[ "$sha" =~ '^[0-9a-f]{64}$' && "$size" == <-> && ${#size} -le 10 ]] || fail "invalid scene resource check"
        [[ "$name" != *[[:cntrl:]]* ]] || fail "invalid scene resource path"
        case "$kind" in
            N) [[ "$name" != */* && "$name" != . && "$name" != .. && -n "$name" ]] || fail "invalid native scene filename"
               scene_path="$revision/$name"; (( size <= 134217728 )) || fail "oversize native scene resource" ;;
            P) [[ "$name" != assets/maps/* ]] || fail "selected scene uses the previous map layout; reopen, save a new copy and review/select it before starting"
               [[ "$name" == maps/* && "$name" != *'/../'* && "$name" != *'/./'* ]] || fail "invalid project scene resource"
               scene_path="$project_root/$name"; (( size <= 536870912 )) || fail "oversize project scene resource" ;;
            B) [[ "$name" == /* ]] || fail "invalid selected renderer path"
               scene_path="$name"; (( size <= 536870912 )) || fail "oversize selected renderer" ;;
            *) fail "unknown selected scene resource kind" ;;
        esac
        (( total += size )); (( total <= 1744830464 )) || fail "selected scene resources exceed their bound"
        scene_hash "$scene_path" "$sha" "$size"
    done < "$checks"
    (( count > 0 )) || fail "empty selected scene resource checks"
    while IFS= read -r line; do
        [[ -n "$line" && "$line" != *[[:cntrl:]]* ]] || fail "invalid literal scene argument"
        (( ${#values} < 64 )) || fail "too many scene arguments"
        if [[ "$line" == '@revision@' ]]; then line="$revision"
        elif [[ "$line" == '@revision@/'* ]]; then line="$revision/${line#@revision@/}"
        fi
        values+=("$line")
    done < "$args"
    (( ${#values} >= 3 )) || fail "incomplete scene command"
    XPLANET_BIN="$values[1]"
    [[ "$XPLANET_BIN" == /* && -x "$XPLANET_BIN" ]] || fail "selected renderer is unavailable"
    desktop_args=("${values[@]:1}")
    scene_hash "$args" "$args_hash" 16384
    scene_hash "$checks" "$checks_hash" 32768
    scene_hash "$manifest" "$identity" 262144
    scene_revision_id || fail "scene selection removed during start"
    [[ "$REPLY" == "$identity" ]] || fail "scene selection changed during start; retry explicitly"
    XPLANET_SCENE_DIRECTORY="$revision"
    XPLANET_SCENE_TMPDIR="$project_root/.state/xplanet/desktop-tmp"
    if [[ -e "$XPLANET_SCENE_TMPDIR" || -L "$XPLANET_SCENE_TMPDIR" ]]; then
        [[ -d "$XPLANET_SCENE_TMPDIR" && ! -L "$XPLANET_SCENE_TMPDIR" && "${XPLANET_SCENE_TMPDIR:A}" == "$XPLANET_SCENE_TMPDIR" ]] || fail "selected scene scratch directory must be real"
    fi
    EARTH_MAP_PRE=''
}

# Stop must also recognize custom renderer names from previously selected revisions.
# Read only bounded literal argument files; do not validate multi-megabyte assets here.
scene_renderer_names() {
    local args binary
    for args in "$project_root"/.state/xplanet/scenes/*/desktop.args(N); do
        [[ "${args:h:t}" =~ '^[0-9a-f]{64}$' ]] || continue
        [[ -f "$args" && ! -L "$args" && "${args:A}" == "$args" ]] || continue
        [[ "$(/usr/bin/stat -f %z "$args")" -le 16384 ]] || continue
        IFS= read -r binary < "$args"
        [[ "$binary" == /* && "$binary" != *[[:cntrl:]]* ]] && print -r -- "${binary:t}"
    done
}
