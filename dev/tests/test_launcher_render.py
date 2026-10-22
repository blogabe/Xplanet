"""Launcher display and finite renders use fixture executables only."""
import json
import os
import shlex
import shutil
import subprocess

from .support import PROJECT, Sandbox


class LauncherRenderTests(Sandbox):
    def setUp(self):
        super().setUp()
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.wrapper = scripts / "xplanet.sh"
        shutil.copy2(PROJECT / "scripts/xplanet.sh", self.wrapper)
        self.capture = self.root / "dev/preview/capture.json"
        self.mock = scripts / "mock-xplanet"
        self.mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['MOCK_CAPTURE'], 'w') as output:\n"
            "    json.dump({'args': sys.argv[1:], 'tmp': os.environ.get('TMPDIR'), "
            "'cache': os.environ.get('XDG_CACHE_HOME')}, output)\n"
            "sys.exit(int(os.environ.get('MOCK_EXIT', '0')))\n")
        self.mock.chmod(0o700)
        (self.root / "config").mkdir()
        (self.root / "config/xp.conf").write_text('[earth]\n"Earth"\n')
        (self.root / "config/xp.def").write_text(
            "XPLANET_BIN=" + shlex.quote(str(self.mock)) + "\n"
            "XPLANET_HOME=" + shlex.quote(str(self.root)) + "\n"
            "XPLANET_CONFIG=" + shlex.quote(str(self.root / "config")) + "\n"
            "XPLANET_PROJECTION=lambert\nXPLANET_LONGITUDE=-118.3989\n"
            "XPLANET_GEOMETRY=1600x900\n")
        self.environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                            "MOCK_CAPTURE": str(self.capture),
                            "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(self, command, extra_environment=None):
        environment = {**self.environment, **(extra_environment or {})}
        return subprocess.run([str(self.wrapper), command], cwd=self.base,
                              env=environment, capture_output=True, text=True,
                              check=False)

    def test_render_is_one_frame_and_all_declared_writes_are_under_dev(self):
        result = self.invoke("render")
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = json.loads(self.capture.read_text())
        args = recorded["args"]
        self.assertEqual(args[args.index("-geometry") + 1], "1600x900")
        self.assertEqual(args[args.index("-projection") + 1], "lambert")
        self.assertEqual(args[args.index("-longitude") + 1], "-118.3989")
        self.assertEqual(args[args.index("-searchdir") + 1], str(self.root))
        self.assertEqual(args[args.index("-config") + 1], str(self.root / "config/xp.conf"))
        self.assertEqual(args[args.index("-output") + 1],
                         str(self.root / "dev/preview/earth-render.png"))
        self.assertEqual(args[args.index("-tmpdir") + 1],
                         str(self.root / "dev/preview/tmp"))
        self.assertEqual(args[args.index("-num_times") + 1], "1")
        self.assertEqual(recorded["tmp"], str(self.root / "dev/preview/tmp"))
        self.assertEqual(recorded["cache"], str(self.root / "dev/preview/cache"))
        self.assertNotIn("-fork", args)

    def test_preview_uses_xp_def_coordinates_projection_and_fixed_geometry(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text()
                          .replace("XPLANET_LONGITUDE=-118.3989", "XPLANET_LONGITUDE=-21.91")
                          .replace("XPLANET_PROJECTION=lambert",
                                   "XPLANET_PROJECTION=orthographic\nXPLANET_LATITUDE=12.5"))
        result = self.invoke("preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text())["args"]
        self.assertEqual(args[args.index("-longitude") + 1], "-21.91")
        self.assertEqual(args[args.index("-latitude") + 1], "12.5")
        self.assertEqual(args[args.index("-projection") + 1], "orthographic")
        self.assertEqual(args[args.index("-geometry") + 1], "1920x1080")
        self.assertEqual(args[args.index("-output") + 1],
                         str(self.root / "dev/preview/earth-manual.png"))
        self.assertEqual(args[args.index("-num_times") + 1], "1")
        self.assertNotIn("-fork", args)

    def test_preview_requires_longitude_from_xp_def_before_launch(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text().replace(
            "XPLANET_LONGITUDE=-118.3989\n", ""))
        result = self.invoke("preview")
        self.assertEqual(result.returncode, 2)
        self.assertIn("xp.def XPLANET_LONGITUDE is required", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_preview_requires_projection_and_omits_unconfigured_latitude(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text().replace("XPLANET_PROJECTION=lambert\n", ""))
        result = self.invoke("preview")
        self.assertEqual(result.returncode, 2)
        self.assertIn("xp.def XPLANET_PROJECTION is required", result.stderr)
        self.assertFalse(self.capture.exists())
        config.write_text(config.read_text() + "XPLANET_PROJECTION=lambert\n")
        result = self.invoke("preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text())["args"]
        self.assertNotIn("-latitude", args)

    def test_preview_requires_project_home_and_executable_from_xp_def(self):
        config = self.root / "config/xp.def"
        original = config.read_text()
        for name, message in (("XPLANET_HOME", "must match this project root"),
                              ("XPLANET_BIN", "must be executable")):
            with self.subTest(name=name):
                config.write_text("\n".join(line for line in original.splitlines()
                                             if not line.startswith(name + "=")) + "\n")
                result = self.invoke("preview")
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertFalse(self.capture.exists())

    def test_render_and_preview_use_configured_position_with_distinct_geometry(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text()
                          .replace("XPLANET_PROJECTION=lambert", "XPLANET_PROJECTION=orthographic")
                          .replace("XPLANET_LONGITUDE=-118.3989", "XPLANET_LONGITUDE=-21.91")
                          .replace("XPLANET_GEOMETRY=1600x900",
                                   "XPLANET_LATITUDE=12.5\nXPLANET_GEOMETRY=1600x900"))
        for command, geometry in (("preview", "1920x1080"), ("render", "1600x900")):
            with self.subTest(command=command):
                self.capture.unlink(missing_ok=True)
                result = self.invoke(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(self.capture.read_text())["args"]
                for option, expected in (("-projection", "orthographic"),
                                         ("-longitude", "-21.91"),
                                         ("-latitude", "12.5"),
                                         ("-geometry", geometry)):
                    self.assertEqual(args[args.index(option) + 1], expected)
                self.assertEqual(args[args.index("-num_times") + 1], "1")

    def test_inherited_position_and_geometry_do_not_override_xp_def(self):
        inherited = {"XPLANET_PROJECTION": "mercator", "XPLANET_LONGITUDE": "99",
                     "XPLANET_LATITUDE": "44", "XPLANET_GEOMETRY": "999x999"}
        for command, geometry in (("preview", "1920x1080"), ("render", "1600x900")):
            with self.subTest(command=command):
                self.capture.unlink(missing_ok=True)
                result = self.invoke(command, inherited)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(self.capture.read_text())["args"]
                self.assertEqual(args[args.index("-projection") + 1], "lambert")
                self.assertEqual(args[args.index("-longitude") + 1], "-118.3989")
                self.assertEqual(args[args.index("-geometry") + 1], geometry)
                self.assertNotIn("-latitude", args)

    def test_missing_or_blank_position_fails_before_launch_despite_environment(self):
        config = self.root / "config/xp.def"
        original = config.read_text()
        for command in ("preview", "render"):
            for name, value in (("XPLANET_PROJECTION", "lambert"),
                                ("XPLANET_LONGITUDE", "-118.3989")):
                for replacement in ("", name + "=\n"):
                    with self.subTest(command=command, name=name,
                                      blank=bool(replacement)):
                        config.write_text(original.replace(name + "=" + value + "\n",
                                                           replacement))
                        self.capture.unlink(missing_ok=True)
                        result = self.invoke(command, {name: "inherited-value"})
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("xp.def " + name + " is required", result.stderr)
                        self.assertFalse(self.capture.exists())
        config.write_text(original)

    def test_render_requires_geometry_from_xp_def_not_environment(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text().replace("XPLANET_GEOMETRY=1600x900\n", ""))
        result = self.invoke("render", {"XPLANET_GEOMETRY": "999x999"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("xp.def XPLANET_GEOMETRY is required", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_preview_and_render_propagate_executable_exit_status(self):
        for command in ("preview", "render"):
            with self.subTest(command=command):
                self.capture.unlink(missing_ok=True)
                result = self.invoke(command, {"MOCK_EXIT": "37"})
                self.assertEqual(result.returncode, 37, result.stderr)
                self.assertTrue(self.capture.exists())

    def test_start_preserves_forked_flags_and_space_containing_paths(self):
        spaced = self.base / "project with spaces"
        self.root.rename(spaced)
        wrapper = spaced / "scripts/xplanet.sh"
        mock = spaced / "scripts/mock-xplanet"
        capture = self.base / "start-capture.json"
        (spaced / "config/xp.def").write_text(
            "XPLANET_BIN=" + shlex.quote(str(mock)) + "\n"
            "XPLANET_HOME=" + shlex.quote(str(spaced)) + "\n"
            "XPLANET_CONFIG=" + shlex.quote(str(spaced / "config")) + "\n"
            "XPLANET_PROJECTION=lambert\nXPLANET_LONGITUDE=-21.91\n"
            "XPLANET_LATITUDE=12.5\nXPLANET_GEOMETRY=1600x900+12-34\n")
        environment = {**self.environment, "MOCK_CAPTURE": str(capture)}
        result = subprocess.run([str(wrapper), "start"], cwd=self.base,
                                env=environment, capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(capture.read_text())["args"], [
            "-searchdir=" + str(spaced),
            "-config=" + str(spaced / "config/xp.conf"),
            "-projection=lambert", "-latitude", "12.5", "-longitude=-21.91",
            "-labelpos=+10-45",
            "-date_format=%D at %r", "-color=green2",
            "-geometry=1600x900+12-34", "-fork",
        ])
        self.assertFalse((spaced / "dev/preview").exists())
        failed = subprocess.run([str(wrapper), "start"], cwd=self.base,
                                env={**environment, "MOCK_EXIT": "37"},
                                capture_output=True, text=True, check=False)
        self.assertEqual(failed.returncode, 37, failed.stderr)

    def test_start_without_geometry_leaves_size_to_xplanet(self):
        config = self.root / "config/xp.def"
        original = config.read_text()
        capture = self.base / "start-capture.json"
        for replacement in ("", "XPLANET_GEOMETRY=\n"):
            with self.subTest(replacement=replacement):
                config.write_text(original.replace("XPLANET_GEOMETRY=1600x900\n",
                                                   replacement))
                result = self.invoke("start", {"XPLANET_GEOMETRY": "999x999",
                                               "MOCK_CAPTURE": str(capture)})
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(capture.read_text())["args"]
                self.assertFalse(any(arg.startswith("-geometry") for arg in args))
                self.assertNotIn("-latitude", args)
                self.assertEqual(args[-1], "-fork")

    def test_start_rejects_missing_or_other_project_config(self):
        config = self.root / "config/xp.def"
        original = config.read_text()
        for replacement in ("", "XPLANET_CONFIG=" + str(self.base) + "\n"):
            with self.subTest(replacement=replacement):
                config.write_text(original.replace(
                    "XPLANET_CONFIG=" + str(self.root / "config") + "\n",
                    replacement))
                result = self.invoke("start")
                self.assertEqual(result.returncode, 2)
                self.assertIn("XPLANET_CONFIG must match", result.stderr)
                self.assertFalse(self.capture.exists())

    def test_stop_calls_only_the_private_killall_stub(self):
        help_text = self.invoke("--help")
        self.assertEqual(help_text.returncode, 0)
        self.assertIn("render", help_text.stdout)
        self.assertIn("earth", help_text.stdout)
        self.assertIn("  start", help_text.stdout)
        self.assertIn("  stop", help_text.stdout)
        safe_bin = self.base / "stub-bin"
        safe_bin.mkdir()
        (safe_bin / "dirname").symlink_to(shutil.which("dirname"))
        killall = safe_bin / "killall"
        killall.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$@" > "$MOCK_KILLALL_TRACE"\n'
            'exit "$MOCK_KILLALL_EXIT"\n')
        killall.chmod(0o700)
        trace = self.base / "killall-args.txt"
        result = self.invoke("stop", {"PATH": str(safe_bin),
                                      "MOCK_KILLALL_TRACE": str(trace),
                                      "MOCK_KILLALL_EXIT": "37"})
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(trace.read_text(), "xplanet\n")
        self.assertFalse(self.capture.exists())

    def test_wrong_home_or_missing_geometry_fails_before_executable(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text().replace(str(self.root), str(self.base)))
        result = self.invoke("render")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must match", result.stderr)
        self.assertFalse(self.capture.exists())
        config.write_text("XPLANET_BIN=" + shlex.quote(str(self.mock)) + "\n"
                          "XPLANET_HOME=" + shlex.quote(str(self.root)) + "\n"
                          "XPLANET_PROJECTION=lambert\n"
                          "XPLANET_LONGITUDE=-118.3989\n")
        result = self.invoke("render")
        self.assertEqual(result.returncode, 2)
        self.assertIn("XPLANET_GEOMETRY", result.stderr)
        self.assertFalse(self.capture.exists())
