"""Repository refresh tests use only temporary local Git repositories."""
import os
import shutil
import subprocess

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
