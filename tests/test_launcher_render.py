"""Launcher display and finite renders use fixture executables only."""
import json
from pathlib import Path
import os
import pty
import select
import shlex
import sys
import shutil
import subprocess

from .support import copy_launcher, PROJECT, Sandbox, stub_desktop_launchctl


class LauncherRenderTests(Sandbox):
    def setUp(self):
        super().setUp()
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.wrapper = scripts / "xplanet.sh"
        copy_launcher(self.wrapper)
        self.desktop_bin = self.base / 'desktop-bin'
        self.desktop_bin.mkdir()
        stub_desktop_launchctl(scripts, self.desktop_bin)
        pgrep = self.desktop_bin / 'pgrep'
        pgrep.write_text('#!/bin/sh\nexit 1\n')
        pgrep.chmod(0o700)
        self.capture = self.root / "output/preview/capture.json"
        self.mock = scripts / "mock-xplanet"
        self.mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['MOCK_CAPTURE'], 'w') as output:\n"
            "    json.dump({'args': sys.argv[1:], 'tmp': os.environ.get('TMPDIR'), "
            "'cache': os.environ.get('XDG_CACHE_HOME'), 'cwd': os.getcwd()}, output)\n"
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
        self.environment = {"HOME": str(self.base), "ZDOTDIR": str(self.base), "PATH": f"{self.desktop_bin}:" + os.environ.get("PATH", "/usr/bin:/bin"),
                            "MOCK_CAPTURE": str(self.capture),
                            "PYTHONDONTWRITEBYTECODE": "1"}

    def invoke(self, command, extra_environment=None):
        environment = {**self.environment, **(extra_environment or {})}
        return subprocess.run([str(self.wrapper), command], cwd=self.base,
                              env=environment, capture_output=True, text=True,
                              check=False)

    def test_render_is_one_frame_and_all_declared_writes_are_under_output(self):
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
                         str(self.root / "output/preview/earth-render.png"))
        self.assertEqual(args[args.index("-tmpdir") + 1],
                         str(self.root / "output/preview/tmp"))
        self.assertEqual(args[args.index("-num_times") + 1], "1")
        self.assertEqual(recorded["tmp"], str(self.root / "output/preview/tmp"))
        self.assertEqual(recorded["cache"], str(self.root / "output/preview/cache"))
        self.assertNotIn("-fork", args)

    def test_preview_uses_xp_def_coordinates_projection_and_fixed_geometry(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text()
                          .replace("XPLANET_LONGITUDE=-118.3989", "XPLANET_LONGITUDE=-21.91")
                          .replace("XPLANET_PROJECTION=lambert",
                                   "XPLANET_PROJECTION=orthographic\nXPLANET_LATITUDE=12.5"))
        result = self.invoke("preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = json.loads(self.capture.read_text())
        args = recorded["args"]
        self.assertEqual(args[args.index("-tmpdir") + 1], str(self.root / "output/preview/tmp"))
        self.assertEqual(recorded["tmp"], str(self.root / "output/preview/tmp"))
        self.assertEqual(recorded["cache"], str(self.root / "output/preview/cache"))
        self.assertFalse((self.root / ".state").exists())
        self.assertEqual(args[args.index("-longitude") + 1], "-21.91")
        self.assertEqual(args[args.index("-latitude") + 1], "12.5")
        self.assertEqual(args[args.index("-projection") + 1], "orthographic")
        self.assertEqual(args[args.index("-geometry") + 1], "1920x1080")
        self.assertEqual(args[args.index("-output") + 1],
                         str(self.root / "output/preview/earth-manual.png"))
        self.assertEqual(args[args.index("-num_times") + 1], "1")
        self.assertNotIn("-fork", args)

    def test_finite_render_resource_lookup_uses_checkout_not_caller_directory(self):
        # Native Xplanet checks cwd before -searchdir. Match that behavior in this
        # fixture so a colliding caller resource cannot pass an argv-only check.
        chosen = self.root / "images/collision-map.png"
        chosen.parent.mkdir()
        chosen.write_bytes(b"selected checkout map")
        colliding = self.base / "collision-map.png"
        colliding.write_bytes(b"other checkout map")
        self.mock.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\nfrom pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "root = Path(args[args.index('-searchdir') + 1])\n"
            "candidates = [Path('collision-map.png'), root / 'images/collision-map.png']\n"
            "selected = next(path for path in candidates if path.is_file())\n"
            "Path(os.environ['MOCK_CAPTURE']).write_text(json.dumps({'cwd': os.getcwd(), "
            "'map': selected.read_text()}))\n")
        for command in ("preview", "render"):
            with self.subTest(command=command):
                result = self.invoke(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                recorded = json.loads(self.capture.read_text())
                self.assertEqual(recorded["cwd"], str(self.root))
                self.assertEqual(recorded["map"], "selected checkout map")
                self.assertEqual(colliding.read_bytes(), b"other checkout map")
                self.assertEqual(chosen.read_bytes(), b"selected checkout map")

    def test_relative_renderer_path_is_resolved_before_changing_directory(self):
        config = self.root / "config/xp.def"
        config.write_text(config.read_text().replace(
            "XPLANET_BIN=" + shlex.quote(str(self.mock)),
            "XPLANET_BIN=" + shlex.quote(str(self.mock.relative_to(self.base)))))
        for command in ("preview", "render"):
            with self.subTest(command=command):
                result = self.invoke(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(self.capture.read_text())["cwd"], str(self.root))

    def test_render_preserves_legacy_preview_exports_and_native_scenes(self):
        legacy=self.root/'dev/preview/old.png';legacy.parent.mkdir(parents=True);legacy.write_bytes(b'old preview')
        export=self.root/'output/exports/keep/preview.png';export.parent.mkdir(parents=True);export.write_bytes(b'user export')
        scene=self.root/'config/scenes/keep.conf';scene.parent.mkdir();scene.write_bytes(b'user scene')
        for command in ('preview','render'):
            result=self.invoke(command);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(legacy.read_bytes(),b'old preview');self.assertEqual(export.read_bytes(),b'user export')
        self.assertEqual(scene.read_bytes(),b'user scene')

    def test_preview_refuses_linked_directories_and_output_files(self):
        outside=self.base/'outside';outside.mkdir();sentinel=outside/'keep';sentinel.write_bytes(b'outside')
        for relative in ('output','output/preview','output/preview/tmp','output/preview/cache','output/preview/earth-manual.png'):
            with self.subTest(relative=relative):
                target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                target.symlink_to(outside if relative.rsplit('/',1)[-1]!='earth-manual.png' else sentinel)
                result=self.invoke('preview');self.assertEqual(result.returncode,2,result.stderr)
                self.assertIn('symlink',result.stderr);self.assertFalse(self.capture.exists())
                self.assertEqual(list(outside.iterdir()),[sentinel]);self.assertEqual(sentinel.read_bytes(),b'outside')
                target.unlink()
                if (self.root/'output').exists():shutil.rmtree(self.root/'output')

    def test_preview_refuses_non_directory_parent_without_overwrite(self):
        target=self.root/'output';target.write_bytes(b'user file')
        result=self.invoke('preview');self.assertEqual(result.returncode,2,result.stderr)
        self.assertEqual(target.read_bytes(),b'user file');self.assertFalse(self.capture.exists())

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

    def test_start_uses_foreground_flags_and_space_containing_paths(self):
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
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(capture.read_text())["args"], [
            "-searchdir=" + str(spaced),
            "-config=" + str(spaced / "config/xp.conf"),
            "-projection=lambert", "-latitude", "12.5", "-longitude=-21.91",
            "-labelpos=+10-45",
            "-date_format=%D at %r", "-color=green2",
            "-geometry=1600x900+12-34",
        ])
        self.assertFalse((spaced / "output/preview").exists())
        failed = subprocess.run([str(wrapper), "restart"], cwd=self.base,
                                env={**environment, "MOCK_EXIT": "37"},
                                capture_output=True, text=True, check=False)
        self.assertEqual(failed.returncode, 0, failed.stderr)  # launchd accepted the request

    def test_start_catches_up_monthly_map_even_when_display_already_running(self):
        env, table, trace, capture = self.lifecycle_env()
        (self.root / "images").mkdir()
        maps = self.root / "maps/world"
        maps.mkdir(parents=True)
        for month in (1, 6, 7):
            (maps / f"world.2004{month:02d}.3x5400x2700.png").write_bytes(b"map")
        link = self.root / "images/earth.png"
        link.symlink_to("../maps/world/world.200401.3x5400x2700.png")
        definition = self.root / "config/xp.def"
        definition.write_text(definition.read_text() + "EARTH_MAP_PRE=world/world\n")
        date = Path(env["PATH"].split(":")[0]) / "date"
        for month in (6, 7):
            date.write_text(f'#!/bin/sh\nprintf "%s\\n" "{month:02d}"\n')
            date.chmod(0o700)
            result = self.invoke("start", env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(link.readlink(), Path(f"../maps/world/world.2004{month:02d}.3x5400x2700.png"))
        self.assertFalse(trace.exists())

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
                self.assertNotIn("-fork", args)

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

    def lifecycle_env(self):
        safe_bin = self.base / "lifecycle-bin"
        safe_bin.mkdir()
        stub = "#!" + sys.executable + "\n" + """
import json
import os
from pathlib import Path
import sys
name = Path(sys.argv[0]).name
table_path = Path(os.environ["MOCK_PROCESS_TABLE"])
table = json.loads(table_path.read_text())
args = sys.argv[1:]
if name == "pgrep":
    if os.environ.get("MOCK_PGREP_TRACE"):
        with open(os.environ["MOCK_PGREP_TRACE"], "a") as out: out.write(json.dumps(args)+"\\n")
    if os.environ.get("MOCK_PGREP_ERROR") == "1":
        sys.exit(2)
    if args[:3] != ["-u", str(os.geteuid()), "-x"] :
        sys.exit(4)
    if args[3:] != ["xplanet"]: sys.exit(1)
    for pid in sorted(table):
        print(pid)
    sys.exit(0 if table else 1)
if name == "kill":
    pid = args[-1]
    if args[0] == "-0":
        sys.exit(0 if pid in table else 1)
    with open(os.environ["MOCK_KILL_TRACE"], "a") as trace:
        trace.write(" ".join(args) + "\\n")
    if os.environ.get("MOCK_KILL_EXIT") != "0":
        sys.exit(int(os.environ["MOCK_KILL_EXIT"]))
    if os.environ.get("MOCK_STAY_RUNNING") != "1":
        table.pop(pid, None)
        table_path.write_text(json.dumps(table))
    sys.exit(0)
sys.exit(4)
"""
        for name in ("pgrep", "kill"):
            binary = safe_bin / name
            binary.write_text(stub)
            binary.chmod(0o700)
        sleep = safe_bin / "sleep"
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(0o700)
        table = self.base / "processes.json"
        table.write_text("{}")
        trace = self.base / "signals.txt"
        capture = self.base / "lifecycle-capture.json"
        env = {
            "PATH": f"{safe_bin}:{self.environment['PATH']}",
            "MOCK_CAPTURE": str(capture),
            "MOCK_PROCESS_TABLE": str(table),
            "MOCK_KILL_TRACE": str(trace),
            "MOCK_KILL_EXIT": "0",
            "MOCK_STAY_RUNNING": "0",
        }
        return env, table, trace, capture

    def invoke_tty(self, command, env):
        master, slave = pty.openpty()
        try:
            result = subprocess.run([str(self.wrapper), command],
                                    cwd=self.base, env={**self.environment, **env},
                                    stdout=slave, stderr=subprocess.PIPE,
                                    text=True, timeout=5)
            ready, _, _ = select.select([master], [], [], 1)
            output = os.read(master, 4096).decode() if ready else ""
            return result, output
        finally:
            os.close(slave)
            os.close(master)

    def test_stop_signals_all_current_user_xplanet_processes(self):
        env, table, trace, capture = self.lifecycle_env()
        table.write_text(json.dumps({"101": "first", "202": "second", "303": "third"}))
        stopped = self.invoke("stop", env)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(stopped.stdout, "")
        self.assertEqual(trace.read_text(), "-TERM 101\n-TERM 202\n-TERM 303\n")
        self.assertEqual(json.loads(table.read_text()), {})
        self.assertFalse(capture.exists())

    def test_stop_and_restart_when_not_running(self):
        env, table, trace, capture = self.lifecycle_env()
        stopped = self.invoke("stop", env)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(stopped.stdout, "")
        self.assertFalse(trace.exists())
        restarted = self.invoke("restart", env)
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertFalse(trace.exists())
        self.assertNotIn("-fork", json.loads(capture.read_text())["args"])

    def test_restart_stops_desktop_preview_and_other_checkout(self):
        env, table, trace, capture = self.lifecycle_env()
        table.write_text(json.dumps({"101": "desktop", "202": "preview", "303": "other"}))
        result = self.invoke("restart", env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(trace.read_text(), "-TERM 101\n-TERM 202\n-TERM 303\n")
        self.assertEqual(json.loads(table.read_text()), {"909": "desktop"})
        self.assertNotIn("-fork", json.loads(capture.read_text())["args"])

    def test_stop_failure_or_process_inspection_error_prevents_restart(self):
        env, table, trace, capture = self.lifecycle_env()
        table.write_text(json.dumps({"101": "first"}))
        denied = self.invoke("restart", {**env, "MOCK_KILL_EXIT": "37"})
        self.assertEqual(denied.returncode, 2)
        self.assertIn("could not stop", denied.stderr)
        self.assertFalse(capture.exists())
        self.assertEqual(json.loads(table.read_text()), {"101": "first"})
        unknown = self.invoke("restart", {**env, "MOCK_PGREP_ERROR": "1"})
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("could not inspect", unknown.stderr)
        self.assertFalse(capture.exists())

    def test_lingering_process_blocks_restart_and_start_error_propagates(self):
        env, table, trace, capture = self.lifecycle_env()
        table.write_text(json.dumps({"101": "first"}))
        lingering = self.invoke("restart", {**env, "MOCK_STAY_RUNNING": "1"})
        self.assertEqual(lingering.returncode, 2)
        self.assertIn("still running after stop", lingering.stderr)
        self.assertFalse(capture.exists())
        table.write_text("{}")
        failed_start = self.invoke("restart", {**env, "MOCK_EXIT": "37"})
        self.assertEqual(failed_start.returncode, 0, failed_start.stderr)
        self.assertTrue(capture.exists())

    def test_lifecycle_status_is_interactive_only_and_errors_use_stderr(self):
        env, table, trace, capture = self.lifecycle_env()
        started, start_output = self.invoke_tty("start", env)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("Xplanet desktop start requested; launchd accepted the request.", start_output)
        table.write_text(json.dumps({"101": "first"}))
        stopped, stop_output = self.invoke_tty("stop", env)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertIn("Xplanet display stopped.", stop_output)
        restarted, restart_output = self.invoke_tty("restart", env)
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertIn("Xplanet desktop start requested; launchd accepted the request.", restart_output)
        self.assertNotIn("Xplanet display stopped.", restart_output)
        self.assertTrue(capture.exists())

    def test_start_twice_uses_one_foreground_job_without_python_runtime(self):
        import plistlib
        env, table, trace, capture = self.lifecycle_env()
        env['TOTALMARKER_PYTHON'] = '/missing/python'
        first = self.invoke('start', env)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = capture.stat().st_mtime_ns
        second = self.invoke('start', env)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(capture.stat().st_mtime_ns, before)
        doc = plistlib.loads((self.base / 'Library/LaunchAgents/local.xplanet.desktop.plist').read_bytes())
        self.assertNotIn('KeepAlive', doc)
        self.assertNotIn('RunAtLoad', doc)
        self.assertEqual(doc['ProgramArguments'], ['/bin/zsh', str(self.root / 'scripts/lib/xplanet/desktop.zsh')])
        self.assertNotIn('-fork', json.loads(capture.read_text())['args'])

    def test_unmanaged_migration_requires_explicit_restart(self):
        env, table, trace, capture = self.lifecycle_env()
        table.write_text(json.dumps({'101':'legacy', '202':'finite'}))
        result = self.invoke('start', env)
        self.assertEqual(result.returncode, 2)
        self.assertIn('use restart', result.stderr)
        self.assertFalse(trace.exists())
        self.assertFalse(capture.exists())
        restarted = self.invoke('restart', env)
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertEqual(trace.read_text(), '-TERM 101\n-TERM 202\n')
        self.assertEqual(json.loads(table.read_text()), {'909':'desktop'})

    def test_stop_removes_job_and_no_restart_occurs(self):
        env, table, trace, capture = self.lifecycle_env()
        calls = self.base / 'launchctl-calls'
        env['MOCK_LAUNCHCTL_TRACE'] = str(calls)
        self.assertEqual(self.invoke('start', env).returncode, 0)
        result = self.invoke('stop', env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(table.read_text()), {})
        before = calls.read_text()
        self.assertIn('bootout gui/', before)
        self.assertEqual(self.invoke('stop', env).returncode, 0)
        self.assertEqual(calls.read_text().count('kickstart '), 1)
        self.assertEqual(json.loads(table.read_text()), {})

    def test_failed_bootout_still_stops_all_processes_and_prevents_restart(self):
        env, table, trace, capture = self.lifecycle_env()
        self.assertEqual(self.invoke('start', env).returncode, 0)
        result = self.invoke('restart', {**env, 'MOCK_BOOTOUT_FAIL':'1'})
        self.assertEqual(result.returncode, 2)
        self.assertIn('desktop job removal failed', result.stderr)
        self.assertEqual(trace.read_text(), '-TERM 909\n')
        self.assertEqual(json.loads(table.read_text()), {})

    def test_configured_names_are_literal_and_symlink_execution_resolves(self):
        env, table, trace, capture = self.lifecycle_env()
        alias = self.root / 'a-long-symlink.with+regex-characters'
        alias.symlink_to(self.mock)
        definition = self.root / 'config/xp.def'
        definition.write_text(definition.read_text().replace(str(self.mock), str(alias)))
        probes = self.base / 'name-probes'
        env['MOCK_PGREP_TRACE'] = str(probes)
        result = self.invoke('start', env)
        self.assertEqual(result.returncode, 0, result.stderr)
        import plistlib
        self.assertEqual(self.invoke('stop', env).returncode, 0)
        patterns = [json.loads(line)[-1] for line in probes.read_text().splitlines()]
        self.assertIn('a-long-symlink\\.with\\+regex-characters', patterns)
        self.assertTrue(capture.exists())
        self.assertNotIn('-fork', json.loads(capture.read_text())['args'])

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
