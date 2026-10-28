"""Repository and formula refresh tests use only local Git and fake brew."""
import json
import os
import shlex
import shutil
import subprocess
import sys

from .support import PROJECT, Sandbox


class LauncherUpdateTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.remote = self.base / "remote.git"
        self.publisher = self.base / "publisher"
        self.launcher = self.root / "scripts/xplanet.sh"
        self.launcher.parent.mkdir()
        shutil.copy2(PROJECT / "scripts/xplanet.sh", self.launcher)
        (self.root / ".gitignore").write_text("cache/\n")
        (self.root / "tracked.txt").write_text("original\n")
        self.environment = {
            **os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
        }
        self.git(self.base, "init", "--bare", str(self.remote))
        self.git(self.root, "init", "-b", "main")
        self.identity(self.root)
        self.git(self.root, "add", ".")
        self.git(self.root, "commit", "-m", "base")
        self.git(self.root, "remote", "add", "origin", str(self.remote))
        self.git(self.root, "push", "-u", "origin", "main")
        self.git(self.base, "clone", "--branch", "main", str(self.remote),
                 str(self.publisher))
        self.identity(self.publisher)
        self.prepare_formula_fixture()
        self.prepare_renderer_fixture()

    def prepare_formula_fixture(self):
        self.tap = self.base / "homebrew-xplanet"
        self.tap.mkdir()
        self.git(self.tap, "init", "-b", "main")
        self.identity(self.tap)
        self.formula = self.tap / "xplanet.rb"
        self.formula.write_text("class Xplanet < Formula\n  revision 99\nend\n")
        self.git(self.tap, "add", "xplanet.rb")
        self.git(self.tap, "commit", "-m", "initial formula")
        self.prefix = self.base / "opt/xplanet"
        self.prefix.mkdir(parents=True)
        self.receipt = self.prefix / "INSTALL_RECEIPT.json"
        self.write_receipt(self.git(self.tap, "rev-parse", "HEAD"))
        self.trace = self.base / "brew-calls.jsonl"
        self.fake_bin = self.base / "fake-bin"
        self.fake_bin.mkdir()
        brew = self.fake_bin / "brew"
        brew.write_text("#!" + sys.executable + "\n" + r"""
import json
import os
from pathlib import Path
import subprocess
import sys
args = sys.argv[1:]
with open(os.environ["TM_BREW_TRACE"], "a") as trace:
    trace.write(json.dumps(args) + "\n")
tap = Path(os.environ["TM_BREW_TAP"])
prefix = Path(os.environ["TM_BREW_PREFIX"])
if args == ["update"]:
    sys.exit(int(os.environ.get("TM_BREW_UPDATE_EXIT", "0")))
if args == ["--repository", "blogabe/xplanet"]:
    if os.environ.get("TM_BREW_TAP_MISSING") == "1":
        sys.exit(1)
    print(tap)
elif args == ["--prefix", "--installed", "blogabe/xplanet/xplanet"]:
    print(prefix)
elif args == ["formula", "blogabe/xplanet/xplanet"]:
    print(tap / "xplanet.rb")
elif args[:4] == ["reinstall", "--formula", "--build-from-source",
                 "blogabe/xplanet/xplanet"]:
    if os.environ.get("TM_BREW_REINSTALL_FAIL") == "1":
        sys.exit(1)
    receipt = prefix / "INSTALL_RECEIPT.json"
    data = json.loads(receipt.read_text())
    data["source"]["tap_git_head"] = subprocess.check_output(
        ["git", "-C", str(tap), "rev-parse", "HEAD"], text=True).strip()
    data["used_options"] = args[4:]
    receipt.write_text(json.dumps(data))
    with open(os.environ["TM_EVENT_TRACE"], "a") as events:
        events.write("reinstall\n")
else:
    sys.exit(4)
""")
        brew.chmod(0o700)
        self.environment.update({
            "PATH": f"{self.fake_bin}:/usr/bin:/bin",
            "TM_BREW_TRACE": str(self.trace),
            "TM_BREW_TAP": str(self.tap),
            "TM_BREW_PREFIX": str(self.prefix),
        })

    def prepare_renderer_fixture(self):
        self.running = self.base / "running.json"
        self.running.write_text("[]")
        self.events = self.base / "renderer-events.txt"
        self.mock_renderer = self.base / "mock-xplanet"
        self.mock_renderer.write_text(
            '#!/bin/sh\nprintf "start\n" >> "$TM_EVENT_TRACE"\n')
        self.mock_renderer.chmod(0o700)
        config = self.root / "config"
        config.mkdir()
        (config / "xp.conf").write_text("# fixture\n")
        (config / "xp.def").write_text(
            "XPLANET_BIN=" + shlex.quote(str(self.mock_renderer)) + "\n"
            "XPLANET_HOME=" + shlex.quote(str(self.root)) + "\n"
            "XPLANET_CONFIG=" + shlex.quote(str(config)) + "\n"
            "XPLANET_PROJECTION=lambert\n"
            "XPLANET_LONGITUDE=-118\n")
        process_stub = "#!" + sys.executable + "\n" + """
import json
import os
from pathlib import Path
import sys
name = Path(sys.argv[0]).name
args = sys.argv[1:]
path = Path(os.environ["TM_RUNNING_PIDS"])
pids = json.loads(path.read_text())
if name == "pgrep":
    if os.environ.get("TM_PGREP_FAIL") == "1":
        sys.exit(2)
    if args != ["-u", str(os.geteuid()), "-x", "xplanet"]:
        sys.exit(4)
    for pid in pids:
        print(pid)
    sys.exit(0 if pids else 1)
if name == "kill":
    pid = args[-1]
    if args[0] == "-0":
        sys.exit(0 if pid in pids else 1)
    if os.environ.get("TM_KILL_FAIL") == "1":
        sys.exit(1)
    with open(os.environ["TM_EVENT_TRACE"], "a") as events:
        events.write("TERM " + pid + "\\n")
    pids.remove(pid)
    path.write_text(json.dumps(pids))
    sys.exit(0)
sys.exit(4)
"""
        for name in ("pgrep", "kill"):
            stub = self.fake_bin / name
            stub.write_text(process_stub)
            stub.chmod(0o700)
        sleep = self.fake_bin / "sleep"
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(0o700)
        self.environment.update({
            "TM_RUNNING_PIDS": str(self.running),
            "TM_EVENT_TRACE": str(self.events),
        })

    def write_receipt(self, commit, *, tap="blogabe/xplanet",
                      options=("--with-cspice", "--without-giflib")):
        self.receipt.write_text(json.dumps({
            "source": {"tap": tap, "tap_git_head": commit,
                       "path": str(self.formula)},
            "used_options": list(options),
        }))

    def change_formula(self):
        self.formula.write_text(
            "class Xplanet < Formula\n  revision 99\n"
            "  patch do\n    sha256 'updated-pin'\n  end\nend\n")
        self.git(self.tap, "add", "xplanet.rb")
        self.git(self.tap, "commit", "-m", "change patch pin without revision bump")

    def brew_calls(self):
        if not self.trace.exists():
            return []
        return [json.loads(line) for line in self.trace.read_text().splitlines()]

    def git(self, directory, *args):
        return subprocess.run(
            ["git", *args], cwd=directory, env=self.environment,
            text=True, capture_output=True, check=True, timeout=5).stdout.strip()

    def identity(self, directory):
        self.git(directory, "config", "user.name", "Fixture")
        self.git(directory, "config", "user.email", "fixture@example.invalid")

    def publish(self, relative, content):
        path = self.publisher / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git(self.publisher, "add", "-f", relative)
        self.git(self.publisher, "commit", "-m", f"add {relative}")
        self.git(self.publisher, "push", "origin", "main")

    def update(self, **overrides):
        return subprocess.run(
            [str(self.launcher), "update"], cwd=self.base,
            env={**self.environment, **overrides},
            text=True, capture_output=True, timeout=10)

    def test_fast_forwards_configured_upstream_only(self):
        self.publish("new.txt", "upstream\n")
        target = self.git(self.publisher, "rev-parse", "HEAD")
        hook = self.root / ".git/hooks/post-merge"
        sentinel = self.base / "unexpected-hook"
        hook.write_text(f'#!/bin/sh\ntouch "{sentinel}"\n')
        hook.chmod(0o755)
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Checking the configured Git upstream", result.stdout)
        self.assertIn("Checking the blogabe/xplanet Homebrew formula", result.stdout)
        self.assertIn("formula unchanged", result.stdout)
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), target)
        self.assertEqual((self.root / "new.txt").read_text(), "upstream\n")
        self.assertFalse(sentinel.exists())

    def test_dirty_tracked_worktree_refuses_before_fetch(self):
        self.publish("new.txt", "upstream\n")
        old_head = self.git(self.root, "rev-parse", "HEAD")
        (self.root / "tracked.txt").write_text("my edits\n")
        result = self.update()
        self.assertEqual(result.returncode, 2)
        self.assertIn("local tracked changes", result.stderr)
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), old_head)
        self.assertEqual((self.root / "tracked.txt").read_text(), "my edits\n")

    def test_untracked_and_ignored_collisions_are_preserved(self):
        for name in ("new.txt", "cache/report.txt"):
            with self.subTest(name=name):
                self.publish(name, "upstream\n")
                local = self.root / name
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_text("mine\n")
                old_head = self.git(self.root, "rev-parse", "HEAD")
                result = self.update()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), old_head)
                self.assertEqual(local.read_text(), "mine\n")
                local.unlink()

    def test_divergence_does_not_merge_or_reset(self):
        self.publish("new.txt", "upstream\n")
        (self.root / "local.txt").write_text("local\n")
        self.git(self.root, "add", "local.txt")
        self.git(self.root, "commit", "-m", "local")
        local_head = self.git(self.root, "rev-parse", "HEAD")
        result = self.update()
        self.assertEqual(result.returncode, 2)
        self.assertIn("fast-forward", result.stderr)
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), local_head)

    def test_missing_upstream_refuses_without_fetch(self):
        self.git(self.root, "branch", "--unset-upstream")
        result = self.update()
        self.assertEqual(result.returncode, 2)
        self.assertIn("configured upstream", result.stderr)

    def test_branch_switch_during_fetch_cannot_advance_other_branch(self):
        original = self.git(self.root, "rev-parse", "HEAD")
        self.git(self.root, "branch", "other")
        self.publish("new.txt", "upstream\n")
        wrapper_dir = self.base / "git-wrapper"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            '#!/bin/sh\n'
            'if [ "$3" = fetch ]; then\n'
            '    "$TM_REAL_GIT" "$@" || exit $?\n'
            '    "$TM_REAL_GIT" -C "$TM_ROOT" switch other >/dev/null || exit $?\n'
            '    exit 0\n'
            'fi\n'
            'exec "$TM_REAL_GIT" "$@"\n')
        wrapper.chmod(0o755)
        result = self.update(
            PATH=f"{wrapper_dir}:{self.environment['PATH']}",
            TM_REAL_GIT=shutil.which("git"), TM_ROOT=str(self.root))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("checkout changed during fetch", result.stderr)
        self.assertEqual(self.git(self.root, "branch", "--show-current"), "other")
        self.assertEqual(self.git(self.root, "rev-parse", "main"), original)
        self.assertEqual(self.git(self.root, "rev-parse", "other"), original)
        self.assertFalse((self.root / "new.txt").exists())

    def test_commit_change_during_fetch_is_reported(self):
        self.publish("new.txt", "upstream\n")
        target = self.git(self.publisher, "rev-parse", "HEAD")
        wrapper_dir = self.base / "git-wrapper"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            '#!/bin/sh\n'
            'if [ "$3" = fetch ]; then\n'
            '    "$TM_REAL_GIT" "$@" || exit $?\n'
            '    "$TM_REAL_GIT" -C "$TM_ROOT" -c core.hooksPath=/dev/null '
            'merge --ff-only FETCH_HEAD >/dev/null || exit $?\n'
            '    exit 0\n'
            'fi\n'
            'exec "$TM_REAL_GIT" "$@"\n')
        wrapper.chmod(0o755)
        result = self.update(
            PATH=f"{wrapper_dir}:{self.environment['PATH']}",
            TM_REAL_GIT=shutil.which("git"), TM_ROOT=str(self.root))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("checkout changed during fetch", result.stderr)
        self.assertEqual(self.git(self.root, "branch", "--show-current"), "main")
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), target)

    def test_upstream_change_during_fetch_is_reported(self):
        self.publish("new.txt", "upstream\n")
        original = self.git(self.root, "rev-parse", "HEAD")
        wrapper_dir = self.base / "git-wrapper"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            '#!/bin/sh\n'
            'if [ "$3" = fetch ]; then\n'
            '    "$TM_REAL_GIT" "$@" || exit $?\n'
            '    "$TM_REAL_GIT" -C "$TM_ROOT" config branch.main.merge '
            'refs/heads/other || exit $?\n'
            '    exit 0\n'
            'fi\n'
            'exec "$TM_REAL_GIT" "$@"\n')
        wrapper.chmod(0o755)
        result = self.update(
            PATH=f"{wrapper_dir}:{self.environment['PATH']}",
            TM_REAL_GIT=shutil.which("git"), TM_ROOT=str(self.root))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("upstream changed during fetch", result.stderr)
        self.assertEqual(self.git(self.root, "rev-parse", "HEAD"), original)
        self.assertFalse((self.root / "new.txt").exists())

    def test_unrelated_tap_commit_does_not_reinstall(self):
        (self.tap / "README.md").write_text("unrelated\n")
        self.git(self.tap, "add", "README.md")
        self.git(self.tap, "commit", "-m", "tap documentation")
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("formula unchanged", result.stdout)
        self.assertEqual(self.brew_calls(), [["update"], ["--repository", "blogabe/xplanet"],
                         ["--prefix", "--installed", "blogabe/xplanet/xplanet"],
                         ["formula", "blogabe/xplanet/xplanet"]])

    def test_same_revision_formula_change_reinstalls_once_with_installed_options(self):
        self.change_formula()
        original_options = json.loads(self.receipt.read_text())["used_options"]
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("formula changed; rebuilding from source", result.stdout)
        self.assertIn("reinstall verified", result.stdout)
        calls = self.brew_calls()
        self.assertEqual(calls[-1], ["--prefix", "--installed", "blogabe/xplanet/xplanet"])
        self.assertIn(["reinstall", "--formula", "--build-from-source",
                       "blogabe/xplanet/xplanet", *original_options], calls)
        self.assertEqual(json.loads(self.receipt.read_text())["source"]["tap_git_head"],
                         self.git(self.tap, "rev-parse", "HEAD"))
        second = self.update()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.events.read_text().splitlines(), ["reinstall"])
        self.assertEqual(sum(call[0] == "reinstall" for call in self.brew_calls()), 1)

    def test_formula_change_restarts_only_a_previously_running_display(self):
        self.change_formula()
        self.running.write_text(json.dumps(["101", "202"]))
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events.read_text().splitlines(),
                         ["reinstall", "TERM 101", "TERM 202", "start"])
        self.assertEqual(json.loads(self.running.read_text()), [])
        self.assertIn("Restarting the running Xplanet display", result.stdout)

    def test_failed_reinstall_leaves_running_display_untouched(self):
        self.change_formula()
        self.running.write_text(json.dumps(["101"]))
        result = self.update(TM_BREW_REINSTALL_FAIL="1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(self.running.read_text()), ["101"])
        self.assertFalse(self.events.exists())

    def test_process_inspection_failure_prevents_reinstall(self):
        self.change_formula()
        result = self.update(TM_PGREP_FAIL="1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("could not inspect", result.stderr)
        self.assertFalse(any(call[0] == "reinstall" for call in self.brew_calls()))
        self.assertFalse(self.events.exists())

    def test_missing_provenance_refuses_unknown_rebuild(self):
        self.change_formula()
        data = json.loads(self.receipt.read_text())
        del data["source"]["tap_git_head"]
        self.receipt.write_text(json.dumps(data))
        result = self.update()
        self.assertEqual(result.returncode, 2)
        self.assertIn("tap commit", result.stderr)
        self.assertFalse(any(call[0] == "reinstall" for call in self.brew_calls()))

    def test_other_tap_or_missing_receipt_does_not_switch_formula(self):
        self.change_formula()
        self.write_receipt(self.git(self.tap, "rev-parse", "HEAD~1"),
                           tap="homebrew/core")
        wrong = self.update()
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("refusing to switch formula", wrong.stderr)
        self.receipt.unlink()
        missing = self.update()
        self.assertEqual(missing.returncode, 2)
        self.assertIn("no Homebrew receipt", missing.stderr)
        self.assertFalse(any(call[0] == "reinstall" for call in self.brew_calls()))

    def test_failed_tap_update_and_reinstall_report_distinctly(self):
        self.change_formula()
        update_failed = self.update(TM_BREW_UPDATE_EXIT="37")
        self.assertEqual(update_failed.returncode, 2)
        self.assertIn("could not update its taps", update_failed.stderr)
        self.assertFalse(any(call[0] == "reinstall" for call in self.brew_calls()))
        reinstall_failed = self.update(TM_BREW_REINSTALL_FAIL="1")
        self.assertEqual(reinstall_failed.returncode, 2)
        self.assertIn("reinstall failed", reinstall_failed.stderr)
        self.assertNotEqual(
            json.loads(self.receipt.read_text())["source"]["tap_git_head"],
            self.git(self.tap, "rev-parse", "HEAD"))

    def test_missing_brew_does_not_prevent_git_fast_forward(self):
        self.publish("new.txt", "upstream\n")
        old_head = self.git(self.root, "rev-parse", "HEAD")
        brew = self.fake_bin / "brew"
        brew.rename(self.fake_bin / "brew-hidden")
        result = self.update()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Homebrew is unavailable", result.stderr)
        self.assertNotEqual(self.git(self.root, "rev-parse", "HEAD"), old_head)
        self.assertEqual((self.root / "new.txt").read_text(), "upstream\n")

    def test_missing_tap_or_local_formula_edit_refuses_reinstall(self):
        self.change_formula()
        missing_tap = self.update(TM_BREW_TAP_MISSING="1")
        self.assertEqual(missing_tap.returncode, 2)
        self.assertIn("tap is unavailable", missing_tap.stderr)
        self.formula.write_text(self.formula.read_text() + "# local edit\\n")
        dirty = self.update()
        self.assertEqual(dirty.returncode, 2)
        self.assertIn("local changes", dirty.stderr)
        self.assertFalse(any(call[0] == "reinstall" for call in self.brew_calls()))

    def test_unrecognized_installed_option_is_not_silently_dropped(self):
        self.change_formula()
        self.write_receipt(self.git(self.tap, "rev-parse", "HEAD~1"),
                           options=("--with-cspice", "--custom-option"))
        result = self.update()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not supported for automatic reinstall", result.stderr)
        self.assertFalse(any(call[0] == "reinstall" for call in self.brew_calls()))
