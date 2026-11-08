"""Small Homebrew metadata fixtures; never read the host tap or receipts."""
import json

FORMULA_INFO = {"formulae": [{"full_name": "blogabe/xplanet/xplanet", "options": [
    {"option": flag, "description": "Fixture " + flag}
    for flag in ("--with-all", "--with-cspice", "--with-netpbm", "--with-pango",
                 "--without-giflib", "--without-jpeg-turbo", "--without-libpng",
                 "--without-libtiff")
]}]}
FORMULA_JSON = json.dumps(FORMULA_INFO)
# TM_PREFIX/INSTALL_RECEIPT.json exists only after this stub's install.
INSTALL_BREW_FIXTURE = (
    'if [ "$1" = formula ]; then printf "class Xplanet < Formula\\nend\\n" > "$TM_PREFIX/fixture.rb"; '
    'printf "%s\\n" "$TM_PREFIX/fixture.rb"; exit 0; fi\n'
    'if [ "$1" = info ]; then [ "${TM_CHANGE_RECIPE:-}" != 1 ] || echo changed >> "$TM_PREFIX/fixture.rb"; printf \'%s\\n\' \'' + FORMULA_JSON + '\'; exit 0; fi\n'
    'if [ "$1 $2" = "--prefix --installed" ]; then\n'
    '  [ -f "$TM_PREFIX/INSTALL_RECEIPT.json" ] || exit 1\n'
    '  printf "%s\\n" "$TM_PREFIX"; exit 0; fi\n'
    'if [ "$1 $2" = "install --formula" ]; then\n'
    '  mkdir -p "$TM_PREFIX/.brew"; cp "$TM_PREFIX/fixture.rb" "$TM_PREFIX/.brew/xplanet.rb"\n'
    '  [ "${TM_CHANGE_INSTALLED_RECIPE:-}" != 1 ] || echo changed >> "$TM_PREFIX/.brew/xplanet.rb"\n'
    '  (shift 4; printf \'%s\' \'{"source":{"tap":"blogabe/xplanet"},"used_options":[\'; sep=;\n'
    '    for flag in "$@"; do printf \'%s"%s"\' "$sep" "$flag"; sep=,; done;\n'
    '    printf \'%s\\n\' \']}\') > "$TM_PREFIX/INSTALL_RECEIPT.json"\nfi\n'
)
