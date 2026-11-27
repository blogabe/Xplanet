# The renderer and helper are one package, not independent PATH lookups.
# REPLY is the helper path on success or a diagnosis on failure.
resolve_desktop_layer_helper() {
    local renderer="${1:A}" helper capabilities line supported=false
    [[ "$renderer" == /* && "$renderer" != *[[:cntrl:]]* && -f "$renderer" && -x "$renderer" ]] || {
        REPLY="The fileless desktop requires a valid Xplanet executable"
        return 1
    }
    if capabilities=$(LC_ALL=C "$renderer" -version 2>/dev/null); then
        for line in "${(f)capabilities}"; do
            [[ "$line" != 'Frame pipe: 1' ]] || supported=true
        done
    fi
    [[ "$supported" == true ]] || {
        REPLY="The fileless desktop requires a renderer that advertises 'Frame pipe: 1'; install or update the compatible Xplanet package"
        return 1
    }
    helper="${renderer:h}/xplanet-desktop"
    [[ -f "$helper" && -x "$helper" && ! -L "$helper" && "$helper" != "$renderer" ]] || {
        REPLY="The fileless desktop requires the packaged xplanet-desktop executable beside the renderer"
        return 1
    }
    REPLY="$helper"
}
