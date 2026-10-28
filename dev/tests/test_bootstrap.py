"""Bootstrap only into temporary homes, with all downloads and clones mocked."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[2]


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xplanet bootstrap ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.downloads = self.base / "downloads"
        self.downloads.mkdir()
        self.entry = self.base / "xplanet.sh"
        shutil.copy2(PROJECT / "scripts/xplanet.sh", self.entry)
        self.helper = self.base / "xp-bootstrap.sh"
        shutil.copy2(PROJECT / "scripts/xp-bootstrap.sh", self.helper)
        self.trace = self.base / "trace"
        self.installer = self.base / "installer"
        self.installer.write_text(
            '#!/bin/zsh\nprint -r -- "$1" > "$HOME/install-command"\n'
            'read -r answer\nprint -r -- "$answer" > "$HOME/install-answer"\n'
            'exit "${INSTALL_EXIT:-0}"\n')
        self.installer.chmod(0o755)
        self.env = {
            **os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin",
            "TMPDIR": str(self.downloads), "BOOT_TRACE": str(self.trace),
            "BOOT_ENTRY": str(self.entry), "BOOT_HELPER": str(self.helper),
            "BOOT_INSTALLER": str(self.installer),
        }
        self.env.pop("XPLANET_BOOTSTRAP_REF", None)
        self.stub("brew", 'raise SystemExit("brew must not be called by bootstrap")\n')
        self.stub("curl", '''
args = sys.argv[1:]
with open(os.environ["BOOT_TRACE"], "a") as f: f.write(json.dumps(["curl", *args]) + "\\n")
source = "BOOT_HELPER" if args[-1].endswith("/xp-bootstrap.sh") else "BOOT_ENTRY"
if "--output" in args:
    shutil.copyfile(os.environ[source], Path(args[args.index("--output") + 1]))
else:
    sys.stdout.write(Path(os.environ[source]).read_text())
raise SystemExit(int(os.environ.get("CURL_EXIT", "0")))
''')
        real_git = shutil.which("git")
        self.stub("git", f'''
args = sys.argv[1:]
with open(os.environ["BOOT_TRACE"], "a") as f: f.write(json.dumps(["git", *args]) + "\\n")
if args[0] == "check-ref-format":
    raise SystemExit(subprocess.call([{real_git!r}, *args]))
if args[0] != "clone": raise SystemExit(99)
if os.environ.get("CLONE_EXIT"): raise SystemExit(int(os.environ["CLONE_EXIT"]))
scripts = Path(args[-1]) / "scripts"
scripts.mkdir()
if not os.environ.get("NO_INSTALLER"):
    shutil.copy2(os.environ["BOOT_INSTALLER"], scripts / "xplanet.sh")
''')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\nimport os, sys, json, shutil, subprocess\nfrom pathlib import Path\n" + body)
        path.chmod(0o755)

    def run_bootstrap(self, *args, **env):
        return subprocess.run(
            ["/bin/zsh", str(self.entry), *(args or ("bootstrap",))],
            cwd=self.base, env={**self.env, **env}, input="interactive answer\n",
            text=True, capture_output=True, timeout=10)

    def calls(self):
        return [json.loads(s) for s in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def test_downloaded_entry_delegates_default_ref_and_preserves_stdin(self):
        result = self.run_bootstrap(INSTALL_EXIT="37")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual((self.home / "install-command").read_text(), "install\n")
        self.assertEqual((self.home / "install-answer").read_text(), "interactive answer\n")
        self.assertIn("/main/scripts/xp-bootstrap.sh", self.calls()[0][-1])
        self.assertEqual(self.calls()[-1], ["git", "clone", "--single-branch", "--branch", "main", "--",
                                          "https://github.com/blogabe/Xplanet.git", str(self.home / ".xplanet")])
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_real_local_clone_checks_out_requested_branch_and_configures_upstream(self):
        real_git = shutil.which("git")
        origin = self.base / "origin"
        subprocess.run([real_git, "init", "-b", "feature/bootstrap-install", str(origin)],
                       check=True, capture_output=True)
        (origin / "scripts").mkdir()
        shutil.copy2(self.installer, origin / "scripts/xplanet.sh")
        subprocess.run([real_git, "-C", str(origin), "add", "scripts/xplanet.sh"], check=True)
        subprocess.run([real_git, "-C", str(origin), "-c", "user.name=Bootstrap Test",
                        "-c", "user.email=bootstrap@example.invalid", "-c", "core.hooksPath=/dev/null",
                        "-c", "commit.gpgsign=false", "commit", "-m", "Fixture installer"],
                       check=True, capture_output=True)
        # Substitute only the network URL; exercise Git's real clone mechanics.
        self.stub("git", f'''args = sys.argv[1:]
if args[0] == "clone": args[-2] = {str(origin)!r}
raise SystemExit(subprocess.call([{real_git!r}, *args]))
''')
        result = self.run_bootstrap(XPLANET_BOOTSTRAP_REF="feature/bootstrap-install")
        self.assertEqual(result.returncode, 0, result.stderr)
        checkout = self.home / ".xplanet"
        upstream = subprocess.check_output(
            [real_git, "-C", str(checkout), "rev-parse", "--abbrev-ref", "@{upstream}"], text=True)
        self.assertEqual(upstream.strip(), "origin/feature/bootstrap-install")
        self.assertEqual((self.home / "install-answer").read_text(), "interactive answer\n")

    def documented_commands(self):
        return re.findall(r"```sh\n(.*?)\n```", (PROJECT / "README.md").read_text(), re.S)

    def test_documented_one_line_command_uses_default_ref_and_preserves_stdin(self):
        command = self.documented_commands()[0]
        self.assertNotIn("\n", command)
        self.assertNotIn("XPLANET_BOOTSTRAP_REF", command)
        result = subprocess.run(["/bin/zsh", "-c", command], cwd=self.base,
                                env={**self.env, "INSTALL_EXIT": "37"}, input="from docs\n", text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 37, result.stderr)
        calls = self.calls()
        self.assertIn("/main/scripts/xplanet.sh", calls[0][-1])
        self.assertIn("/main/scripts/xp-bootstrap.sh", calls[1][-1])
        self.assertIn("main", calls[-1])
        self.assertEqual((self.home / "install-answer").read_text(), "from docs\n")
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_documented_developer_command_uses_feature_ref(self):
        command = re.search(r"```sh\n(.*?)\n```",
                            (PROJECT / "docs/technical-notes.md").read_text(), re.S).group(1)
        command = command.replace("./scripts/xplanet.sh", '"' + str(self.entry) + '"')
        result = subprocess.run(["/bin/zsh", "-c", command], cwd=self.base,
                                env=self.env, input="branch answer\n", text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/feature/bootstrap-install/scripts/xp-bootstrap.sh", self.calls()[0][-1])
        self.assertIn("feature/bootstrap-install", self.calls()[-1])
        self.assertEqual((self.home / "install-answer").read_text(), "branch answer\n")

    def test_failed_entry_download_in_documented_command_never_executes(self):
        # curl writes a complete entry point before failing, as a stronger case
        # than partial content: even this must never reach the helper download.
        result = subprocess.run(["/bin/zsh", "-c", self.documented_commands()[0]], cwd=self.base,
                                env={**self.env, "CURL_EXIT": "22"},
                                input="", text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 22)
        self.assertEqual(len(self.calls()), 1)
        self.assertFalse((self.home / ".xplanet").exists())
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_destination_appearing_before_reservation_is_preserved(self):
        self.stub("mkdir", 'Path(sys.argv[-1]).mkdir()\nraise SystemExit(1)\n')
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 2)
        self.assertIn("could not reserve", result.stderr)
        self.assertTrue((self.home / ".xplanet").is_dir())
        self.assertFalse(any(call[1] == "clone" for call in self.calls()))

    def test_partial_failed_download_never_executes_helper(self):
        result = self.run_bootstrap(CURL_EXIT="22")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertFalse((self.home / ".xplanet").exists())
        self.assertEqual(list(self.downloads.iterdir()), [])

    def test_all_existing_destination_types_are_preserved(self):
        destination = self.home / ".xplanet"
        for kind in ("directory", "file", "symlink", "dangling symlink"):
            with self.subTest(kind=kind):
                if kind == "directory": destination.mkdir()
                elif kind == "file": destination.write_text("keep")
                else: destination.symlink_to(self.base if kind == "symlink" else self.base / "absent")
                self.trace.unlink(missing_ok=True)
                result = self.run_bootstrap()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("already exists", result.stderr)
                self.assertEqual(len(self.calls()), 1)
                if kind == "directory": destination.rmdir()
                else:
                    if kind == "file": self.assertEqual(destination.read_text(), "keep")
                    else: self.assertTrue(destination.is_symlink())
                    destination.unlink()

    def test_missing_homebrew_stops_before_clone(self):
        (self.bin / "brew").unlink()
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Homebrew is required", result.stderr)
        self.assertFalse((self.home / ".xplanet").exists())
        self.assertEqual(len(self.calls()), 1)

    def test_clone_failure_leaves_destination_without_installing(self):
        result = self.run_bootstrap(CLONE_EXIT="17")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clone failed", result.stderr)
        self.assertTrue((self.home / ".xplanet").is_dir())
        self.assertFalse((self.home / "install-command").exists())

    def test_missing_checkout_entry_stops_before_install(self):
        result = self.run_bootstrap(NO_INSTALLER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no executable", result.stderr)
        self.assertFalse((self.home / "install-command").exists())

    def test_invalid_ref_and_extra_arguments_do_not_download(self):
        for args, env in [(("bootstrap", "extra"), {}),
                          (("bootstrap",), {"XPLANET_BOOTSTRAP_REF": "main?query"}),
                          (("bootstrap",), {"XPLANET_BOOTSTRAP_REF": "-main"})]:
            with self.subTest(args=args, env=env):
                result = self.run_bootstrap(*args, **env)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.calls(), [])

    def test_invalid_git_ref_stops_before_destination_creation(self):
        result = self.run_bootstrap(XPLANET_BOOTSTRAP_REF="feature/../main")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid repository", result.stderr)
        self.assertFalse((self.home / ".xplanet").exists())

    def test_missing_local_setup_does_not_trigger_bootstrap(self):
        result = self.run_bootstrap("setup", "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.home / ".xplanet").exists())
