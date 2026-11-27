# Shared renderer capability probe. No advertisement means legacy macOS
# renderer behavior; an advertisement with no matching token is not legacy.
probe_wallpaper_backends() {
    local capabilities line token
    local -a match mbegin mend
    wallpaper_backends=()
    wallpaper_backends_advertised=false
    desktop_frame_pipe_available=false
    capabilities=$(LC_ALL=C "$1" -version 2>/dev/null) || return 1
    for line in "${(f)capabilities}"; do
        [[ "$line" == 'Frame pipe: 1' ]] && desktop_frame_pipe_available=true
        [[ "$line" =~ '^[[:blank:]]*Wallpaper backends:[[:space:]]*(.*)$' ]] || continue
        wallpaper_backends_advertised=true
        for token in "${(@s:,:)match[1]}"; do
            if [[ "$token" =~ '^[[:space:]]*([^[:space:]]+)[[:space:]]*$' ]]; then
                wallpaper_backends+=("$match[1]")
            fi
        done
    done
    return 0
}

has_wallpaper_backend() {
    (( wallpaper_backends[(Ie)$1] != 0 ))
}

# The renderer and helper are one package, not independent PATH lookups.
# REPLY is the helper path on success or a diagnosis on failure.
resolve_desktop_layer_helper() {
    local renderer="${1:A}" helper
    local wallpaper_backends_advertised desktop_frame_pipe_available
    local -a wallpaper_backends
    [[ "$renderer" == /* && "$renderer" != *[[:cntrl:]]* && -f "$renderer" && -x "$renderer" ]] || {
        REPLY="desktop-layer requires a valid Xplanet executable"
        return 1
    }
    probe_wallpaper_backends "$renderer" && [[ "$desktop_frame_pipe_available" == true ]] || {
        REPLY="desktop-layer requires a renderer that advertises 'Frame pipe: 1'"
        return 1
    }
    helper="${renderer:h}/xplanet-desktop"
    [[ -f "$helper" && -x "$helper" && ! -L "$helper" && "$helper" != "$renderer" ]] || {
        REPLY="desktop-layer requires the packaged xplanet-desktop executable beside the renderer"
        return 1
    }
    REPLY="$helper"
}
