from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from helpers import IsolatedHome, fixture
from resuskill_core import imports, jobs, package, store
from resuskill_core.util import ResuError


class ImportTests(IsolatedHome):
    def records(self):
        return [{'company': 'Example', 'title': 'Engineer', 'description': 'Python required',
                 'source_url': 'https://example.com/jobs/1', 'observed_at': '2026-01-01T00:00:00Z'}]

    def test_preview_apply_replay_and_reordered_input(self):
        data = self.records()
        preview = imports.preview(data)
        self.assertEqual(preview['rows'][0]['state'], 'addition')
        result = imports.apply(data, preview, [1])
        self.assertEqual(imports.apply(data, preview, [1]), result)
        self.assertEqual(len(jobs.list_jobs()), 1)
        self.assertEqual(jobs.list_jobs()[0]['listing']['status'], 'unknown')
        self.assertEqual(imports.preview(data)['rows'][0]['state'], 'duplicate')
        changed = deepcopy(data)
        changed[0]['description'] = 'New description'
        with self.assertRaises(ResuError):
            imports.apply(changed, preview, [1])

    def test_distinct_requisitions_and_possible_duplicates(self):
        data = self.records()
        data[0].update(source_namespace='example', requisition_id='one')
        imports.apply(data, imports.preview(data), [1])
        data[0]['requisition_id'] = 'two'
        data[0]['source_url'] = 'https://example.com/jobs/2'
        preview = imports.preview(data)
        self.assertEqual(preview['rows'][0]['state'], 'possible_duplicate')
        imports.apply(data, preview, [1])
        self.assertEqual(len(jobs.list_jobs()), 2)

    def test_changed_import_source_metadata_requires_reviewed_update(self):
        data = self.records()
        data[0].update(source_namespace='example', requisition_id='one')
        jid = imports.apply(data, imports.preview(data), [1])['jobs'][0]
        for changes in ({'source_url': 'https://example.com/new-posting'},
                        {'observed_at': '2026-10-24T00:00:00Z'}):
            with self.subTest(changes=changes):
                before = jobs.load(jid)
                data[0].update(changes)
                preview = imports.preview(data)
                self.assertEqual(preview['rows'][0]['state'], 'update')
                with self.assertRaises(ResuError):
                    imports.apply(data, preview, [1])
                self.assertEqual(jobs.load(jid), before)
                imports.apply(data, preview, [1], {1: jid})
                after = jobs.load(jid)
                self.assertEqual(after['url'], data[0]['source_url'])
                self.assertEqual(after['import_source']['observed_at'], data[0]['observed_at'])
                self.assertEqual(after['revision'], before['revision'] + 1)
                self.assertEqual(after['tracking'], before['tracking'])
                self.assertEqual(imports.preview(data)['rows'][0]['state'], 'duplicate')

    def test_update_requires_selection_preserves_package_and_tracking(self):
        data = self.records()
        jid = imports.apply(data, imports.preview(data), [1])['jobs'][0]
        before = jobs.load(jid)
        store.write_json(store.job_dir(jid) / 'package.json', {'marker': 'preserve'})
        data[0]['description'] = 'Rust required'
        preview = imports.preview(data)
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        imports.apply(data, preview, [1], {1: jid})
        after = jobs.load(jid)
        self.assertEqual(after['tracking'], before['tracking'])
        self.assertEqual(after['revision'], before['revision'] + 1)
        self.assertEqual(store.read_json(store.job_dir(jid) / 'package.json'), {'marker': 'preserve'})

    def test_stale_preview_and_rejected_rows_do_not_write(self):
        data = self.records()
        preview = imports.preview(data)
        jobs.add('Other', 'Role', 'Text')
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        data.append({'company': 'Invalid'})
        preview = imports.preview(data)
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1, 2])
        self.assertEqual(len(jobs.list_jobs()), 1)

    def test_partial_import_resumes_after_failure_without_duplicates(self):
        data = self.records()
        data.append(dict(data[0], source_url='https://example.com/jobs/2'))
        preview = imports.preview(data)
        real = store.write_json
        count = 0
        def interrupted(path, value):
            nonlocal count
            if Path(path).name == 'job.json':
                count += 1
                if count == 2:
                    raise OSError('interrupted')
            real(path, value)
        with patch.object(store, 'write_json', side_effect=interrupted), self.assertRaises(OSError):
            imports.apply(data, preview, [1, 2])
        self.assertEqual(len(jobs.list_jobs()), 1)
        result = imports.apply(data, preview, [1, 2])
        self.assertEqual(len(result['jobs']), 2)
        self.assertEqual(len(jobs.list_jobs()), 2)

    def test_recovery_accepts_only_its_own_empty_interrupted_directory(self):
        data = self.records()
        preview = imports.preview(data)
        real_write = store.write_json
        def interrupted(path, value):
            if Path(path).name == 'job.json':
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                raise OSError('interrupted after creating destination')
            real_write(path, value)
        with patch.object(store, 'write_json', side_effect=interrupted), self.assertRaises(OSError):
            imports.apply(data, preview, [1])
        missing = next(store.jobs_dir().iterdir())
        with self.assertRaises(ResuError):
            imports.preview(data)
        unrelated = store.jobs_dir() / 'unexplained'
        unrelated.mkdir()
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        unrelated.rmdir()
        extra = missing / 'package.json'
        extra.write_text('{}', encoding='utf-8')
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        extra.unlink()
        result = imports.apply(data, preview, [1])
        self.assertEqual(result['jobs'], [missing.name])
        self.assertEqual(len(jobs.list_jobs()), 1)

    def test_modified_destination_blocks_resume(self):
        data = self.records()
        preview = imports.preview(data)
        result = imports.apply(data, preview, [1])
        job = jobs.load(result['jobs'][0])
        job['tracking']['status'] = 'interview'
        jobs.save(job)
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])

    def test_url_identity_and_duplicate_input(self):
        self.assertEqual(imports.canonical_url('https://EXAMPLE.com:443/jobs/1#top'), 'https://example.com/jobs/1')
        data = self.records()
        data.append(deepcopy(data[0]))
        self.assertEqual(imports.preview(data)['rows'][1]['state'], 'rejected')
        for url in ('javascript:alert(1)', 'https://user:secret@example.com', 'https://example.com:bad'):
            data = self.records()
            data[0]['source_url'] = url
            self.assertEqual(imports.preview(data)['rows'][0]['state'], 'rejected')

    def test_damaged_journal_is_rejected_without_writes(self):
        data = self.records()
        preview = imports.preview(data)
        result = imports.apply(data, preview, [1])
        journal = store.read_json(Path(result['journal']))
        journal['plan'] = [None]
        store.write_json(Path(result['journal']), journal)
        before = jobs.list_jobs()
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        self.assertEqual(before, jobs.list_jobs())

    def test_valid_but_changed_recovery_payload_is_refused(self):
        data = self.records()
        preview = imports.preview(data)
        real = store.write_json
        def interrupted(path, value):
            if Path(path).name == 'job.json':
                raise OSError('interrupted')
            real(path, value)
        with patch.object(store, 'write_json', side_effect=interrupted), self.assertRaises(OSError):
            imports.apply(data, preview, [1])
        path = next((store.home() / 'imports').glob('*.json'))
        journal = store.read_json(path)
        journal['plan'][0]['after']['description'] = 'Unreviewed replacement'
        journal['plan'][0]['after']['tracking']['status'] = 'applied'
        from resuskill_core.util import content_hash
        journal['plan_hash'] = content_hash(journal['plan'])  # Even an updated checksum cannot change approved semantics.
        store.write_json(path, journal)
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        self.assertEqual(jobs.list_jobs(), [])

    def test_removed_recovery_steps_cannot_report_completion(self):
        data = self.records()
        preview = imports.preview(data)
        real = store.write_json
        def interrupted(path, value):
            if Path(path).name == 'job.json':
                raise OSError('interrupted')
            real(path, value)
        with patch.object(store, 'write_json', side_effect=interrupted), self.assertRaises(OSError):
            imports.apply(data, preview, [1])
        path = next((store.home() / 'imports').glob('*.json'))
        journal = store.read_json(path)
        journal['plan'] = []
        from resuskill_core.util import content_hash
        journal['plan_hash'] = content_hash([])
        store.write_json(path, journal)
        with self.assertRaises(ResuError):
            imports.apply(data, preview, [1])
        self.assertEqual(jobs.list_jobs(), [])
