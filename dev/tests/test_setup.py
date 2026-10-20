"""Preparation writes only to isolated project fixture roots."""
from datetime import datetime
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys

from .support import PROJECT, Sandbox, wait_for_prompt


class SetupTests(Sandbox):
    def test_public_stock_templates_prepare_without_private_maps(self):
        scripts, env, _ = self._shell_fixture()
        shutil.rmtree(self.root / "assets")
        for name in ("xp.conf", "xp.def"):
            example = (PROJECT / "config" / f"{name}.example").read_text()
            if name == "xp.def":
                example = example.replace("XPLANET_BIN=\n",
                                          "XPLANET_BIN=" + shlex.quote(str(self.root / "mock-xplanet")) + "\n")
            (self.root / "config" / name).write_text(example)
        dry = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("Would link markers/earth", dry.stdout)
        self.assertNotIn("Would link images/earth.png", dry.stdout)
        done = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.root / "markers/earth").readlink(), Path("../config/earth"))
        self.assertFalse((self.root / "images/earth.png").exists())
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 0)

    def test_config_parent_swap_at_first_prompt_stops_before_copy(self):
        scripts, env, _ = self._shell_fixture()
        process = subprocess.Popen([str(scripts / "xp-setup.sh")], cwd=PROJECT,
                                   env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            wait_for_prompt(process, b"No Python package or virtual environment")
            outside = self.base / "outside-config"
            shutil.copytree(self.root / "config", outside)
            (self.root / "config").rename(self.root / "config-original")
            (self.root / "config").symlink_to(outside, target_is_directory=True)
            process.communicate(b"y\n", timeout=5)
            self.assertEqual(process.returncode, 2)
            self.assertFalse((outside / "totalmarker.toml").exists())
            self.assertFalse((outside / "earth").exists())
            self.assertFalse((self.root / "arcs").exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def setUp(self):
        super().setUp()
        config = self.root / "config"
        config.mkdir()
        xplanet = self.root / "mock-xplanet"
        xplanet.write_text("#!/bin/sh\nexit 0\n")
        xplanet.chmod(0o700)
        (config / "xp.conf").write_bytes(b"marker_file=markers/quake\n")
        (config / "xp.def").write_text(
            "#EARTH_MAP_PRE=other/other\nEARTH_MAP_PRE=world/world\n"
            "XPLANET_BIN=" + shlex.quote(str(xplanet)) + "\n"
            "XPLANET_HOME=" + shlex.quote(str(self.root)) + "\n"
            "XPLANET_CONFIG=" + shlex.quote(str(config)) + "\n")
        (config / "totalmarker.example.toml").write_bytes(b"personal example\n")
        (config / "earth.example").write_bytes(b"earth example\n")
        self.sources = {
            f"assets/maps/world/world.2004{datetime.now().month:02d}.3x5400x2700.png": b"map",
            "assets/maps/lights/earth_lights_4800.tiff": b"lights",
            "assets/maps/bump/gebco_08_rev_elev_21600x10800.png": b"bump",
            "assets/maps/specular/specular.png": b"specular",
        }
        for name, data in self.sources.items():
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

    def test_initialization_repeat_and_expected_products(self):
        scripts, env, products = self._shell_fixture()
        dry = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("Would mkdir arcs", dry.stdout)
        self.assertIn("Would link markers/earth <- ../config/earth", dry.stdout)
        self.assertIn("Would copy config/totalmarker.toml", dry.stdout)
        self.assertFalse((self.root / "arcs").exists())
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 1)
        done = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / "arcs").is_dir())
        self.assertTrue((self.root / "logs/totalmarker").is_dir())
        self.assertTrue((self.root / ".state/totalmarker").is_dir())
        self.assertEqual((self.root / "config/totalmarker.toml").read_bytes(), b"personal example\n")
        self.assertEqual((self.root / "config/earth").read_bytes(), b"earth example\n")
        self.assertEqual((self.root / "config/totalmarker.toml").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "config/earth").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "markers/earth").readlink(), Path("../config/earth"))
        self.assertEqual((self.root / "images/earth.png").read_bytes(), b"map")
        for name in ("arcs/storm", "markers/quake", "markers/storm", "markers/volcano",
                     "images/clouds-4096.jpg"):
            self.assertFalse((self.root / name).exists())
        self.assertFalse((self.root / "scripts/launchd").exists())
        self.assertFalse(products.exists())
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 0)
        self.assertEqual(self._inspect(scripts, env, input="y\nq\n").returncode, 0)

    def test_fresh_config_bootstrap_waits_for_confirmation_and_is_repeatable(self):
        spaced = self.base / "fresh root with spaces"
        self.root.rename(spaced)
        self.root = spaced
        config = self.root / "config"
        for name in ("xp.conf", "xp.def"):
            (config / name).unlink()
            shutil.copy2(PROJECT / "config" / f"{name}.example",
                         config / f"{name}.example")
        bin_dir = self.base / "bin with spaces"
        bin_dir.mkdir()
        xplanet = bin_dir / "xplanet"
        xplanet.write_text("#!/bin/sh\nexit 0\n")
        xplanet.chmod(0o700)
        scripts, env, _ = self._shell_fixture()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["XPLANET_INSTALLED_BIN"] = str(xplanet)
        dry = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("Would copy config/xp.conf", dry.stdout)
        self.assertIn("Would copy config/xp.def", dry.stdout)
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 1)
        declined = self._inspect(scripts, env, input="n\n")
        self.assertEqual(declined.returncode, 0, declined.stderr)
        self.assertFalse((config / "xp.conf").exists())
        self.assertFalse((config / "xp.def").exists())
        accepted = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual((config / "xp.conf").read_bytes(),
                         (config / "xp.conf.example").read_bytes())
        definition = (config / "xp.def").read_text()
        self.assertIn("XPLANET_BIN=", definition)
        self.assertIn(str(xplanet).replace(" ", "\\ "), definition)
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 0)
        self.assertEqual(self._inspect(scripts, env, input="y\nq\n").returncode, 0)
        self.assertEqual((config / "xp.def").read_text(), definition)

    def test_new_personal_file_created_at_prompt_is_not_overwritten(self):
        config = self.root / "config"
        (config / "xp.conf").unlink()
        shutil.copy2(PROJECT / "config/xp.conf.example", config / "xp.conf.example")
        scripts, env, _ = self._shell_fixture()
        process = subprocess.Popen([str(scripts / "xp-setup.sh")], cwd=PROJECT,
                                   env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            wait_for_prompt(process, b"No Python package or virtual environment")
            (config / "xp.conf").write_bytes(b"personal config created during prompt")
            process.communicate(b"y\n", timeout=5)
            self.assertEqual(process.returncode, 2)
            self.assertEqual((config / "xp.conf").read_bytes(),
                             b"personal config created during prompt")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_missing_example_names_file_and_preserves_existing_config(self):
        config = self.root / "config"
        custom = (config / "xp.def").read_bytes()
        (config / "xp.conf").unlink()
        scripts, env, _ = self._shell_fixture()
        result = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("config/xp.conf is missing", result.stderr)
        self.assertIn("config/xp.conf.example", result.stderr)
        self.assertEqual((config / "xp.def").read_bytes(), custom)
        self.assertFalse((config / "xp.conf").exists())

    def test_mixed_existing_config_is_not_replaced(self):
        config = self.root / "config"
        custom = (config / "xp.conf").read_bytes()
        (config / "xp.def").unlink()
        shutil.copy2(PROJECT / "config/xp.def.example", config / "xp.def.example")
        scripts, env, _ = self._shell_fixture()
        env["XPLANET_INSTALLED_BIN"] = str(self.root / "mock-xplanet")
        done = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((config / "xp.conf").read_bytes(), custom)
        self.assertIn("XPLANET_BIN=", (config / "xp.def").read_text())

    def test_inspection_modes_do_not_need_the_totalmarker_launcher(self):
        scripts, env, _ = self._shell_fixture()
        (scripts / "run-totalmarker").unlink()
        self.assertEqual(self._inspect(scripts, env, "--dry-run").returncode, 0)
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 1)
        self.assertFalse((self.root / "arcs").exists())

    def test_existing_custom_files_and_links_are_preserved(self):
        (self.root / "images").mkdir()
        (self.root / "markers").mkdir()
        (self.root / "config/totalmarker.toml").write_bytes(b"custom toml")
        (self.root / "config/earth").write_bytes(b"custom earth")
        (self.root / "images/earth.png").write_bytes(b"custom map")
        (self.root / "images/lights.tiff").symlink_to("../assets/maps/lights/earth_lights_4800.tiff")
        scripts, env, _ = self._shell_fixture()
        done = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        for name, data in (("config/totalmarker.toml", b"custom toml"),
                           ("config/earth", b"custom earth"),
                           ("images/earth.png", b"custom map")):
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertEqual((self.root / "images/lights.tiff").readlink(),
                         Path("../assets/maps/lights/earth_lights_4800.tiff"))

    def test_external_dangling_and_parent_links_refuse_before_writes(self):
        scripts, env, _ = self._shell_fixture()
        (self.root / "images").mkdir()
        link = self.root / "images/earth.png"
        for target in ("../../outside.png", "../assets/maps/world/missing.png"):
            with self.subTest(target=target):
                link.symlink_to(target)
                self.assertEqual(self._inspect(scripts, env).returncode, 2)
                self.assertFalse((self.root / "arcs").exists())
                link.unlink()
        (self.root / "images").rmdir()
        (self.root / "images").symlink_to(self.base)
        result = self._inspect(scripts, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("real directory", result.stderr)
        self.assertFalse((self.root / "arcs").exists())

    def test_existing_link_to_other_internal_file_is_not_accepted(self):
        scripts, env, _ = self._shell_fixture()
        (self.root / "images").mkdir()
        (self.root / "images/earth.png").symlink_to("../config/xp.def")
        result = self._inspect(scripts, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("internal map asset", result.stderr)
        self.assertFalse((self.root / "arcs").exists())

    def test_unsafe_examples_missing_assets_and_invalid_map_prefix(self):
        scripts, env, _ = self._shell_fixture()
        example = self.root / "config/earth.example"
        example.unlink()
        example.symlink_to(self.base / "outside")
        result = self._inspect(scripts, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("restore the shipped config/earth.example", result.stderr)
        self.assertFalse((self.root / "arcs").exists())
        example.unlink()
        example.write_bytes(b"earth")
        personal = self.root / "config/totalmarker.toml"
        personal.symlink_to(self.base / "outside")
        result = self._inspect(scripts, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("config/totalmarker.toml must be a real regular file", result.stderr)
        self.assertFalse((self.root / "arcs").exists())
        personal.unlink()
        source = self.root / "assets/maps/specular/specular.png"
        source.unlink()
        result = self._inspect(scripts, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("specular.png", result.stderr)
        source.write_bytes(b"specular")
        (self.root / "config/xp.def").write_text("EARTH_MAP_PRE=../../outside\n")
        result = self._inspect(scripts, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("safe folder/name", result.stderr)

    def test_cli_modes_and_space_containing_root(self):
        spaced = self.base / "project with spaces"
        old_root = self.root
        self.root.rename(spaced)
        self.root = spaced
        definition = spaced / "config/xp.def"
        definition.write_text(definition.read_text().replace(str(old_root),
                                                             shlex.quote(str(spaced))))
        scripts, env, _ = self._shell_fixture()
        dry = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("Would mkdir arcs", dry.stdout)
        self.assertFalse((spaced / "arcs").exists())
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 1)
        done = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 0)

    def test_solarsystem_retained_asset_is_used_for_new_link(self):
        scripts, env, _ = self._shell_fixture()
        dry = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("assets/maps/solarsystem is absent", dry.stdout)
        self.assertNotIn("Would link images/solarsystem", dry.stdout)
        source = self.root / "assets/maps/solarsystem"
        source.mkdir()
        dry = self._inspect(scripts, env, "--dry-run")
        self.assertIn("Would link images/solarsystem <- ../assets/maps/solarsystem", dry.stdout)
        done = self._inspect(scripts, env, input="y\nq\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        solar_link = self.root / "images/solarsystem"
        self.assertEqual(solar_link.readlink(), Path("../assets/maps/solarsystem"))
        solar_link.unlink()
        solar_link.symlink_to("../assets/maps/solarsystem")
        self.assertEqual(self._inspect(scripts, env, "--check").returncode, 0)
        self.assertEqual(solar_link.readlink(), Path("../assets/maps/solarsystem"))
        solar_link.unlink()
        solar_link.symlink_to(self.base)
        unsafe = self._inspect(scripts, env, "--dry-run")
        self.assertEqual(unsafe.returncode, 2)
        self.assertIn("outside the project", unsafe.stderr)

    def _assert_retry(self, result, scripts, product):
        lines = [line.strip()[len("Retry: "):] for line in result.stderr.splitlines()
                 if line.strip().startswith("Retry: ")]
        self.assertIn([str(scripts / "xplanet.sh"), product],
                      [shlex.split(line) for line in lines])

    def _inspect(self, scripts, env, mode=None, *, input=None, cwd=None):
        command = [str(scripts / "xp-setup.sh")]
        if mode is not None:
            command.append(mode)
        return subprocess.run(command, cwd=PROJECT if cwd is None else cwd,
                              env=env, input=input,
                              capture_output=True, text=True, check=False)

    def test_shell_wrapper_prepares_fixture_without_using_checkout(self):
        scripts, env, products = self._shell_fixture()
        command = [str(scripts / "xp-setup.sh")]
        launcher = [str(scripts / "xplanet.sh")]
        launcher_dry = subprocess.run([*launcher, "setup", "--dry-run"],
                                      cwd=PROJECT, env=env, capture_output=True,
                                      text=True, check=False)
        self.assertEqual(launcher_dry.returncode, 0, launcher_dry.stderr)
        self.assertFalse((self.root / "arcs").exists())
        launcher_check = subprocess.run([*launcher, "setup", "--check"],
                                        cwd=PROJECT, env=env, capture_output=True,
                                        text=True, check=False)
        self.assertEqual(launcher_check.returncode, 1, launcher_check.stderr)
        dry = subprocess.run([*command, "--dry-run"], cwd=PROJECT, env=env,
                             capture_output=True, text=True, check=False)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse((self.root / "arcs").exists())
        override = subprocess.run([*command, "--root", str(self.base), "--check"],
                                  cwd=PROJECT, env=env, capture_output=True,
                                  text=True, check=False)
        self.assertEqual(override.returncode, 2, override.stderr)
        done = subprocess.run([*launcher, "setup"], cwd=PROJECT, env=env,
                              input="y\n\ny\ny\ny\nn\nn\n", capture_output=True,
                              text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / "arcs").is_dir())
        self.assertEqual(products.read_text().splitlines(), ["quake", "storm", "volcano"])
        launcher_ready = subprocess.run([*launcher, "setup", "--check"],
                                        cwd=PROJECT, env=env, capture_output=True,
                                        text=True, check=False)
        self.assertEqual(launcher_ready.returncode, 0, launcher_ready.stderr)

    def _shell_fixture(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("xp-setup.sh", "xplanet.sh"):
            shutil.copy2(PROJECT / "scripts" / name, scripts / name)
        runner = scripts / "run-totalmarker"
        runner.write_text('#!/bin/sh\n'
                          'if [ "$1" = --python-path ]; then printf "%s\\n" "$TM_PYTHON"; exit 0; fi\n'
                          'printf "%s\\n" "$1" >> "$TM_SETUP_PRODUCTS"\n'
                          'if [ "$1" = "$TM_FAIL_PRODUCT" ]; then\n'
                          "  printf '{\"outcome\": \"failed\", \"message\": \"%s\"}\\n' \"$TM_FAIL_MESSAGE\"\n"
                          '  exit "$TM_FAIL_STATUS"\n'
                          'fi\nexit 0\n')
        runner.chmod(0o700)
        products = self.base / "products.txt"
        env = {"PATH": "/usr/bin:/bin", "TOTALMARKER_PYTHON": sys.executable,
               "PYTHONDONTWRITEBYTECODE": "1", "TM_SETUP_PRODUCTS": str(products),
               "TM_FAIL_PRODUCT": "", "TM_FAIL_MESSAGE": "Mock source unavailable",
               "TM_FAIL_STATUS": "1", "TM_PYTHON": sys.executable}
        return scripts, env, products

    def test_interactive_automation_uses_stub_only(self):
        scripts, env, products = self._shell_fixture()
        examples = scripts / "launchd"
        examples.mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, examples / source.name)
        home = self.base / "home with spaces"
        home.mkdir()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        calls = self.base / "launchctl-calls.txt"
        launchctl = bin_dir / "launchctl"
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TM_LAUNCHCTL_CALLS"\n'
                             '[ "$1" = list ] && [ "$2" = "$TM_LIST_FAIL_LABEL" ] && exit 3\n'
                             'exit 0\n')
        launchctl.chmod(0o700)
        env.update(HOME=str(home), PATH=f"{bin_dir}:/usr/bin:/bin",
                   TM_LAUNCHCTL_CALLS=str(calls), TM_LIST_FAIL_LABEL="")
        command = [str(scripts / "xplanet.sh"), "setup"]
        done = subprocess.run(command, cwd=PROJECT, env=env,
                              input="y\n\ny\ny\ny\ny\ny\n", capture_output=True,
                              text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Setup complete.", done.stdout)
        self.assertIn("If macOS asks to let Xplanet control Finder, choose Allow", done.stdout)
        self.assertIn("Allow a few minutes for the first desktop update", done.stdout)
        self.assertLess(done.stdout.index("Setup complete."),
                        done.stdout.index("If macOS asks to let Xplanet control Finder"))
        self.assertEqual(products.read_text().splitlines(),
                         ["quake", "storm", "volcano", "clouds"])
        jobs = ("start", "earth-map", "quake", "storm", "volcano", "clouds")
        self.assertEqual(calls.read_text().splitlines(), [line for job in jobs for line in (
            f"load -w {home}/Library/LaunchAgents/local.xplanet.{job}.plist",
            f"list local.xplanet.{job}")])
        for job in jobs:
            local = examples / f"local.xplanet.{job}.plist"
            self.assertEqual((home / "Library/LaunchAgents" / local.name).readlink(), local)

    def test_selected_homebrew_python_is_written_to_new_launchd_jobs(self):
        scripts, env, _ = self._shell_fixture()
        shutil.copy2(PROJECT / "scripts/run-totalmarker", scripts / "run-totalmarker")
        examples = scripts / "launchd"
        examples.mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, examples / source.name)
        home = self.base / "home"
        home.mkdir()
        prefix = self.base / "custom Homebrew prefix"
        (prefix / "bin").mkdir(parents=True)
        selected = prefix / "bin/python3"
        selected.symlink_to(sys.executable)
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        old = bin_dir / "python3"
        old.write_text("#!/bin/sh\nexit 1\n")
        old.chmod(0o700)
        for name in ("dirname", "grep", "readlink", "mktemp"):
            (bin_dir / name).symlink_to("/usr/bin/" + name)
        brew = bin_dir / "brew"
        brew.write_text('#!/bin/sh\n'
                        '[ "$1" = --prefix ] || exit 9\n'
                        'printf "%s\\n" "$TM_BREW_PREFIX"\n')
        brew.chmod(0o700)
        launchctl = bin_dir / "launchctl"
        launchctl.write_text('#!/bin/sh\nexit 0\n')
        launchctl.chmod(0o700)
        env.pop("TOTALMARKER_PYTHON")
        env.update(HOME=str(home), PATH=f"{bin_dir}:/bin",
                   TM_BREW_PREFIX=str(prefix))
        done = self._inspect(scripts, env, input="y\n\nn\nn\nn\nn\ny\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"TotalMarker will use {selected}", done.stdout)
        for job in ("start", "earth-map", "quake", "storm", "volcano"):
            local = examples / f"local.xplanet.{job}.plist"
            document = plistlib.loads(local.read_bytes())
            self.assertEqual(document["EnvironmentVariables"]["TOTALMARKER_PYTHON"],
                             str(selected))

    def test_interactive_automation_refuses_personal_plist_without_loading(self):
        scripts, env, products = self._shell_fixture()
        examples = scripts / "launchd"
        examples.mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, examples / source.name)
        personal = examples / "local.xplanet.start.plist"
        personal.write_bytes(b"custom local plist")
        home = self.base / "home"
        home.mkdir()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        calls = self.base / "launchctl-calls.txt"
        launchctl = bin_dir / "launchctl"
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TM_LAUNCHCTL_CALLS"\n'
                             'exit 0\n')
        launchctl.chmod(0o700)
        env.update(HOME=str(home), PATH=f"{bin_dir}:/usr/bin:/bin",
                   TM_LAUNCHCTL_CALLS=str(calls))
        done = subprocess.run([str(scripts / "xplanet.sh"), "setup"],
                              cwd=PROJECT, env=env, input="y\n\ny\ny\ny\nn\ny\n",
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 1)
        self.assertIn("launchd file preparation failed", done.stderr)
        self.assertEqual(personal.read_bytes(), b"custom local plist")
        self.assertFalse(calls.exists())
        self.assertEqual(products.read_text().splitlines(), ["quake", "storm", "volcano"])

    def test_product_skip_and_refresh_warning_continue_into_automation(self):
        scripts, env, products = self._shell_fixture()
        env["TM_FAIL_PRODUCT"] = "volcano"
        examples = scripts / "launchd"
        examples.mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, examples / source.name)
        home = self.base / "home"
        home.mkdir()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        calls = self.base / "launchctl-calls.txt"
        launchctl = bin_dir / "launchctl"
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TM_LAUNCHCTL_CALLS"\n'
                             'exit 0\n')
        launchctl.chmod(0o700)
        env.update(HOME=str(home), PATH=f"{bin_dir}:/usr/bin:/bin",
                   TM_LAUNCHCTL_CALLS=str(calls))
        done = subprocess.run([str(scripts / "xplanet.sh"), "setup"],
                              cwd=PROJECT, env=env, input="y\n\nn\nn\ny\ny\ny\n",
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(products.read_text().splitlines(), ["volcano", "clouds"])
        self.assertEqual(sum(line.startswith("load -w ") for line in calls.read_text().splitlines()), 6)
        self.assertIn("volcano refresh failed", done.stderr)
        self.assertIn("volcano: Mock source unavailable", done.stderr)
        self._assert_retry(done, scripts, "volcano")
        self.assertIn("Setup complete with refresh warnings.", done.stdout)
        self.assertIn("If macOS asks to let Xplanet control Finder, choose Allow", done.stdout)

    def test_volcano_http_403_warns_without_blocking_cloud_or_erasing_marker(self):
        scripts, env, products = self._shell_fixture()
        marker = self.root / "markers/volcano"
        marker.parent.mkdir()
        marker.write_bytes(b"last good volcano marker")
        runner = scripts / "run-totalmarker"
        runner.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = --python-path ]; then printf "%s\\n" "$TM_PYTHON"; exit 0; fi\n'
            'printf "%s\\n" "$1" >> "$TM_SETUP_PRODUCTS"\n'
            'if [ "$1" = volcano ]; then\n'
            '  printf "%s\\n" \'{"outcome": "failed", "message": "Source returned HTTP 403; server=cloudflare"}\'\n'
            '  exit 1\n'
            'fi\n'
            'exit 0\n')
        done = self._inspect(scripts, env, input="y\n\nn\nn\ny\ny\nn\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(products.read_text().splitlines(), ["volcano", "clouds"])
        self.assertEqual(marker.read_bytes(), b"last good volcano marker")
        self.assertIn("volcano: Source returned HTTP 403; server=cloudflare", done.stderr)
        self.assertIn("Optional refresh warning", done.stderr)
        self._assert_retry(done, scripts, "volcano")
        self.assertNotIn("failed core step", done.stderr)
        self.assertIn("Setup complete with refresh warnings.", done.stdout)

    def test_each_optional_refresh_failure_warns_with_custom_output_present_or_absent(self):
        scripts, env, products = self._shell_fixture()
        (self.root / "config/totalmarker.toml").write_text(
            '[quake]\noutput = "markers/personal-quake"\n'
            '[storm]\noutput = "markers/personal-storm"\narc_output = "arcs/personal-storm"\n'
            '[volcano]\noutput = "markers/personal-volcano"\n'
            '[cloud]\nlocal_image_name = "personal-cloud.jpg"\n')
        outputs = {
            "quake": ("markers/personal-quake",),
            "storm": ("markers/personal-storm", "arcs/personal-storm"),
            "volcano": ("markers/personal-volcano",),
            "clouds": ("images/personal-cloud.jpg",),
        }
        for product in outputs:
            for previous_output in (False, True):
                with self.subTest(product=product, previous_output=previous_output):
                    products.unlink(missing_ok=True)
                    for name in outputs[product]:
                        path = self.root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if previous_output:
                            path.write_bytes(b"last good custom output")
                        else:
                            path.unlink(missing_ok=True)
                    env["TM_FAIL_PRODUCT"] = product
                    env["TM_FAIL_MESSAGE"] = f"{product} provider unavailable"
                    choices = "".join("y\n" if choice == product else "n\n"
                                      for choice in ("quake", "storm", "volcano", "clouds"))
                    done = self._inspect(scripts, env, input="y\n\n" + choices + "n\n")
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(products.read_text().splitlines(), [product])
                    self.assertIn(f'"message": "{product} provider unavailable"', done.stdout)
                    self.assertIn(f"{product}: {product} provider unavailable", done.stderr)
                    self._assert_retry(done, scripts, product)
                    self.assertIn("If no previous output exists, that layer is unavailable",
                                  done.stderr)
                    self.assertIn("Setup complete with refresh warnings.", done.stdout)
                    for name in outputs[product]:
                        path = self.root / name
                        if previous_output:
                            self.assertEqual(path.read_bytes(), b"last good custom output")
                        else:
                            self.assertFalse(path.exists())

    def test_all_optional_refreshes_can_warn_together(self):
        scripts, env, products = self._shell_fixture()
        runner = scripts / "run-totalmarker"
        runner.write_text('#!/bin/sh\n'
                          'if [ "$1" = --python-path ]; then printf "%s\\n" "$TM_PYTHON"; exit 0; fi\n'
                          'printf "%s\\n" "$1" >> "$TM_SETUP_PRODUCTS"\n'
                          "printf '{\"outcome\": \"failed\", \"message\": \"%s unavailable\"}\\n' \"$1\"\n"
                          'exit 1\n')
        done = self._inspect(scripts, env, input="y\n\ny\ny\ny\ny\nn\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(products.read_text().splitlines(),
                         ["quake", "storm", "volcano", "clouds"])
        for product in ("quake", "storm", "volcano", "clouds"):
            self.assertIn(f"{product}: {product} unavailable", done.stderr)
            self._assert_retry(done, scripts, product)
        self.assertIn("Setup complete with refresh warnings.", done.stdout)

    def test_exit_one_without_valid_failed_result_remains_core_failure(self):
        scripts, env, _ = self._shell_fixture()
        runner = scripts / "run-totalmarker"
        for payload in (None, '{"outcome":"failed","message":"truncated"',
                        '{"outcome":"changed","message":"not a failure"}',
                        '{"outcome":"failed","message":7}',
                        '{"outcome":"failed","message":""}',
                        '<?xml version="1.0"?><plist version="1.0"><dict>'
                        '<key>outcome</key><string>failed</string>'
                        '<key>message</key><string>feed</string></dict></plist>'):
            with self.subTest(payload=payload):
                result = (f"printf '%s\\n' {shlex.quote(payload)}\n" if payload is not None else "")
                runner.write_text('#!/bin/sh\n'
                                  'if [ "$1" = --python-path ]; then printf "%s\\n" "$TM_PYTHON"; exit 0; fi\n'
                                  + result + 'exit 1\n')
                done = self._inspect(scripts, env, input="y\n\nn\ny\nn\nn\nn\n")
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn("storm refresh: command exited with status 1 without a valid failed TotalMarker result",
                              done.stderr)
                self.assertIn("Setup finished with 1 failed core step(s):", done.stderr)
                self.assertNotIn("Optional refresh warning", done.stderr)
                self.assertNotIn("Setup complete", done.stdout)

    def test_missing_totalmarker_module_is_not_an_optional_refresh_warning(self):
        scripts, env, _ = self._shell_fixture()
        shutil.copy2(PROJECT / "scripts/run-totalmarker", scripts / "run-totalmarker")
        package = scripts / "totalmarker"
        package.mkdir()
        (package / "__init__.py").write_text("")
        direct = subprocess.run([str(scripts / "run-totalmarker"), "storm"],
                                cwd=self.base, env=env, capture_output=True,
                                text=True, check=False)
        self.assertEqual(direct.returncode, 1)
        self.assertEqual(direct.stdout, "")
        done = self._inspect(scripts, env, input="y\n\nn\ny\nn\nn\nn\n",
                             cwd=self.base)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("storm refresh: command exited with status 1 without a valid failed TotalMarker result",
                      done.stderr)
        self.assertNotIn("Optional refresh warning", done.stderr)
        self.assertNotIn("Setup complete", done.stdout)

    def test_actual_cli_config_and_storage_errors_remain_core_failures(self):
        scripts, env, _ = self._shell_fixture()
        shutil.copy2(PROJECT / "scripts/run-totalmarker", scripts / "run-totalmarker")
        shutil.copytree(PROJECT / "scripts/totalmarker", scripts / "totalmarker")
        cases = (
            ("quake", "[quake\n", "Cannot parse TOML configuration"),
            ("clouds", '[quake]\noutput = "../outside"\n',
             "Parent traversal is not allowed"),
        )
        for product, config_text, reason in cases:
            with self.subTest(product=product):
                (self.root / "config/totalmarker.toml").write_text(config_text)
                direct = subprocess.run([str(scripts / "run-totalmarker"), product],
                                        cwd=self.base, env=env, capture_output=True,
                                        text=True, check=False)
                self.assertEqual(direct.returncode, 2, direct.stdout + direct.stderr)
                self.assertIn(reason, direct.stdout)
                choices = "".join("y\n" if choice == product else "n\n"
                                  for choice in ("quake", "storm", "volcano", "clouds"))
                done = self._inspect(scripts, env, input="y\n\n" + choices + "n\n",
                                     cwd=self.base)
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn(reason, done.stdout)
                self.assertIn(f"{product} refresh: {reason} (exit 2)", done.stderr)
                self.assertIn("Setup finished with 1 failed core step(s):", done.stderr)
                self.assertNotIn("Optional refresh warning", done.stderr)
                self.assertNotIn("Setup complete", done.stdout)

    def test_unexpected_runner_statuses_remain_core_failures(self):
        scripts, env, _ = self._shell_fixture()
        for code in (4, 143):
            with self.subTest(exit_code=code):
                env.update(TM_FAIL_PRODUCT="storm", TM_FAIL_STATUS=str(code))
                done = self._inspect(scripts, env, input="y\n\nn\ny\nn\nn\nn\n")
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn(f"storm refresh: Mock source unavailable (exit {code})",
                              done.stderr)
                self.assertNotIn("Optional refresh warning", done.stderr)
                self.assertNotIn("Setup complete", done.stdout)

    def test_retry_uses_shell_quoted_absolute_checkout_path(self):
        old_root = self.root
        self.root = self.base / "project with spaces"
        old_root.rename(self.root)
        definition = self.root / "config/xp.def"
        definition.write_text(definition.read_text().replace(
            str(old_root), shlex.quote(str(self.root))))
        scripts, env, _ = self._shell_fixture()
        env["TM_FAIL_PRODUCT"] = "quake"
        done = self._inspect(scripts, env, input="y\n\ny\nn\nn\nn\nn\n",
                             cwd=self.base)
        self.assertEqual(done.returncode, 0, done.stderr)
        self._assert_retry(done, scripts, "quake")
        self.assertNotIn("Retry: scripts/xplanet.sh", done.stderr)

    def test_refresh_warning_and_automation_failure_keep_core_failure_nonzero(self):
        scripts, env, products = self._shell_fixture()
        examples = scripts / "launchd"
        examples.mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, examples / source.name)
        home = self.base / "home"
        home.mkdir()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        calls = self.base / "launchctl-calls.txt"
        launchctl = bin_dir / "launchctl"
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TM_LAUNCHCTL_CALLS"\n'
                             '[ "$1" = list ] && [ "$2" = local.xplanet.storm ] && exit 3\n'
                             'exit 0\n')
        launchctl.chmod(0o700)
        env.update(HOME=str(home), PATH=f"{bin_dir}:/usr/bin:/bin",
                   TM_LAUNCHCTL_CALLS=str(calls), TM_FAIL_PRODUCT="storm")
        done = self._inspect(scripts, env, input="y\n\nn\ny\nn\nn\ny\n")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(products.read_text().splitlines(), ["storm"])
        self.assertIn("storm: Mock source unavailable", done.stderr)
        self._assert_retry(done, scripts, "storm")
        self.assertIn("did not confirm registration of storm", done.stderr)
        self.assertIn("Setup finished with 1 failed core step(s):", done.stderr)
        self.assertNotIn("Setup complete", done.stdout)
        self.assertNotIn("If macOS asks to let Xplanet control Finder", done.stdout)
        self.assertEqual(sum(line.startswith("load -w ") for line in calls.read_text().splitlines()), 5)

    def test_declined_refreshes_and_direct_product_status(self):
        scripts, env, products = self._shell_fixture()
        env["TM_FAIL_PRODUCT"] = "storm"
        done = self._inspect(scripts, env, input="y\n\nn\nn\nn\nn\nn\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(products.exists())
        self.assertIn("Setup complete.", done.stdout)
        self.assertNotIn("If macOS asks to let Xplanet control Finder", done.stdout)
        self.assertNotIn("refresh warning", done.stdout + done.stderr)
        direct = subprocess.run([str(scripts / "xplanet.sh"), "storm"], cwd=PROJECT,
                                env=env, capture_output=True, text=True, check=False)
        self.assertEqual(direct.returncode, 1)
        self.assertIn('"outcome": "failed"', direct.stdout)
        self.assertNotIn("Setup complete", direct.stdout)

    def test_zero_exit_load_without_registration_is_reported_as_failure(self):
        scripts, env, products = self._shell_fixture()
        examples = scripts / "launchd"
        examples.mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, examples / source.name)
        home = self.base / "home"
        home.mkdir()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        calls = self.base / "launchctl-calls.txt"
        launchctl = bin_dir / "launchctl"
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TM_LAUNCHCTL_CALLS"\n'
                             '[ "$1" = list ] && [ "$2" = "$TM_LIST_FAIL_LABEL" ] && exit 3\n'
                             'exit 0\n')
        launchctl.chmod(0o700)
        env.update(HOME=str(home), PATH=f"{bin_dir}:/usr/bin:/bin",
                   TM_LAUNCHCTL_CALLS=str(calls),
                   TM_LIST_FAIL_LABEL="local.xplanet.volcano")
        done = subprocess.run([str(scripts / "xplanet.sh"), "setup"],
                              cwd=PROJECT, env=env, input="y\n\nn\nn\nn\nn\ny\n",
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("did not confirm registration of volcano", done.stderr)
        self.assertNotIn("Setup complete.", done.stdout)
        self.assertNotIn("If macOS asks to let Xplanet control Finder", done.stdout)
        self.assertEqual(sum(line.startswith("load -w ") for line in calls.read_text().splitlines()), 5)
        self.assertFalse(products.exists())
