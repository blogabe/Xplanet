"""Public CLI JSON and status contract; product execution is stubbed offline."""
import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from totalmarker.cli import main
from totalmarker.errors import ConfigError
from totalmarker.features.clouds import Result as CloudResult
from totalmarker.features.eclipse import Result as EclipseResult
from totalmarker.features.norad import Result as NoradResult
from totalmarker.features.quake import Result as QuakeResult
from totalmarker.features.santa import Result as SantaResult
from totalmarker.features.storm import Result as StormResult
from totalmarker.features.volcano import Result as VolcanoResult

from .support import Sandbox


CASES = (
    ("clouds", "run", CloudResult("changed", "cloud ready", 11.25, None),
     {"outcome": "changed", "message": "cloud ready", "installed_at": 11.25,
      "source_created_at": None}),
    ("labels", "run", CloudResult("unchanged", "labels aged", None, 12.5),
     {"outcome": "unchanged", "message": "labels aged", "installed_at": None,
      "source_created_at": 12.5}),
    ("quake", "run_quake", QuakeResult("changed", "quake ready", 1.0, 2.0,
                                        None, 3.0, 4.0, 5),
     {"outcome": "changed", "message": "quake ready", "installed_at": 1.0,
      "successful_at": 2.0, "feed_generated_at": None,
      "latest_origin_at": 3.0, "latest_revision_at": 4.0, "count": 5}),
    ("storm", "run_storm", StormResult("unchanged", "storm ready", 1.0, 2.0,
                                        3.0, 0),
     {"outcome": "unchanged", "message": "storm ready", "installed_at": 1.0,
      "successful_at": 2.0, "source_at": 3.0, "count": 0}),
    ("volcano", "run_volcano", VolcanoResult("changed", "volcano ready", 1.0,
                                              2.0, None, 3, 4.0,
                                              "2026-10-01", "2026-10-07",
                                              "weekly_html"),
     {"outcome": "changed", "message": "volcano ready", "installed_at": 1.0,
      "successful_at": 2.0, "source_report_at": None,
      "coverage_end_at": 4.0, "report_period_start": "2026-10-01",
      "report_period_end": "2026-10-07", "provider": "weekly_html", "count": 3}),
    ("norad", "run_norad", NoradResult("unchanged", "norad ready", None, 2.0,
                                        None, 0),
     {"outcome": "unchanged", "message": "norad ready", "installed_at": None,
      "successful_at": 2.0, "oldest_epoch_at": None, "count": 0}),
    ("eclipse", "run_eclipse", EclipseResult("changed", "eclipse ready", 1.0,
                                              2.0, 3.0, 4.0, 6),
     {"outcome": "changed", "message": "eclipse ready", "installed_at": 1.0,
      "successful_at": 2.0, "start_at": 3.0, "end_at": 4.0, "count": 6}),
    ("santa", "run_santa", SantaResult("disabled", "santa disabled", None,
                                        None, None, 0, False),
     {"outcome": "disabled", "message": "santa disabled",
      "installed_at": None, "successful_at": None, "source_at": None,
      "count": 0, "stale": False}),
)


class CliContractTests(Sandbox):
    def assert_json_contract(self, actual, expected):
        # These results are flat JSON objects; value equality alone accepts
        # False == 0 and 1.0 == 1 in Python.
        self.assertIs(type(actual), dict)
        self.assertEqual(set(actual), set(expected))
        for key, value in expected.items():
            self.assertIs(type(actual[key]), type(value), key)
            self.assertEqual(actual[key], value, key)

    def invoke(self, command, runner, result):
        output = io.StringIO()
        settings = SimpleNamespace(deferred_settings=("first", "second"))
        with (patch("totalmarker.cli.load", return_value=settings),
              patch("totalmarker.cli." + runner, return_value=result) as product,
              redirect_stdout(output)):
            status = main(["--root", str(self.root), command])
        self.assertEqual(product.call_count, 1)
        if command in {"clouds", "labels"}:
            self.assertEqual(product.call_args.kwargs,
                             {"label_only": command == "labels"})
        return status, json.loads(output.getvalue())

    def test_all_commands_return_exact_fields_nulls_and_statuses(self):
        for command, runner, example, fields in CASES:
            for outcome in ("changed", "unchanged", "failed"):
                message = "provider unavailable" if outcome == "failed" else example.message
                with self.subTest(command=command, outcome=outcome):
                    status, actual = self.invoke(
                        command, runner, replace(example, outcome=outcome,
                                                 message=message))
                    self.assertEqual(status, 1 if outcome == "failed" else 0)
                    self.assert_json_contract(actual, {**fields, "outcome": outcome,
                                              "message": message,
                                              "deferred_settings_count": 2})

    def test_disabled_optional_products_still_return_complete_result(self):
        for command, runner, example, fields in CASES:
            if command not in {"norad", "eclipse", "santa"}:
                continue
            with self.subTest(command=command):
                status, actual = self.invoke(
                    command, runner, replace(example, outcome="disabled",
                                              message="disabled in config"))
                self.assertEqual(status, 0)
                self.assert_json_contract(actual, {**fields, "outcome": "disabled",
                                          "message": "disabled in config",
                                          "deferred_settings_count": 2})

    def test_type_check_rejects_values_that_compare_equal(self):
        for actual, expected in (({"stale": 0}, {"stale": False}),
                                 ({"count": False}, {"count": 0}),
                                 ({"installed_at": 1}, {"installed_at": 1.0}),
                                 ({"source_at": ""}, {"source_at": None})):
            with self.subTest(actual=actual, expected=expected):
                with self.assertRaises(AssertionError):
                    self.assert_json_contract(actual, expected)

    def test_config_and_internal_errors_keep_distinct_status_two_json(self):
        output = io.StringIO()
        with (patch("totalmarker.cli.load", side_effect=ConfigError("bad config")),
              redirect_stdout(output)):
            status = main(["--root", str(self.root), "clouds"])
        self.assertEqual(status, 2)
        self.assert_json_contract(json.loads(output.getvalue()),
                         {"outcome": "failed", "message": "bad config"})

        output = io.StringIO()
        with (patch("totalmarker.cli.load", return_value=SimpleNamespace(
                  deferred_settings=())),
              patch("totalmarker.cli.run", side_effect=RuntimeError("sensitive")),
              redirect_stdout(output)):
            status = main(["--root", str(self.root), "clouds"])
        self.assertEqual(status, 2)
        self.assert_json_contract(json.loads(output.getvalue()),
                         {"outcome": "failed", "message": "Unexpected internal failure"})
