"""Explicit stdlib-only review and selection commands; never restart services."""
import argparse,json,sys
from pathlib import Path
from .handoff import create_plan,stage_plan,check_bundle
from .fileio import native_error
from .selection import inspect_selection,apply_bundle,select_revision,read_revision,UncertainSelection


def main():
    parser=argparse.ArgumentParser(description='Review/export or explicitly select a scene revision; no renderer or service actions.')
    parser.add_argument('--root',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--export-handoff',type=Path,metavar='NEW_DIRECTORY')
    mode.add_argument('--check-handoff',type=Path,metavar='DIRECTORY')
    mode.add_argument('--apply-handoff',type=Path,metavar='DIRECTORY')
    mode.add_argument('--select-revision',metavar='REVISION_ID')
    mode.add_argument('--use-legacy',action='store_true',help='Return next start to custom xp.def/xp.conf (compatibility option name).')
    mode.add_argument('--show-selection',action='store_true')
    parser.add_argument('--expect-selected',metavar='legacy_OR_REVISION_ID')
    parser.add_argument('--view',type=Path)
    parser.add_argument('--renderer')
    parser.add_argument('--geometry')
    args=parser.parse_args()
    try:
        changing=args.apply_handoff is not None or args.select_revision is not None or args.use_legacy
        if changing or args.show_selection:
            if args.view or args.renderer or args.geometry:parser.error('Selection uses the reviewed bundle/revision; no scene overrides accepted.')
            before=inspect_selection(args.root)
            if changing:
                if args.expect_selected is None:parser.error('Selection requires --expect-selected legacy or the current revision ID.')
                if before.label!=args.expect_selected:raise ValueError('Selection differs from --expect-selected; inspect and review again.')
                receipt=apply_bundle(args.root,args.apply_handoff,before) if args.apply_handoff else select_revision(args.root,None if args.use_legacy else args.select_revision,before)
                print('Desktop selection: '+receipt.after.label+'. No restart, renderer, provider or job action occurred.')
                print('Previous selection: '+receipt.before.label+'. Retained revisions can be explicitly selected again; no automatic rollback.')
            else:
                if args.expect_selected is not None:parser.error('--expect-selected is only for a selection change.')
                if before.revision:
                    record=read_revision(args.root,before.revision)
                    print('Native scene: '+record['scene']+'; desktop geometry: '+record['geometry']+'; renderer: '+record['renderer']['path'])
                print('Desktop selection: '+before.label+'. For next explicit start/restart; running state not inspected. No files or jobs changed.')
            return 0
        if args.expect_selected is not None:parser.error('--expect-selected is only for a selection change.')
        if args.export_handoff:
            if args.view is None or not args.renderer or not args.geometry:parser.error('Export requires --view, --renderer and explicit --geometry.')
            plan=create_plan(args.root,args.view,args.renderer,args.geometry)
            target=stage_plan(plan,args.export_handoff);record=check_bundle(args.root,target)
            print('Review-only handoff exported to '+str(target)+'. No selection, setup, restart or desktop change occurred.')
        else:
            if args.view or args.renderer or args.geometry:parser.error('Check uses the exported plan; no override options are accepted.')
            record=check_bundle(args.root,args.check_handoff)
            print('Review-only handoff verified. No scene selected, setup or job changes occurred.')
        print(json.dumps({'id':record['id'],'scene':record['scene'],'geometry':record['geometry'],'activation_ready':False,'unbound_stock_lookups':record['unbound_stock_lookups']},indent=2))
        return 0
    except UncertainSelection as exc:
        print('Selection outcome uncertain: '+str(exc),file=sys.stderr)
        for note in getattr(exc,'__notes__',()):print(note,file=sys.stderr)
        return 5
    except (ValueError,OSError) as exc:
        print('Handoff refused: '+native_error(exc),file=sys.stderr)
        for note in getattr(exc,'__notes__',()):print(note,file=sys.stderr)
        return 2
    except KeyboardInterrupt as exc:
        print('Handoff interrupted. Inspect the selection before retrying; no automatic rollback was attempted.',file=sys.stderr)
        for note in getattr(exc,'__notes__',()):print(note,file=sys.stderr)
        return 130


if __name__=='__main__':sys.exit(main())
