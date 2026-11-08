"""Build choices use synthetic Homebrew data and an isolated zsh/PTY harness."""
import copy
import fcntl
import json
import os
import pty
import select
import shlex
import shutil
import struct
import subprocess
import sys
import termios
import time

from .support import PROJECT, Sandbox


FORMULA_INFO = {"formulae": [{
    "full_name": "blogabe/xplanet/xplanet",
    "options": [
        {"option": "--without-giflib", "description": "Disable GIF"},
        {"option": "--without-jpeg-turbo", "description": "Disable JPEG"},
        {"option": "--without-libpng", "description": "Disable PNG"},
        {"option": "--without-libtiff", "description": "Disable TIFF"},
        {"option": "--with-cspice", "description": "Enable CSPICE"},
        {"option": "--with-netpbm", "description": "Enable Netpbm"},
        {"option": "--with-pango", "description": "Enable Pango"},
        {"option": "--with-all", "description": "Enable optional features"},
    ],
}]}
OPTIONAL = ["--with-cspice", "--with-pango", "--with-netpbm"]
INFO_CALL = ["info", "--json=v2", "--formula", "blogabe/xplanet/xplanet"]


class BuildOptionsTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.scripts = self.root / "scripts"
        helpers = self.scripts / "lib/xplanet"
        helpers.mkdir(parents=True)
        for name in ("build-options.zsh", "management-input.zsh"):
            shutil.copy2(PROJECT / "scripts/lib/xplanet" / name, helpers / name)
        self.metadata = self.base / "formula metadata.json"
        self.metadata.write_text(json.dumps(FORMULA_INFO))
        self.receipt = self.base / "INSTALL_RECEIPT.json"
        self.write_receipt([])
        self.trace = self.base / "brew-calls.jsonl"
        self.mutation = self.base / "brew-mutation"
        self.scratch = self.base / "temporary-files"
        self.scratch.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.brew = self.bin / "brew"
        self.brew.write_text("#!" + sys.executable + "\n" + r'''
import json
import os
from pathlib import Path
import sys
args = sys.argv[1:]
with open(os.environ["TEST_BREW_TRACE"], "a") as trace:
    trace.write(json.dumps(args) + "\n")
if args == ["info", "--json=v2", "--formula", "blogabe/xplanet/xplanet"]:
    if os.environ.get("TEST_BREW_INFO_FAIL") == "1":
        sys.exit(1)
    sys.stdout.write(Path(os.environ["TEST_FORMULA_METADATA"]).read_text())
elif args[:3] == ["reinstall", "--formula", "blogabe/xplanet/xplanet"]:
    Path(os.environ["TEST_BREW_MUTATION"]).write_text(json.dumps(args[3:]))
else:
    sys.exit("Unexpected fake brew command: " + repr(args))
''')
        self.brew.chmod(0o700)
        self.harness = self.base / "build-harness.zsh"
        self.harness.write_text(
            "emulate -LR zsh\nsetopt nounset\n"
            "script_dir=" + shlex.quote(str(self.scripts)) + "\n"
            "brew_bin=" + shlex.quote(str(self.brew)) + "\n"
            'source "$script_dir/lib/xplanet/build-options.zsh" || exit $?\n'
            + r'''
typeset -a build_options=()
build_options_changed=unset
action=$1; shift
case "$action" in
    choose)
        mode=$1; receipt=$2; shift 2
        choose_build_options "$mode" "$receipt" "$@"
        result=$?
        print -r -- "RESULT:$result"
        print -r -- "OPTIONS:${(j: :)build_options}"
        print -r -- "CHANGED:$build_options_changed"
        if (( result == 0 )) && [[ "$TEST_ALLOW_MUTATION" == 1 ]]; then
            "$brew_bin" reinstall --formula blogabe/xplanet/xplanet "${build_options[@]}" || exit $?
        fi
        exit "$result"
        ;;
    verify)
        receipt=$1; shift
        build_options=("$@")
        verify_build_options "$receipt"
        exit $?
        ;;
    arguments)
        build_options_arguments "$@"
        exit $?
        ;;
esac
exit 97
''')
        self.environment = {
            **os.environ,
            "HOME": str(self.base), "ZDOTDIR": str(self.base),
            "PATH": f"{self.bin}:/usr/bin:/bin", "TMPDIR": str(self.scratch),
            "TERM": "dumb", "NO_COLOR": "1",
            "TEST_FORMULA_METADATA": str(self.metadata),
            "TEST_BREW_TRACE": str(self.trace),
            "TEST_BREW_MUTATION": str(self.mutation), "TEST_ALLOW_MUTATION": "0",
        }

    def write_receipt(self, options, *, tap="blogabe/xplanet"):
        self.receipt.write_text(json.dumps({
            "source": {"tap": tap}, "used_options": options,
        }))

    def shell(self, action, *args, env=None):
        return subprocess.run(
            ["/bin/zsh", "-f", str(self.harness), action, *map(str, args)],
            env={**self.environment, **(env or {})}, capture_output=True,
            input="", text=True, timeout=15,
        )

    def choose(self, *options, installed=False, mutate=False, mode=None):
        return self.shell(
            "choose", mode or ("update" if installed else "install"),
            self.receipt if installed else "", *options,
            env={"TEST_ALLOW_MUTATION": "1" if mutate else "0"},
        )

    def calls(self):
        if not self.trace.exists():
            return []
        return [json.loads(line) for line in self.trace.read_text().splitlines()]

    def assert_choices(self, result, options, *, changed=True):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OPTIONS:" + " ".join(options) + "\n", result.stdout)
        self.assertIn("CHANGED:" + str(changed).lower() + "\n", result.stdout)
        self.assertFalse(list(self.scratch.glob("xplanet-build-options.*")))

    def test_explicit_defaults_match_formula_and_need_no_saved_preferences(self):
        result = self.choose("--defaults")
        self.assert_choices(result, [])
        self.assertIn("Enabled:  JPEG, PNG, GIF, TIFF", result.stdout)
        self.assertIn("Disabled: CSPICE, Pango, PNM", result.stdout)
        self.assertEqual(self.calls(), [INFO_CALL])
        self.assertFalse(self.mutation.exists())

    def test_noninteractive_fresh_install_requires_explicit_choice(self):
        result = self.choose(mutate=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Noninteractive install requires", result.stderr)
        self.assertEqual(self.calls(), [INFO_CALL])
        self.assertFalse(self.mutation.exists())
        self.assertFalse(list(self.scratch.iterdir()))

    def test_noninteractive_update_preserves_receipt_choices_without_menu(self):
        self.write_receipt(["--without-giflib", "--with-cspice"])
        result = self.choose(installed=True)
        self.assert_choices(result, ["--without-giflib", "--with-cspice"], changed=False)
        self.assertNotIn("Xplanet build options", result.stdout)

    def test_keep_options_matches_current_receipt(self):
        self.write_receipt(["--with-pango", "--without-libpng"])
        result = self.choose("--keep-options", installed=True)
        self.assert_choices(result, ["--without-libpng", "--with-pango"], changed=False)

    def test_keep_options_without_receipt_fails_without_mutation(self):
        result = self.choose("--keep-options", mutate=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [INFO_CALL])
        self.assertFalse(self.mutation.exists())

    def test_with_all_expands_to_optional_capabilities(self):
        result = self.choose("--with-all")
        self.assert_choices(result, OPTIONAL)
        self.assertNotIn("--with-all", result.stdout)
        self.assertIn("Disabled: none", result.stdout)

    def test_receipt_with_all_expands_without_marking_choices_changed(self):
        self.write_receipt(["--with-all", "--without-libpng"])
        result = self.choose("--keep-options", installed=True)
        self.assert_choices(result, ["--without-libpng", *OPTIONAL], changed=False)

    def test_legacy_jpeg_flag_is_normalized_in_request_and_receipt(self):
        self.assert_choices(self.choose("--without-jpeg"), ["--without-jpeg-turbo"])
        self.write_receipt(["--without-jpeg"])
        result = self.choose("--keep-options", installed=True)
        self.assert_choices(result, ["--without-jpeg-turbo"], changed=False)

    def test_unknown_requested_or_recorded_option_is_not_silently_dropped(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                self.trace.unlink(missing_ok=True)
                self.write_receipt(["--with-retired-feature"])
                args = ("--keep-options",) if installed else ("--with-retired-feature",)
                result = self.choose(*args, installed=installed, mutate=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("no longer supported", result.stderr)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())

    def test_equivalent_explicit_choices_are_a_noop_regardless_of_order(self):
        self.write_receipt(["--with-pango", "--without-giflib", "--with-cspice"])
        result = self.choose("--with-cspice", "--with-pango", "--without-giflib", installed=True, mode="install")
        self.assert_choices(result, ["--without-giflib", "--with-cspice", "--with-pango"], changed=False)

    def test_additive_choices_are_allowed_and_emitted_once(self):
        self.write_receipt(["--with-cspice"])
        result = self.choose("--with-cspice", "--with-pango", "--with-pango", installed=True, mutate=True, mode="install")
        self.assert_choices(result, ["--with-cspice", "--with-pango"])
        self.assertEqual(json.loads(self.mutation.read_text()), ["--with-cspice", "--with-pango"])

    def test_removing_recorded_flag_refuses_before_brew_mutation(self):
        for recorded, requested in (
            (["--with-cspice"], ["--defaults"]),
            (["--without-giflib"], ["--defaults"]),
            (["--with-cspice"], ["--with-pango"]),
            (["--with-all"], ["--with-cspice"]),
        ):
            with self.subTest(recorded=recorded, requested=requested):
                self.trace.unlink(missing_ok=True)
                self.write_receipt(recorded)
                before = self.receipt.read_bytes()
                result = self.choose(*requested, installed=True, mutate=True, mode="install")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("cannot remove previously recorded", result.stderr)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())
                self.assertEqual(self.receipt.read_bytes(), before)
                self.assertFalse(list(self.scratch.iterdir()))

    def test_receipt_from_another_tap_is_rejected(self):
        self.write_receipt([], tap="homebrew/core")
        result = self.choose("--keep-options", installed=True, mutate=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not from blogabe/xplanet", result.stderr)
        self.assertFalse(self.mutation.exists())

    def test_failed_metadata_lookup_leaves_no_temporary_file_or_mutation(self):
        self.environment["TEST_BREW_INFO_FAIL"] = "1"
        result = self.choose("--defaults", mutate=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Could not read Xplanet build options", result.stderr)
        self.assertFalse(list(self.scratch.iterdir()))
        self.assertFalse(self.mutation.exists())

    def test_malformed_metadata_is_rejected_before_mutation(self):
        invalid = ["not JSON", "{}"]
        for field, value in (("full_name", "homebrew/core/xplanet"), ("options", []),
                             ("options", [{"option": "--enable-unsafe", "description": "Bad"}]),
                             ("options", [{"option": "--with-$(touch injected)", "description": "Bad"}]),
                             ("options", [{"option": "--with-cspice"}]),
                             ("options", 0), ("options", "0"), ("options", {}),
                             ("options", [{"option": 0, "description": "Bad"}]),
                             ("options", [{"option": "--with-cspice", "description": 0}]),
                             ("options", [{"option": "--with-unmapped", "description": "Bad"}]),
                             ("options", [FORMULA_INFO["formulae"][0]["options"][0]] * 2),
                             ("options", [FORMULA_INFO["formulae"][0]["options"][0]] * 33)):
            data = copy.deepcopy(FORMULA_INFO)
            data["formulae"][0][field] = value
            invalid.append(json.dumps(data))
        invalid.append(json.dumps({"formulae": FORMULA_INFO["formulae"] * 2}))
        invalid.extend(json.dumps({"formulae": value}) for value in (0, "0", {}, {"0": FORMULA_INFO["formulae"][0]}))
        for metadata in invalid:
            with self.subTest(metadata=metadata[:150]):
                self.trace.unlink(missing_ok=True)
                self.metadata.write_text(metadata)
                result = self.choose("--defaults", mutate=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())
                self.assertFalse(list(self.scratch.iterdir()))

    def test_malformed_receipt_is_rejected_before_mutation(self):
        for data in ({"source": {"tap": "blogabe/xplanet"}},
                     {"source": {"tap": "blogabe/xplanet"}, "used_options": ["--bad"]},
                     {"source": {"tap": "blogabe/xplanet"}, "used_options": ["--with-cspice"] * 33}):
            with self.subTest(receipt=data):
                self.receipt.write_text(json.dumps(data))
                result = self.choose("--keep-options", installed=True, mutate=True)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.mutation.exists())
                self.assertFalse(list(self.scratch.iterdir()))

    def test_receipt_options_must_be_an_array_of_strings(self):
        for options in (0, "0", {}, {"0": "--with-cspice"}, [0], [False], [{}]):
            with self.subTest(options=options):
                self.trace.unlink(missing_ok=True)
                self.write_receipt(options)
                result = self.choose("--keep-options", installed=True, mutate=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.mutation.exists())
                self.assertFalse(list(self.scratch.iterdir()))
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertEqual(self.shell("verify", self.receipt).returncode, 2)

    def test_update_rejects_feature_changes_and_defaults_without_mutation(self):
        self.write_receipt(["--with-cspice"])
        before = self.receipt.read_bytes()
        for options in (("--defaults",), ("--with-cspice",), ("--with-pango",),
                        ("--with-all",), ("--without-giflib",), ("--keep-options", "--defaults")):
            with self.subTest(options=options):
                self.trace.unlink(missing_ok=True)
                result = self.choose(*options, installed=True, mutate=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("Update preserves installed build choices", result.stderr)
                self.assertEqual(self.receipt.read_bytes(), before)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())

    def test_install_requires_png_even_when_disabling_it_is_explicit(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                self.trace.unlink(missing_ok=True)
                self.write_receipt(["--without-libpng"])
                result = self.choose("--without-libpng", installed=installed, mutate=True, mode="install")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("PNG support is required for macOS wallpaper", result.stderr)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())
        data = copy.deepcopy(FORMULA_INFO)
        data["formulae"][0]["options"] = [
            item for item in data["formulae"][0]["options"] if item["option"] != "--without-libpng"]
        self.metadata.write_text(json.dumps(data))
        result = self.choose("--defaults", mutate=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PNG support is required", result.stderr)
        self.assertFalse(self.mutation.exists())

    def test_post_install_verification_accepts_exact_normalized_receipt(self):
        for actual, expected in (([], []),
                                 (["--with-pango", "--with-cspice"], ["--with-cspice", "--with-pango"]),
                                 (["--without-jpeg"], ["--without-jpeg-turbo"]),
                                 (["--without-libpng"], ["--without-libpng"]),
                                 (["--with-all", "--with-pango"], OPTIONAL)):
            with self.subTest(actual=actual):
                self.write_receipt(actual)
                result = self.shell("verify", self.receipt, *expected)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_one_receipt_string_cannot_verify_as_two_build_options(self):
        self.write_receipt(["--with-cspice --with-pango"])
        result = self.shell("verify", self.receipt, "--with-cspice", "--with-pango")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])
        before = self.receipt.read_bytes()
        result = self.choose("--keep-options", installed=True, mutate=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.receipt.read_bytes(), before)
        self.assertFalse(self.mutation.exists())

    def test_receipt_flag_whitespace_is_not_trimmed_into_a_valid_flag(self):
        for flag in ("--with-cspice ", "--with-cspice\t", "--with-cspice\n",
                     "--with-cspice\r", "--with-cspice\n\n", " --with-cspice"):
            with self.subTest(flag=flag):
                self.trace.unlink(missing_ok=True)
                self.write_receipt([flag])
                before = self.receipt.read_bytes()
                result = self.choose("--keep-options", installed=True, mutate=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(self.receipt.read_bytes(), before)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())
                self.assertFalse(list(self.scratch.iterdir()))
                result = self.shell("verify", self.receipt, "--with-cspice")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_metadata_flag_whitespace_is_rejected_before_mutation(self):
        for flag in ("--without-giflib ", "--without-giflib\t", "--without-giflib\n",
                     "--without-giflib\n\n", "--without-giflib --with-cspice"):
            with self.subTest(flag=flag):
                self.trace.unlink(missing_ok=True)
                data = copy.deepcopy(FORMULA_INFO)
                data["formulae"][0]["options"][0]["option"] = flag
                self.metadata.write_text(json.dumps(data))
                result = self.choose("--defaults", mutate=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())
                self.assertFalse(list(self.scratch.iterdir()))

    def test_post_install_verification_rejects_different_or_unreadable_receipt(self):
        for actual, expected in (([], ["--with-cspice"]),
                                 (["--with-pango"], []),
                                 (["--with-cspice", "--with-pango"], ["--with-cspice"]),
                                 (["--with-retired-feature"], [])):
            with self.subTest(actual=actual, expected=expected):
                self.write_receipt(actual)
                result = self.shell("verify", self.receipt, *expected)
                self.assertEqual(result.returncode, 2)
                self.assertIn("different build options", result.stderr)
        self.receipt.write_text("not JSON")
        self.assertEqual(self.shell("verify", self.receipt).returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_argument_modes_are_exclusive_and_flags_are_data(self):
        for args in ([], ["--defaults"], ["--keep-options"], ["--help"],
                     ["--without-jpeg", "--with-cspice"]):
            with self.subTest(valid=args):
                self.assertEqual(self.shell("arguments", *args).returncode, 0)
        for args in (["--defaults", "--with-pango"], ["--keep-options", "--defaults"],
                     ["--help", "--with-all"], ["--build-from-source"],
                     ["--with-pango;touch injected"], ["--defaults=1"]):
            with self.subTest(invalid=args):
                self.assertEqual(self.shell("arguments", *args).returncode, 2)
        self.assertEqual(self.calls(), [])

    def terminal(self, keys, *, installed=False, ansi=False, mode=None, options=()):
        """Send one key/line per rendered prompt, with an owned controlling TTY."""
        mode = mode or ("update" if installed else "install")
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        before = termios.tcgetattr(slave)
        process = subprocess.Popen(
            ["/bin/zsh", "-f", str(self.harness), "choose", mode,
             str(self.receipt) if installed else "", *options], stdin=slave, stdout=slave, stderr=slave,
            env={**self.environment, "TERM": "xterm-256color" if ansi else "dumb",
                 "TEST_ALLOW_MUTATION": "1"}, start_new_session=True,
            preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
        )
        output = b""
        marker = b"Continue with these choices? [Y/n] " if mode == "update" else (
            b"q: cancel: " if ansi else b"q to cancel: ")
        deadline = time.monotonic() + 15
        try:
            for index, key in enumerate(keys, 1):
                while output.count(marker) < index and process.poll() is None and time.monotonic() < deadline:
                    if select.select([master], [], [], .05)[0]:
                        output += os.read(master, 65536)
                self.assertGreaterEqual(output.count(marker), index, output.decode())
                # zsh prints the prompt just before entering its read. For
                # control bytes, wait for that owned read rather than racing it.
                if key in (b"\x03", b"\x04"):
                    if ansi and mode != "update":
                        while termios.tcgetattr(slave)[3] & termios.ICANON and time.monotonic() < deadline:
                            select.select([], [], [], .001)
                        self.assertFalse(termios.tcgetattr(slave)[3] & termios.ICANON, output.decode())
                    else:
                        state = ""
                        while time.monotonic() < deadline:
                            state = subprocess.check_output(
                                ["/bin/ps", "-o", "state=", "-p", str(process.pid)], text=True).strip()
                            if state.startswith("S"):
                                break
                        self.assertTrue(state.startswith("S"), (state, output))
                os.write(master, key)
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    output += os.read(master, 65536)
            self.assertIsNotNone(process.poll(), output.decode())
            process.wait(timeout=2)
            while select.select([master], [], [], .05)[0]:
                chunk = os.read(master, 65536)
                if not chunk:
                    break
                output += chunk
            self.assertEqual(termios.tcgetattr(master), before)
            self.assertFalse(list(self.scratch.iterdir()))
            return process.returncode, output.decode()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_menu_enter_accepts_defaults_without_toggling(self):
        for ansi in (False, True):
            with self.subTest(ansi=ansi):
                code, output = self.terminal([b"\n"], ansi=ansi)
                self.assertEqual(code, 0, output)
                self.assertIn("Formula defaults (no personal preferences)", output)
                self.assertIn("OPTIONS:\r\n", output)
                self.assertEqual(json.loads(self.mutation.read_text()), [])
                if ansi:
                    self.assertIn("\x1b[?1049h", output)
                    self.assertIn("\x1b[?1049l", output)

    def test_menu_update_enter_accepts_installed_choices(self):
        self.write_receipt(["--without-jpeg", "--with-cspice"])
        code, output = self.terminal([b"\n"], installed=True)
        self.assertEqual(code, 0, output)
        self.assertIn("Xplanet update keeps", output)
        self.assertNotIn("Reset", output)
        self.assertNotIn("Space toggles", output)
        self.assertIn("CHANGED:false", output)
        self.assertEqual(json.loads(self.mutation.read_text()), ["--without-jpeg-turbo", "--with-cspice"])

    def test_numbered_menu_toggles_and_reset_restore_defaults(self):
        code, output = self.terminal([b"5\n", b"\n"])
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(self.mutation.read_text()), ["--with-cspice"])
        code, output = self.terminal([b"5\n", b"9\n", b"\n"])
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(self.mutation.read_text()), [])

    def test_arrow_menu_space_toggles_then_continue_accepts(self):
        keys = [b"\x1b[A"] * 3 + [b" "] + [b"\x1b[B"] * 3 + [b"\n"]
        code, output = self.terminal(keys, ansi=True)
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(self.mutation.read_text()), ["--with-cspice"])
        self.assertIn("\x1b[?1049l", output)

    def test_menu_details_do_not_change_choices(self):
        code, output = self.terminal([b"d\n", b"\n"])
        self.assertEqual(code, 0, output)
        self.assertIn("Homebrew options: (formula defaults)", output)
        self.assertEqual(json.loads(self.mutation.read_text()), [])

    def test_menu_cancel_ctrl_c_and_ctrl_d_never_reach_brew_mutation(self):
        self.write_receipt(["--with-cspice"])
        before = self.receipt.read_bytes()
        for ansi in (False, True):
            for key, expected in ((b"q" if ansi else b"q\n", 3), (b"\x03", 130), (b"\x04", 3)):
                with self.subTest(ansi=ansi, key=key):
                    self.trace.unlink(missing_ok=True)
                    code, output = self.terminal([key], installed=True, ansi=ansi, mode="install")
                    self.assertEqual(code, expected, output)
                    self.assertEqual(self.calls(), [INFO_CALL])
                    self.assertFalse(self.mutation.exists())
                    self.assertEqual(self.receipt.read_bytes(), before)
                    if ansi:
                        self.assertIn("\x1b[?1049l", output)

    def test_formula_description_cannot_inject_terminal_or_shell_content(self):
        injected = self.base / "description-executed"
        data = copy.deepcopy(FORMULA_INFO)
        data["formulae"][0]["options"][0]["description"] = (
            "Future\x1b[31m\n$(touch " + shlex.quote(str(injected)) + ")")
        self.metadata.write_text(json.dumps(data))
        code, output = self.terminal([b"q\n"])
        self.assertEqual(code, 3, output)
        self.assertIn("Read and write GIF images", output)
        self.assertNotIn("$(touch", output)
        self.assertNotIn("\x1b", output)
        self.assertFalse(injected.exists())
        self.assertFalse(self.mutation.exists())

    def test_menu_removal_is_rejected_before_mutation(self):
        self.write_receipt(["--with-cspice"])
        before = self.receipt.read_bytes()
        code, output = self.terminal([b"5\n", b"\n"], installed=True, mode="install")
        self.assertEqual(code, 2, output)
        self.assertIn("cannot remove previously recorded", output)
        self.assertEqual(self.calls(), [INFO_CALL])
        self.assertFalse(self.mutation.exists())
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_update_review_accepts_yes_and_keep_options_skips_prompt(self):
        self.write_receipt(["--without-jpeg", "--with-cspice"])
        before = self.receipt.read_bytes()
        for answer in (b"y\n", b"Y\n"):
            with self.subTest(answer=answer):
                code, output = self.terminal([answer], installed=True, ansi=True)
                self.assertEqual(code, 0, output)
                self.assertIn("Continue with these choices? [Y/n]", output)
                self.assertNotIn("Reset", output)
                self.assertNotIn("Space toggles", output)
                self.assertIn("CHANGED:false", output)
                self.assertEqual(self.receipt.read_bytes(), before)
        code, output = self.terminal([], installed=True, options=("--keep-options",))
        self.assertEqual(code, 0, output)
        self.assertNotIn("Continue with these choices?", output)
        self.assertIn("CHANGED:false", output)

    def test_update_review_cancel_interrupt_and_eof_do_not_mutate(self):
        self.write_receipt(["--with-cspice"])
        before = self.receipt.read_bytes()
        for key, expected in ((b"n\n", 3), (b"q\n", 3), (b"5\n", 3),
                              (b"\x03", 130), (b"\x04", 3)):
            with self.subTest(key=key):
                self.trace.unlink(missing_ok=True)
                code, output = self.terminal([key], installed=True)
                self.assertEqual(code, expected, output)
                self.assertEqual(self.calls(), [INFO_CALL])
                self.assertFalse(self.mutation.exists())
                self.assertEqual(self.receipt.read_bytes(), before)
                self.assertNotIn("Reset", output)
                self.assertNotIn("Space toggles", output)

    def test_required_png_row_cannot_be_toggled_off(self):
        for ansi in (False, True):
            keys = ([b"\x1b[A"] * 6 + [b" "] + [b"\x1b[B"] * 6 + [b"\n"]
                    if ansi else [b"2\n", b"\n"])
            with self.subTest(ansi=ansi):
                code, output = self.terminal(keys, ansi=ansi)
                self.assertEqual(code, 0, output)
                self.assertIn("2) [*] PNG", output)
                self.assertIn("Required for macOS wallpaper", output)
                self.assertEqual(json.loads(self.mutation.read_text()), [])
