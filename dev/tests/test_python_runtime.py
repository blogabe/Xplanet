"""The existing command wrappers require a supported interpreter in sparse PATHs."""
import subprocess
import sys

from .support import PROJECT, Sandbox


class PythonRuntimeTests(Sandbox):
    def run_selector(self, environment):
        return subprocess.run([str(PROJECT / "scripts/run-totalmarker"), "--python-path"],
                              cwd=self.base, env=environment, capture_output=True,
                              text=True, check=False)

    def run_selector_with_controlled_probe(self, accepted, home):
        # Exercise the source selector while controlling probes for fixed paths
        # that cannot be created under the isolated test root.
        source = (PROJECT / "scripts/run-totalmarker").read_text()
        begin = source.index("select_python() {\n")
        end = source.index("\n}\n\npython_bin=", begin) + 2
        shell = (source[begin:end] + '\n'
                 'supported_python() { [ "$1" = "$TM_ACCEPT_PATH" ]; }\n'
                 'select_python\n')
        return subprocess.run(["/bin/sh", "-c", shell], cwd=self.base,
                              env={"PATH": "", "HOME": str(home),
                                   "TM_ACCEPT_PATH": str(accepted)},
                              capture_output=True, text=True, check=False)

    def test_standard_homebrew_prefixes_are_considered(self):
        home = self.root / "home"
        for candidate in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3"):
            with self.subTest(candidate=candidate):
                result = self.run_selector_with_controlled_probe(candidate, home)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), candidate)

    def test_per_user_homebrew_fallback_follows_standard_prefixes(self):
        home = self.root / "home with spaces"
        fallback = home / ".homebrew/bin/python3"
        result = self.run_selector_with_controlled_probe(fallback, home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(fallback))

    def test_shadowed_python_uses_custom_homebrew_prefix_in_fresh_shell(self):
        binary_dir = self.root / "bin"
        binary_dir.mkdir()
        old = binary_dir / "python3"
        old.write_text("#!/bin/sh\nexit 1\n")
        old.chmod(0o700)
        (binary_dir / "dirname").symlink_to("/usr/bin/dirname")
        prefix = self.base / "custom Homebrew prefix"
        (prefix / "bin").mkdir(parents=True)
        selected_python = prefix / "bin/python3"
        selected_python.symlink_to(sys.executable)
        brew = binary_dir / "brew"
        brew.write_text('#!/bin/sh\n'
                        '[ "$1" = --prefix ] || exit 9\n'
                        'printf "%s\\n" "$TM_BREW_PREFIX"\n')
        brew.chmod(0o700)
        environment = {"PATH": str(binary_dir),
                       "HOME": str(self.root / "home"),
                       "TM_BREW_PREFIX": str(prefix)}
        for _ in range(2):  # separate calls model install handoff and a fresh shell
            result = self.run_selector(environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(selected_python))
        help_result = subprocess.run([str(PROJECT / "scripts/run-totalmarker"), "--help"],
                                     cwd=self.base, env=environment, capture_output=True,
                                     text=True, check=False)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("{clouds,labels,quake,storm,volcano,norad,eclipse,santa}",
                      help_result.stdout)
        minimal_job = self.run_selector({"PATH": "/usr/bin:/bin",
                                         "TOTALMARKER_PYTHON": str(selected_python)})
        self.assertEqual(minimal_job.returncode, 0, minimal_job.stderr)
        self.assertEqual(minimal_job.stdout.strip(), str(selected_python))
        for invalid in ("", "python3", str(old)):
            with self.subTest(invalid=invalid):
                overridden = self.run_selector({**environment,
                                                "TOTALMARKER_PYTHON": invalid})
                self.assertEqual(overridden.returncode, 2)
                self.assertEqual(overridden.stdout, "")

    def test_later_path_python_is_checked_after_old_system_candidate(self):
        old_dir = self.root / "system-first"
        new_dir = self.root / "homebrew-later"
        old_dir.mkdir()
        new_dir.mkdir()
        old = old_dir / "python3"
        old.write_text("#!/bin/sh\nexit 1\n")
        old.chmod(0o700)
        (old_dir / "dirname").symlink_to("/usr/bin/dirname")
        current = new_dir / "python3"
        current.symlink_to(sys.executable)
        result = self.run_selector({"PATH": f"{old_dir}:{new_dir}",
                                    "HOME": str(self.root / "home")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(current))

    def test_explicit_absolute_override_is_checked_and_never_falls_through(self):
        good = self.run_selector({"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                                  "TOTALMARKER_PYTHON": sys.executable})
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(good.stdout.strip(), sys.executable)
        old = self.root / "old-python"
        old.write_text("#!/bin/sh\nexit 1\n")
        old.chmod(0o700)
        for invalid in ("python3", str(old)):
            with self.subTest(invalid=invalid):
                result = self.run_selector({"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                                            "TOTALMARKER_PYTHON": invalid})
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("Python 3.11+", result.stderr)

    def test_marker_entrypoint_parses_with_sparse_path_and_selected_python(self):
        result = subprocess.run([str(PROJECT / "scripts/run-totalmarker"), "--help"],
                                cwd=self.base,
                                env={"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                                     "TOTALMARKER_PYTHON": sys.executable,
                                     "PYTHONDONTWRITEBYTECODE": "1"},
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("{clouds,labels,quake,storm,volcano,norad,eclipse,santa}", result.stdout)

    def test_marker_launcher_reports_selected_interpreter_for_setup(self):
        result = subprocess.run([str(PROJECT / "scripts/run-totalmarker"), "--python-path"],
                                cwd=self.base,
                                env={"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                                     "TOTALMARKER_PYTHON": sys.executable},
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), sys.executable)

    def test_launcher_selects_path_python_without_override_in_sparse_environment(self):
        binary_dir = self.root / "bin"
        binary_dir.mkdir()
        (binary_dir / "python3").symlink_to(sys.executable)
        (binary_dir / "dirname").symlink_to("/usr/bin/dirname")
        environment = {"PATH": str(binary_dir),
                       "HOME": str(self.root), "PYTHONDONTWRITEBYTECODE": "1"}
        selected = self.run_selector(environment)
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout.strip(), str(binary_dir / "python3"))
        help_result = subprocess.run([str(PROJECT / "scripts/run-totalmarker"), "--help"],
                                     cwd=self.base, env=environment, capture_output=True,
                                     text=True, check=False)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("{clouds,labels,quake,storm,volcano,norad,eclipse,santa}",
                      help_result.stdout)

    def test_no_discoverable_python_fails_clearly(self):
        result = self.run_selector_with_controlled_probe(
            self.root / "no-match", self.root / "empty-home")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Python 3.11+ is required", result.stderr)

    def test_missing_explicit_python_fails_without_falling_back(self):
        binary_dir = self.root / "bin"
        binary_dir.mkdir()
        (binary_dir / "dirname").symlink_to("/usr/bin/dirname")
        (binary_dir / "python3").symlink_to(sys.executable)
        result = self.run_selector({"PATH": str(binary_dir),
                                    "TOTALMARKER_PYTHON": str(self.root / "missing-python")})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("not an executable Python 3.11+", result.stderr)
