"""One CLI; all runtime writes are constrained to an explicit root."""
import argparse
from dataclasses import asdict
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
