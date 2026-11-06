"""Independent terminal entrypoint; renderer discovery never executes xp.def."""
import argparse
from pathlib import Path
import sys


def report_result(result):
    """Keep save and scene-selection outcomes independent, including uncertainty."""
    label=None
    if result and result[0] in ('saved','kept','draft'):
        label=result[2] if len(result)>2 else None
        if result[0]=='draft':print(f'Private recovery draft retained at {result[1]}; no native scene saved on exit. Nothing activated.')
        elif result[0]=='kept':print(f'Last saved view remains at {result[1]}; no additional save was made on exit.')
        else:print(f'View saved to {result[1]}; '+('no desktop restart occurred.' if label is not None else 'desktop settings were not changed.'))
    elif result and result[0]=='selected':label=result[1]
    else:
        print('Configurator cancelled; no desktop settings were changed.')
        return 3
    if label=='uncertain':
        print('Scene selection outcome uncertain; inspect config/desktop.scene before retrying. No renderer or jobs started.')
        return 5
    if label is not None:print('Desktop scene selection: '+label+'. Restart explicitly when ready; no renderer or jobs started.')
    return 0


def main():
    parser = argparse.ArgumentParser(description='Explore Earth, planets and supported moons; save native files without automatic activation.',epilog='In-app Help: F1. Full manual: --guide or scripts/xplanet.sh config --guide. See docs/configurator/user-guide.md.')
    parser.add_argument('--guide',action='store_true',help='Print the bundled user guide without opening the UI')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--renderer', help='Explicit local Xplanet executable; otherwise use literal project setting, PATH or standard Homebrew locations')
    parser.add_argument('--view', type=Path, help='Reopen a generated named .conf/.def or legacy scene directory as a snapshot.')
    args = parser.parse_args()
    if args.guide:
        from .guide import read_guide
        try:print(read_guide(),end='');return 0
        except (OSError,ValueError,UnicodeError) as exc:print('Guide unavailable: '+str(exc),file=sys.stderr);return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error('The configurator requires an interactive terminal.')
    from .app import ConfiguratorApp
    from .display_geometry import detect
    from .workspace import Workspace, open_view
    try:
        document = open_view(args.view) if args.view is not None else None
    except (ValueError, OSError) as exc:
        print(f'Cannot open view: {exc}', file=sys.stderr)
        return 2
    from .renderer_discovery import discover
    renderer, renderer_note = discover(args.root.resolve(), args.renderer)
    workspace = Workspace()
    app=None
    try:
        app=ConfiguratorApp(args.root.resolve(),renderer,workspace,document=document,display=detect(),renderer_note=renderer_note)
        result=app.run()
        code=report_result(result)
        if app.recovery_notice:print(app.recovery_notice)
        return code if code==5 or app.termination_signal is None else 128+app.termination_signal
    finally:
        if app is not None and app.recovery:app.recovery.close()
        workspace.close()
        if app is not None and getattr(app,'exchange_notice',''):print(app.exchange_notice)


if __name__ == '__main__':
    sys.exit(main())
