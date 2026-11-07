"""Relevant scene diagnostics never guess an installed tree or certify data."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import io
import os
import tempfile
import unittest
from unittest import mock

from configurator.model import View
from configurator.resource_diagnostics import describe, requests, _metadata, REPORT_LIMIT, MAX_REQUESTS
from configurator.resources import resource_evidence


class RelevantResourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root/'project'; self.project.mkdir()
        self.work = self.root/'preview'; self.work.mkdir()

    def report(self, view=None, rows=(), **kwargs):
        return describe(view or View(), rows, self.work, self.project, **kwargs)

    def test_lunar_orbital_origin_is_a_scene_owned_diagnostic_request(self):
        view = replace(View(), projection='space', observer='moon', camera_mode='lunar_orbit', time_mode='fixed')
        selected, limited = requests(view)
        self.assertFalse(limited)
        origin = next(request for request in selected if request.name == 'camera.origin')
        self.assertEqual((origin.role, origin.source), ('observer path', 'scene'))
        report = self.report(view)
        self.assertIn('observer path: camera.origin', report)
        self.assertIn(str(self.work/'camera.origin')+' [missing]', report)
        (self.work/'camera.origin').write_bytes(view.origin_data())
        report = self.report(view, ((str(self.work/'camera.origin'), True),))
        self.assertIn(str(self.work/'camera.origin')+' [regular file present]', report)
        self.assertNotIn('Possible shadowing', report)
        report = self.report(view, (('/other/camera.origin', True),))
        self.assertIn('Possible shadowing/path mismatch', report)

    def test_imported_annotations_are_scene_owned_requests_only_when_active(self):
        from configurator.installed_annotations import DATASETS, import_datasets
        from tests.configurator.support_installed_annotations import SOURCES
        source = self.root/'installed'
        for key, text in SOURCES.items():
            path = source/DATASETS[key][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        data = import_datasets(source, DATASETS)
        fields = {field: value for key, text in data.items()
                  for field, value in ((key, 'on'), (key+'_text', text))}
        view = replace(View(), target='moon', projection='space', **fields)
        for name, payload in view.auxiliary_files(active_only=True).items():
            (self.work/name).write_bytes(payload)
        selected, limited = requests(view)
        self.assertFalse(limited)
        names = {request.name: request for request in selected}
        for key in ('sky_labels', 'sky_constellations', 'moon_sites'):
            self.assertEqual(names[DATASETS[key][1]].source, 'scene')
        self.assertNotIn(DATASETS['mars_names'][1], names)
        report = self.report(view)
        self.assertIn('sky markers: sky-labels.markers', report)
        self.assertIn('sky arcs: sky-constellations.arcs', report)
        self.assertIn('moon marker_file: moon-sites.markers', report)
        self.assertNotIn('mars-names.markers', report)
        self.assertIn('Expected scene input:', report)
        projected, _ = requests(replace(view, projection='rectangular'))
        projected_names = {request.name for request in projected}
        self.assertIn('moon-sites.markers', projected_names)
        self.assertNotIn('sky-labels.markers', projected_names)
        self.assertNotIn('sky-constellations.arcs', projected_names)

    def test_stock_is_unknown_without_lookup_even_if_local_copy_exists(self):
        (self.project/'images').mkdir()
        (self.project/'images/earth.jpg').write_bytes(b'not an image')
        report = self.report()
        self.assertIn('Renderer lookup input; installed location is unknown', report)
        self.assertIn('regular file present', report)
        self.assertIn('resolution remains unknown', report)
        self.assertIn('not readability/decoding', report)
        self.assertNotIn('unsupported', report)
        self.assertNotIn('/usr/local/share', report)

    def test_expected_map_missing_and_not_found_do_not_mean_missing_capability(self):
        view = replace(View(), target='moon')
        name = view.resource_paths()[0].as_posix()
        report = self.report(view, ((name, False),))
        self.assertIn('[missing]', report)
        self.assertIn('not proof that every search location failed', report)
        self.assertIn('resolution remains unknown', report)
        self.assertNotIn('unsupported', report)

    def test_regular_expected_project_map_and_successful_lookup_are_separate(self):
        view = replace(View(), target='moon'); name = view.resource_paths()[0]
        path = self.project/name; path.parent.mkdir(parents=True); path.write_bytes(b'not decoded')
        report = self.report(view, ((str(path), True),))
        self.assertIn('regular file present', report)
        self.assertIn('Reported found (filename match, not decoding)', report)
        self.assertNotIn('Possible shadowing', report)
        self.assertIn('do not bind resource bytes', report)

    def test_miss_then_found_and_potential_shadow_copy_are_not_errors(self):
        local = self.project/'images'; local.mkdir(); (local/'earth.jpg').write_bytes(b'local')
        rows = (('earth.jpg', False), ('/package/images/earth.jpg', True))
        report = self.report(rows=rows)
        self.assertIn('/package/images/earth.jpg', report)
        self.assertIn('a later found path is normal', report)
        self.assertIn('Potentially shadowed/not selected', report)
        self.assertIn('precedence is not independently verified', report)
        self.assertNotIn('Expected project input', report)

    def test_expected_map_found_under_other_root_is_only_possible_shadowing(self):
        view = replace(View(), target='moon'); name = view.resource_paths()[0].as_posix()
        report = self.report(view, (('/other/'+name, True),))
        self.assertIn('Possible shadowing/path mismatch', report)
        self.assertIn('matching names alone do not prove a role match', report)

    def test_log_paths_are_not_inspected_and_nonmatching_suffix_is_not_attributed(self):
        real_stat = os.stat
        calls = []
        def record(path, *args, **kwargs):
            calls.append(str(path))
            return real_stat(path, *args, **kwargs)
        with mock.patch('configurator.resource_diagnostics.os.stat', side_effect=record):
            report = self.report(rows=(('/untrusted/earth.jpg', True), ('/untrusted/notearth.jpg', True)))
        self.assertIn('/untrusted/earth.jpg', report)
        self.assertNotIn('notearth.jpg', report)
        self.assertFalse(any('/untrusted' in path for path in calls))

    def test_child_symlinks_and_nonregular_inputs_are_not_followed(self):
        outside = self.root/'outside'; outside.mkdir(); (outside/'earth.jpg').write_bytes(b'NEVER_READ_FILE_CONTENTS')
        (self.project/'images').symlink_to(outside, target_is_directory=True)
        self.assertEqual(_metadata(self.project, 'images/earth.jpg'), 'symlink (not followed)')
        (self.project/'earth.jpg').symlink_to(outside/'earth.jpg')
        os.mkfifo(self.work/'night.jpg')
        report = self.report()
        self.assertIn('symlink (not followed)', report)
        self.assertIn('not a regular file', report)
        self.assertNotIn('NEVER_READ_FILE_CONTENTS', report)

    def test_explicit_root_symlink_can_resolve_without_following_children(self):
        alias = self.root/'project-alias'; alias.symlink_to(self.project, target_is_directory=True)
        (self.project/'earth.jpg').write_bytes(b'fixture')
        report = describe(View(), (), self.work, alias)
        self.assertIn(str(self.project/'earth.jpg'), report)
        self.assertIn('regular file present', report)

    def test_scene_and_sky_roles_stay_distinct_and_inactive_auxiliary_is_not_requested(self):
        view = SimpleNamespace(
            body=lambda: b'[moon]\nmarker_file=moon-sites.markers\n',
            resource_paths=lambda: [],
            auxiliary_files=lambda **kwargs: {'moon-sites.markers': b'body', 'sky-labels.markers': b'sky', 'inactive.arcs': b'inactive'},
            arguments=lambda: ['-marker_file', 'sky-labels.markers'])
        selected, limited = requests(view)
        self.assertFalse(limited)
        self.assertEqual([(r.role, r.name, r.source) for r in selected],
                         [('moon marker_file', 'moon-sites.markers', 'scene'),
                          ('sky markers', 'sky-labels.markers', 'scene')])
        (self.work/'moon-sites.markers').write_bytes(b'fixture')
        report = self.report(view)
        self.assertIn('Expected scene input', report)
        self.assertNotIn('inactive.arcs', report)

    def test_request_count_names_and_output_are_bounded(self):
        def sample(body):
            return SimpleNamespace(body=lambda: body, resource_paths=lambda: [],
                                   auxiliary_files=lambda **kwargs: {}, arguments=lambda: [])
        view = sample(b'[earth]\n'+b''.join(f'marker_file={n:02d}-'.encode()+b'x'*480+b'\n' for n in range(40)))
        selected, limited = requests(view)
        self.assertEqual(len(selected), MAX_REQUESTS); self.assertTrue(limited)
        report = self.report(view)
        self.assertLess(len(report), REPORT_LIMIT+100)
        self.assertIn('report omitted', report)
        for name in ('../escape', '/absolute', 'bad name', 'x'*513):
            selected, _ = requests(sample(('[earth]\nmap='+name+'\n').encode()))
            self.assertEqual(selected, ())
        report = self.report(sample(b'x'*65537))
        self.assertIn('unknown; request inspection failed', report)

    def test_incomplete_lookup_and_row_limit_are_explicit(self):
        report = self.report(incomplete=True)
        self.assertIn('omitted searches cannot establish absence or precedence', report)
        raw = b''.join(f'Looking for /candidate/{n}/earth.jpg ... not found\n'.encode() for n in range(129))
        evidence = resource_evidence(self.root/'renderer', View(), io.BytesIO(raw), self.work/'output.png', 'failed', 1)
        self.assertEqual(len(evidence.lookups), 128)
        self.assertTrue(evidence.lookup_limited)
        self.assertIn('Lookup evidence is incomplete', evidence.resource_details)
        self.assertIn('row limit reached: True', '\n'.join(evidence.sections()))

    def test_log_controls_are_escaped_in_user_facing_sections(self):
        evidence = resource_evidence(self.root/'renderer', View(), io.BytesIO(b'Looking for /unsafe/\x1b[31m/earth.jpg ... found\n'), self.work/'out', 'failed', 1)
        report = '\n'.join(evidence.sections())
        self.assertNotIn('\x1b', report)
        self.assertIn('\\x1b', report)
