"""Launcher display and finite renders use fixture executables only."""
import json
import os
import pty
import select
import shlex
import sys
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
        self.assertEqual(result.stdout, "")
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
    if os.environ.get("MOCK_PGREP_ERROR") == "1":
        sys.exit(2)
    if args[:3] != ["-u", str(os.geteuid()), "-x"] or args[3:] != ["xplanet"]:
        sys.exit(4)
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
        self.assertEqual(json.loads(capture.read_text())["args"][-1], "-fork")

    def test_restart_stops_all_current_user_processes_then_starts_once(self):
        env, table, trace, capture = self.lifecycle_env()
        table.write_text(json.dumps({"101": "first", "202": "second"}))
        result = self.invoke("restart", env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(trace.read_text(), "-TERM 101\n-TERM 202\n")
        self.assertEqual(json.loads(table.read_text()), {})
        self.assertEqual(json.loads(capture.read_text())["args"][-1], "-fork")

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
        self.assertEqual(failed_start.returncode, 37, failed_start.stderr)
        self.assertTrue(capture.exists())

    def test_lifecycle_status_is_interactive_only_and_errors_use_stderr(self):
        env, table, trace, capture = self.lifecycle_env()
        started, start_output = self.invoke_tty("start", env)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("Xplanet display started.", start_output)
        table.write_text(json.dumps({"101": "first"}))
        stopped, stop_output = self.invoke_tty("stop", env)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertIn("Xplanet display stopped.", stop_output)
        restarted, restart_output = self.invoke_tty("restart", env)
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertIn("Xplanet display running.", restart_output)
        self.assertNotIn("Xplanet display stopped.", restart_output)
        self.assertTrue(capture.exists())

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
