"""Shell launchd preparation touches only isolated project and HOME fixtures."""
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

from .support import PROJECT, Sandbox


class LaunchdSetupTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.home = self.base / "home with spaces"
        self.home.mkdir()
        scripts = self.root / "scripts"
        self.source = scripts / "launchd"
        self.source.mkdir(parents=True)
        launcher = scripts / "xplanet.sh"
        launcher.write_text("#!/bin/zsh\n")
        launcher.chmod(0o700)
        shutil.copy2(PROJECT / "scripts/xp-setup.sh", scripts / "xp-setup.sh")
        (self.root / "logs").mkdir()
        (self.root / "images").mkdir()
        for source in (PROJECT / "scripts/launchd").glob("*.plist.example"):
            shutil.copy2(source, self.source / source.name)
        self.agents = self.home / "Library/LaunchAgents"

    def prepare(self, *, clouds=False, home=None):
        command = [str(self.root / "scripts/xp-setup.sh"), "--prepare-launchd", "--home",
                   str(self.home if home is None else home), "--python", sys.executable]
        if clouds:
            command.append("--include-clouds")
        return subprocess.run(command, cwd=PROJECT, capture_output=True,
                              text=True, check=False)

    def test_rendered_jobs_have_absolute_paths_and_repeat_without_overwrite(self):
        first = self.prepare(clouds=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("12 new entries", first.stdout)
        self.assertIn("0 new entries", self.prepare(clouds=True).stdout)
        for job in ("start", "earth-map", "quake", "storm", "volcano", "clouds"):
            with self.subTest(job=job):
                local = self.source / f"local.xplanet.{job}.plist"
                document = plistlib.loads(local.read_bytes())
                working = self.root / "images" if job == "earth-map" else self.root
                self.assertEqual(document["WorkingDirectory"], str(working))
                self.assertEqual(document["ProgramArguments"], [
                    str(self.root / "scripts/xplanet.sh"),
                    "earth" if job == "earth-map" else job])
                self.assertEqual(document["EnvironmentVariables"]["TOTALMARKER_PYTHON"],
                                 sys.executable)
                for key in ("StandardOutPath", "StandardErrorPath"):
                    self.assertEqual(Path(document[key]).parent, self.root / "logs")
                self.assertEqual((self.agents / local.name).readlink(), local)

    def test_personal_schedule_is_preserved_and_clouds_remain_optional(self):
        self.assertEqual(self.prepare().returncode, 0)
        local = self.source / "local.xplanet.quake.plist"
        document = plistlib.loads(local.read_bytes())
        document["StartCalendarInterval"] = [{"Minute": 7}]
        personalized = plistlib.dumps(document)
        local.write_bytes(personalized)
        self.assertEqual(self.prepare().returncode, 0)
        self.assertEqual(local.read_bytes(), personalized)
        self.assertFalse((self.source / "local.xplanet.clouds.plist").exists())

    def test_existing_relative_jobs_without_python_override_are_preserved(self):
        spaced_root = self.base / "project with spaces"
        self.root.rename(spaced_root)
        self.root = spaced_root
        self.source = self.root / "scripts/launchd"
        original = {}
        for job in ("start", "earth-map", "quake", "storm", "volcano", "clouds"):
            path = self.source / f"local.xplanet.{job}.plist"
            document = plistlib.loads((self.source / (path.name + ".example")).read_bytes())
            document["WorkingDirectory"] = str(self.root / "images" if job == "earth-map"
                                                else self.root)
            document["StartCalendarInterval"] = [{"Minute": 13}]
            document.pop("EnvironmentVariables", None)
            original[path] = plistlib.dumps(document)
            path.write_bytes(original[path])
        first = self.prepare(clouds=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("6 new entries", first.stdout)
        self.assertIn("0 new entries", self.prepare(clouds=True).stdout)
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual((self.agents / path.name).readlink(), path)

    def test_relative_paths_must_resolve_inside_expected_root(self):
        self.assertEqual(self.prepare().returncode, 0)
        local = self.source / "local.xplanet.start.plist"
        baseline = plistlib.loads(local.read_bytes())
        (self.root / "xplanet.sh").symlink_to("scripts/xplanet.sh")
        for field, value, error in (
            ("WorkingDirectory", str(self.base), "WorkingDirectory"),
            ("ProgramArguments", ["../../outside.sh", "start"], "ProgramArguments.0"),
            ("ProgramArguments", ["xplanet.sh", "start"], "ProgramArguments.0"),
            ("StandardOutPath", "../outside.log", "log path"),
        ):
            with self.subTest(field=field):
                document = dict(baseline)
                document[field] = value
                changed = plistlib.dumps(document)
                local.write_bytes(changed)
                result = self.prepare()
                self.assertEqual(result.returncode, 2)
                self.assertIn(error, result.stderr)
                self.assertEqual(local.read_bytes(), changed)
        local.write_bytes(plistlib.dumps(baseline))

    def test_explicit_python_override_can_differ_but_must_be_supported(self):
        self.assertEqual(self.prepare().returncode, 0)
        local = self.source / "local.xplanet.start.plist"
        baseline = plistlib.loads(local.read_bytes())
        alternative = self.root / "another supported python"
        alternative.symlink_to(sys.executable)
        document = dict(baseline)
        document["EnvironmentVariables"] = {"TOTALMARKER_PYTHON": str(alternative)}
        valid = plistlib.dumps(document)
        local.write_bytes(valid)
        self.assertEqual(self.prepare().returncode, 0)
        self.assertEqual(local.read_bytes(), valid)
        for invalid in ("python3", str(self.root / "missing-python")):
            with self.subTest(invalid=invalid):
                document["EnvironmentVariables"] = {"TOTALMARKER_PYTHON": invalid}
                changed = plistlib.dumps(document)
                local.write_bytes(changed)
                result = self.prepare()
                self.assertEqual(result.returncode, 2)
                self.assertIn("TOTALMARKER_PYTHON", result.stderr)
                self.assertEqual(local.read_bytes(), changed)

    def test_existing_local_or_agent_conflict_refuses_before_writes(self):
        local = self.source / "local.xplanet.start.plist"
        local.write_bytes(b"personal plist")
        result = self.prepare()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid launchd plist", result.stderr)
        self.assertEqual(local.read_bytes(), b"personal plist")
        self.assertFalse(self.agents.exists())
        local.unlink()
        self.agents.mkdir(parents=True)
        agent = self.agents / local.name
        agent.write_bytes(b"personal agent")
        result = self.prepare()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Existing LaunchAgent", result.stderr)
        self.assertEqual(agent.read_bytes(), b"personal agent")
        self.assertFalse(local.exists())

    def test_symlinked_parent_home_and_log_are_refused(self):
        scripts = self.root / "scripts"
        sibling = self.base / "sibling-scripts"
        scripts.rename(sibling)
        scripts.symlink_to(sibling)
        self.assertIn("real directory", self.prepare().stderr)
        self.assertFalse((sibling / "launchd/local.xplanet.start.plist").exists())
        scripts.unlink()
        sibling.rename(scripts)
        alias = self.base / "home-alias"
        alias.symlink_to(self.home)
        self.assertIn("symlink ancestors", self.prepare(home=alias).stderr)
        self.assertFalse(self.agents.exists())
        external_log = self.base / "external.log"
        external_log.write_text("personal log")
        (self.root / "logs/xplanet.log").symlink_to(external_log)
        result = self.prepare()
        self.assertEqual(result.returncode, 2)
        self.assertIn("log path", result.stderr)
        self.assertEqual(external_log.read_text(), "personal log")
        self.assertFalse(self.agents.exists())

    def test_program_overrides_and_old_local_paths_are_refused(self):
        example = self.source / "local.xplanet.start.plist.example"
        document = plistlib.loads(example.read_bytes())
        document["Program"] = "/bin/false"
        example.write_bytes(plistlib.dumps(document))
        self.assertIn("Program override", self.prepare().stderr)
        self.assertFalse((self.source / "local.xplanet.start.plist").exists())
        del document["Program"]
        example.write_bytes(plistlib.dumps(document))
        self.assertEqual(self.prepare().returncode, 0)
        local = self.source / "local.xplanet.start.plist"
        document = plistlib.loads(local.read_bytes())
        document["Program"] = "/bin/false"
        local.write_bytes(plistlib.dumps(document))
        result = self.prepare()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Review local launchd Program override", result.stderr)

    def test_symlinked_launchagents_directory_is_refused_before_writes(self):
        outside = self.base / "outside-agents"
        outside.mkdir()
        self.agents.parent.mkdir()
        self.agents.symlink_to(outside)
        result = self.prepare()
        self.assertEqual(result.returncode, 2)
        self.assertIn("real directory", result.stderr)
        self.assertEqual(tuple(outside.iterdir()), ())
        self.assertFalse((self.source / "local.xplanet.start.plist").exists())
