"""The install workflow is exercised only with isolated command stubs."""
import os
import shutil
import subprocess
import sys

from .support import PROJECT, Sandbox, wait_for_prompt


class LauncherInstallTests(Sandbox):
    def test_install_fills_blank_public_definition_without_touching_example(self):
        self.prepare_real_setup()
        template = (PROJECT / "config/xp.def.example").read_bytes()
        self.definition.write_bytes(template)
        result = self.run_install("n\ny\ny\nq\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"XPLANET_BIN={self.prefix}/bin/xplanet\n",
                      self.definition.read_text())
        self.assertEqual((PROJECT / "config/xp.def.example").read_bytes(), template)
        self.assertEqual(self.calls(), self.expected_brew_calls())

    def test_config_parent_swap_at_replace_prompt_stops_before_write(self):
        self.prepare_real_setup()
        original = self.personal_definition("/prior/xplanet")
        self.definition.write_text(original)
        process = subprocess.Popen([str(self.launcher), "install"], cwd=self.base,
                                   env=self.environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.stdin.write(b"n\n")
            process.stdin.flush()
            wait_for_prompt(process, b"No Python package or virtual environment")
            process.stdin.write(b"y\n")
            process.stdin.flush()
            wait_for_prompt(process, b"Installed Xplanet differs from config/xp.def")
            outside = self.base / "outside-config"
            shutil.copytree(self.config, outside)
            self.config.rename(self.root / "config-original")
            self.config.symlink_to(outside, target_is_directory=True)
            process.communicate(b"y\n", timeout=5)
            self.assertEqual(process.returncode, 2)
            self.assertEqual((outside / "xp.def").read_text(), original)
            self.assertEqual(list(outside.glob(".xp.def.*")), [])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def setUp(self):
        super().setUp()
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.launcher = scripts / "xplanet.sh"
        shutil.copy2(PROJECT / "scripts/xplanet.sh", self.launcher)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.prefix = self.base / "formula"
        (self.prefix / "bin").mkdir(parents=True)
        self.trace = self.base / "trace"
        self.config = self.root / "config"
        self.config.mkdir()
        self.definition = self.config / "xp.def"
        self.definition.write_text(
            f"XPLANET_BIN={self.prefix}/bin/xplanet\n"
            "EARTH_MAP_PRE=world/world\n")
        self._script(
            self.bin / "brew",
            '#!/bin/sh\n'
            'printf "brew %s\\n" "$*" >> "$TM_TRACE"\n'
            'if [ "$1" = "--prefix" ]; then printf "%s\\n" "$TM_PREFIX"; fi\n'
            'if [ "$TM_FAIL" = "$1" ]; then exit 17; fi\n'
            'if [ "$TM_FAIL" = "install-python" ] && [ "$1 $2" = "install python" ]; then exit 17; fi\n'
            'exit 0\n')
        self._script(
            self.prefix / "bin/xplanet",
            '#!/bin/sh\n'
            'printf "xplanet %s\\n" "$*" >> "$TM_TRACE"\n'
            'exit "$TM_XPLANET_EXIT"\n')
        self._script(
            scripts / "xp-setup.sh",
            '#!/bin/sh\n'
            'printf "setup %s\\n" "$*" >> "$TM_TRACE"\n'
            'exit "$TM_SETUP_EXIT"\n')
        self.environment = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "TM_TRACE": str(self.trace),
            "TM_PREFIX": str(self.prefix),
            "TM_FAIL": "",
            "TM_XPLANET_EXIT": "0",
            "TM_SETUP_EXIT": "0",
        }

    def personal_definition(self, binary):
        return (PROJECT / "config/xp.def.example").read_text().replace(
            "XPLANET_BIN=\n", "XPLANET_BIN=" + binary + "\n")

    def prepare_real_setup(self):
        for name in ("xp.def", "xp.conf", "totalmarker", "earth"):
            example = ("config/totalmarker.example.toml" if name == "totalmarker"
                       else f"config/{name}.example")
            shutil.copy2(PROJECT / example, self.root / example)
        scripts = self.root / "scripts"
        shutil.copy2(PROJECT / "scripts/xp-setup.sh", scripts / "xp-setup.sh")
        runner = scripts / "run-totalmarker"
        self._script(runner, '#!/bin/sh\n'
                     'if [ "$1" = --python-path ]; then printf "%s\\n" "$TM_PYTHON"; exit 0; fi\n'
                     'exit 42\n')
        self.environment["TM_PYTHON"] = sys.executable

    @staticmethod
    def _script(path, content):
        path.write_text(content)
        path.chmod(0o755)

    def run_install(self, answers="", **environment):
        return subprocess.run(
            [str(self.launcher), "install"], cwd=self.base,
            env={**self.environment, **environment}, input=answers,
            text=True, capture_output=True, timeout=5)

    def calls(self):
        return self.trace.read_text().splitlines() if self.trace.exists() else []

    def expected_brew_calls(self):
        return [
            "brew tap blogabe/xplanet",
            "brew trust blogabe/xplanet",
            "brew install --formula --build-from-source blogabe/xplanet/xplanet --without-giflib --with-cspice",
            "brew install python",
            "brew --prefix blogabe/xplanet/xplanet",
        ]

    def test_success_runs_one_prompted_frame_then_setup(self):
        result = self.run_install("y\n", TM_SETUP_EXIT="37")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(
            self.calls(), self.expected_brew_calls() + [
                f"xplanet -searchdir={self.root} -num_times=1", "setup "])

    def test_declining_optional_frame_still_enters_setup(self):
        result = self.run_install("n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), self.expected_brew_calls() + ["setup "])

    def test_trust_failure_stops_before_install_and_setup(self):
        result = self.run_install(TM_FAIL="trust")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not trust", result.stderr)
        self.assertEqual(self.calls(), self.expected_brew_calls()[:2])

    def test_python_failure_stops_before_setup(self):
        result = self.run_install(TM_FAIL="install-python")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.calls(), self.expected_brew_calls()[:4])

    def test_existing_config_requires_explicit_replacement(self):
        self.prepare_real_setup()
        original = self.personal_definition("/my/current/xplanet")
        self.definition.write_text(original)
        result = self.run_install("n\ny\nn\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Kept config/xp.def unchanged", result.stderr)
        self.assertEqual(self.definition.read_text(), original)
        self.assertEqual(self.calls(), self.expected_brew_calls())

        self.trace.unlink()
        result = self.run_install("n\ny\ny\nq\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.definition.read_text(),
                         self.personal_definition(f"{self.prefix}/bin/xplanet"))
        self.assertEqual(self.calls(), self.expected_brew_calls())

    def test_missing_config_requires_shipped_example_before_setup(self):
        self.prepare_real_setup()
        self.definition.unlink()
        (self.config / "xp.def.example").unlink()
        result = self.run_install("n\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("config/xp.def.example", result.stderr)
        self.assertEqual(self.calls(), self.expected_brew_calls())

    def test_missing_config_is_deferred_to_confirmed_setup(self):
        self.definition.unlink()
        shutil.copy2(PROJECT / "config/xp.def.example", self.config / "xp.def.example")
        result = self.run_install("n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.definition.exists())  # The setup fixture is a stub.
        self.assertEqual(self.calls(), self.expected_brew_calls() + ["setup "])

    def test_install_to_real_setup_bootstraps_only_after_confirmation(self):
        self.definition.unlink()
        for name in ("xp.def", "xp.conf", "totalmarker", "earth"):
            example = ("config/totalmarker.example.toml" if name == "totalmarker"
                       else f"config/{name}.example")
            shutil.copy2(PROJECT / example, self.root / example)
        scripts = self.root / "scripts"
        shutil.copy2(PROJECT / "scripts/xp-setup.sh", scripts / "xp-setup.sh")
        runner = scripts / "run-totalmarker"
        self._script(runner, '#!/bin/sh\n'
                     'if [ "$1" = --python-path ]; then printf "%s\n" "$TM_PYTHON"; exit 0; fi\n'
                     'exit 42\n')
        self.environment["TM_PYTHON"] = sys.executable
        declined = self.run_install("n\nn\n")
        self.assertEqual(declined.returncode, 0, declined.stderr)
        for name in ("xp.def", "xp.conf", "totalmarker.toml", "earth"):
            self.assertFalse((self.config / name).exists(), name)
        self.trace.unlink()
        accepted = self.run_install("n\ny\nq\n")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn(f"XPLANET_BIN={self.prefix}/bin/xplanet", self.definition.read_text())
        self.assertEqual((self.config / "xp.conf").read_bytes(),
                         (self.config / "xp.conf.example").read_bytes())
        self.assertTrue((self.config / "totalmarker.toml").is_file())
        self.assertTrue((self.config / "earth").is_file())
        self.assertEqual(self.calls(), self.expected_brew_calls())

    def test_new_homebrew_python_survives_install_handoff_and_fresh_shell(self):
        self.prepare_real_setup()
        self.definition.write_text(self.personal_definition(f"{self.prefix}/bin/xplanet"))
        scripts = self.root / "scripts"
        shutil.copy2(PROJECT / "scripts/run-totalmarker", scripts / "run-totalmarker")
        brew_prefix = self.base / "Homebrew prefix with spaces"
        (brew_prefix / "bin").mkdir(parents=True)
        selected = brew_prefix / "bin/python3"
        self.assertFalse(selected.exists())
        self._script(self.bin / "python3", "#!/bin/sh\nexit 1\n")
        (self.bin / "dirname").symlink_to("/usr/bin/dirname")
        (self.bin / "grep").symlink_to("/usr/bin/grep")
        (self.bin / "readlink").symlink_to("/usr/bin/readlink")
        self._script(self.bin / "brew",
                     '#!/bin/sh\n'
                     'printf "brew %s\\n" "$*" >> "$TM_TRACE"\n'
                     'if [ "$1" = --prefix ]; then\n'
                     '  if [ "$#" -eq 1 ]; then printf "%s\\n" "$TM_BREW_PREFIX";\n'
                     '  else printf "%s\\n" "$TM_PREFIX"; fi\n'
                     '  exit 0\n'
                     'fi\n'
                     'if [ "$1 $2" = "install python" ]; then\n'
                     '  ln -sf "$TM_PYTHON" "$TM_BREW_PREFIX/bin/python3"\n'
                     'fi\n'
                     'exit 0\n')
        self.environment.update(PATH=f"{self.bin}:/bin",
                                TM_BREW_PREFIX=str(brew_prefix), TM_PYTHON=sys.executable)
        self.environment.pop("TOTALMARKER_PYTHON", None)
        installed = self.run_install("n\ny\nq\n")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(selected.is_symlink())
        self.assertIn(f"TotalMarker will use {selected}", installed.stdout)
        self.assertIn("brew --prefix", self.calls())
        standalone = subprocess.run([str(self.launcher), "setup"], cwd=self.base,
                                    env=self.environment, input="y\nq\n",
                                    text=True, capture_output=True, check=False)
        self.assertEqual(standalone.returncode, 0, standalone.stderr)
        self.assertIn(f"TotalMarker will use {selected}", standalone.stdout)
        bad_override = self.run_install("n\n", TOTALMARKER_PYTHON=str(self.base / "missing-python"))
        self.assertEqual(bad_override.returncode, 2)
        self.assertIn("TOTALMARKER_PYTHON is not an executable", bad_override.stderr)

    def test_install_rejects_setup_options(self):
        result = subprocess.run(
            [str(self.launcher), "install", "--check"], cwd=self.base,
            env=self.environment, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])
