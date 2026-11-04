"""One CLI; all runtime writes are constrained to an explicit root."""
import argparse
from dataclasses import asdict
import json
import os
import sys
from .config import load
from .health import check as check_health, exit_status as health_status, format_report, format_dashboard
from .errors import TotalMarkerError
from .features.clouds import run
from .features.volcano import run as run_volcano
from .features.quake import run as run_quake
from .features.storm import run as run_storm
from .features.norad import run as run_norad
from .features.eclipse import run as run_eclipse
from .features.santa import run as run_santa
from .paths import RootFS
from .log_trim import trim as trim_log


def main(argv=None):
    parser = argparse.ArgumentParser(prog="totalmarker")
    parser.add_argument("--root", required=True, help="Existing isolated project root")
    parser.add_argument("--config", help="INI or TOML path within root (never rewritten)")
    parser.add_argument("command", choices=["clouds", "labels", "quake", "storm", "volcano", "norad", "eclipse", "santa", "health", "log-trim"])
    parser.add_argument("--live", action="store_true", help="Health: validate sources in a temporary root")
    parser.add_argument("--json", action="store_true", help="Health: output structured JSON")
    parser.add_argument("--verbose", action="store_true", help="Health: include source and diagnostic details")
    parser.add_argument("--dashboard", action="store_true", help="Health: compact saved-status records for management")
    parser.add_argument("--days", type=int, help="Log trim: retain this many days (default 30)")
    parser.add_argument("--dry-run", action="store_true", help="Log trim: report without writing")
    args = parser.parse_args(argv)
    if args.command != "log-trim" and (args.days is not None or args.dry_run):
        parser.error("--days and --dry-run are log-trim options")
    if args.days is not None and args.days < 1:
        parser.error("--days must be a positive integer")
    if args.dashboard and (args.live or args.json or args.verbose):
        parser.error("--dashboard requires saved health without --live, --json or --verbose")
    if args.command != "health" and (args.live or args.json or args.verbose or args.dashboard):
        parser.error("--live, --json, --verbose and --dashboard are health options")
    try:
        fs = RootFS(args.root)
        settings = load(fs, args.config)
        if args.command == "log-trim":
            result = trim_log(fs, settings, days=args.days or 30, dry_run=args.dry_run)
            print(json.dumps(result))
            return 0
        if args.command == "health":
            report = check_health(fs, settings, live=args.live)
            color = (sys.stdout.isatty() and 'NO_COLOR' not in os.environ
                     and os.environ.get('TERM', '') not in {'', 'dumb'})
            print(format_dashboard(report) if args.dashboard else json.dumps(report) if args.json else format_report(
                report, verbose=args.verbose, color=color))
            return health_status(report)
        if args.command == "volcano":
            result = run_volcano(fs, settings)
        elif args.command == "quake":
            result = run_quake(fs, settings)
        elif args.command == "storm":
            result = run_storm(fs, settings)
        elif args.command == "norad":
            result = run_norad(fs, settings)
        elif args.command == "eclipse":
            result = run_eclipse(fs, settings)
        elif args.command == "santa":
            result = run_santa(fs, settings)
        else:
            result = run(fs, settings, label_only=args.command == "labels")
        fields = asdict(result)
        print(json.dumps({**fields, "deferred_settings_count": len(settings.deferred_settings)}))
        return 1 if result.outcome == "failed" else 0
    except TotalMarkerError as error:
        print(json.dumps({"outcome": "failed", "message": str(error)}))
        return 2
    except Exception:
        print(json.dumps({"outcome": "failed", "message": "Unexpected internal failure"}))
        return 2
