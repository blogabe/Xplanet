# Separate configurator module: save proposed files or cancel, never apply jobs.
configure_xplanet() {
    local configurator_status
    "$script_dir/run-configurator" "$@"
    configurator_status=$?
    case "$configurator_status" in
        0) case "${1:-}" in
               --prepare) configuration_result=prepared ;;
               --help|-h|--guide|--export-handoff|--check-handoff|--apply-handoff|--select-revision|--use-legacy|--show-selection) configuration_result=info ;;
               *) configuration_result=saved ;;
           esac ;;
        5) configuration_result=uncertain ;;
        129|130|143) configuration_result=interrupted ;;
        3) configuration_result=cancelled ;;
        4) configuration_result=unavailable ;;
        *) configuration_result=failed ;;
    esac
    return "$configurator_status"
}
