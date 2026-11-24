"""Examples ship separately from the guided setup automation bundle."""
import plistlib
import unittest

from .support import PROJECT


class OptionalLaunchAgentExamplesTests(unittest.TestCase):
    def test_manual_templates_run_only_the_expected_producer_on_local_schedule(self):
        schedules = {
            "norad": [(hour, 40) for hour in range(0, 24, 3)],
            "eclipse": [(6, 15), (18, 15)],
        }
        root = "__XPLANET_ROOT__"
        for product, times in schedules.items():
            with self.subTest(product=product):
                label = f"local.xplanet.{product}"
                path = PROJECT / "scripts/launchd" / f"{label}.plist.example"
                self.assertEqual(plistlib.loads(path.read_bytes()), {
                    "Label": label,
                    "WorkingDirectory": root,
                    "ProgramArguments": [f"{root}/scripts/xplanet.sh", product],
                    "StartCalendarInterval": [
                        {"Hour": hour, "Minute": minute} for hour, minute in times
                    ],
                    "StandardOutPath": f"{root}/logs/xplanet.log",
                    "StandardErrorPath": f"{root}/logs/xplanet-{product}.log",
                })
