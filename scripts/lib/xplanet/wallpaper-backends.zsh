# Shared renderer capability probe. No advertisement means legacy macOS
# renderer behavior; an advertisement with no matching token is not legacy.
probe_wallpaper_backends() {
    local capabilities line token
    local -a match mbegin mend
    wallpaper_backends=()
    wallpaper_backends_advertised=false
    capabilities=$(LC_ALL=C "$1" -version 2>/dev/null) || return 1
    for line in "${(f)capabilities}"; do
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
