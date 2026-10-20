"""One CLI; all runtime writes are constrained to an explicit root."""
import argparse
import json
from .config import load
from .errors import TotalMarkerError
from .features.clouds import run
from .features.volcano import run as run_volcano
from .features.quake import run as run_quake
from .features.storm import run as run_storm
from .features.norad import run as run_norad
from .features.eclipse import run as run_eclipse
from .features.santa import run as run_santa
from .paths import RootFS


def main(argv=None):
    parser = argparse.ArgumentParser(prog="totalmarker")
    parser.add_argument("--root", required=True, help="Existing isolated project root")
    parser.add_argument("--config", help="INI or TOML path within root (never rewritten)")
    parser.add_argument("command", choices=["clouds", "labels", "quake", "storm", "volcano", "norad", "eclipse", "santa"])
    args = parser.parse_args(argv)
    try:
        fs = RootFS(args.root)
        settings = load(fs, args.config)
        if args.command == "volcano":
            result = run_volcano(fs, settings)
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "successful_at": result.successful_at,
                      "source_report_at": result.source_report_at,
                      "coverage_end_at": result.coverage_end_at,
                      "report_period_start": result.report_period_start,
                      "report_period_end": result.report_period_end,
                      "provider": result.provider, "count": result.count}
        elif args.command == "quake":
            result = run_quake(fs, settings)
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "successful_at": result.successful_at,
                      "feed_generated_at": result.feed_generated_at,
                      "latest_origin_at": result.latest_origin_at,
                      "latest_revision_at": result.latest_revision_at,
                      "count": result.count}
        elif args.command == "storm":
            result = run_storm(fs, settings)
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "successful_at": result.successful_at,
                      "source_at": result.source_at, "count": result.count}
        elif args.command == "norad":
            result = run_norad(fs, settings)
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "successful_at": result.successful_at,
                      "oldest_epoch_at": result.oldest_epoch_at,
                      "count": result.count}
        elif args.command == "eclipse":
            result = run_eclipse(fs, settings)
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "successful_at": result.successful_at,
                      "start_at": result.start_at, "end_at": result.end_at,
                      "count": result.count}
        elif args.command == "santa":
            result = run_santa(fs, settings)
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "successful_at": result.successful_at,
                      "source_at": result.source_at, "count": result.count,
                      "stale": result.stale}
        else:
            result = run(fs, settings, label_only=args.command == "labels")
            fields = {"outcome": result.outcome, "message": result.message,
                      "installed_at": result.installed_at,
                      "source_created_at": result.source_created_at}
        print(json.dumps({**fields, "deferred_settings_count": len(settings.deferred_settings)}))
        return 1 if result.outcome == "failed" else 0
    except TotalMarkerError as error:
        print(json.dumps({"outcome": "failed", "message": str(error)}))
        return 2
    except Exception:
        print(json.dumps({"outcome": "failed", "message": "Unexpected internal failure"}))
        return 2
