"""Explicit copy migration; original data and historical snapshots stay unchanged."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

from . import jobs, package, profile, store
from .util import ResuError, now_iso


def migrate(output):
    source = store.home().resolve()
    target = Path(output).expanduser().absolute()
    if target.exists() or target.is_symlink() or source == target.resolve() or source in target.resolve().parents:
        raise ResuError('Migration needs a new directory outside the source data directory.')
    if store.data_version() != 1:
        raise ResuError('This directory is already migrated.')
    # Validate current data before any copy; historical artifacts remain byte-for-byte.
    profile.load()
    problems = []
    saved = jobs.list_jobs(problems)
    if problems:
        raise ResuError('Repair unreadable jobs before migration.', [str(p) for p in problems])
    for job in saved:
        package.load(job['id'])
        package.load_proposal(job['id'])
    for path in (source / 'imports').glob('*.json'):
        journal = store.read_json(path)
        if not isinstance(journal, dict) or journal.get('complete') is not True:
            raise ResuError('Finish or recover incomplete imports in the original directory before migration. Import previews must be regenerated after migration.')
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ResuError('Migration refuses symlinks; use a regular-file data backup.')
        if path.is_file() and path.suffix == '.json':
            store.read_json(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.resuskill-migrate-', dir=target.parent))
    previous = os.environ.get('RESUSKILL_HOME')
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.command-lock'))
        p = staging / 'profile.json'
        prof = store.read_json(p)
        prof['_meta']['schema'] = 2
        store.write_json(p, prof)
        for job in saved:
            folder = staging / 'jobs' / job['id']
            for name in ('job.json', 'package.json', 'proposal.json'):
                path = folder / name
                data = store.read_json(path)
                if data is not None:
                    data['schema_version'] = 2
                    if name == 'package.json':
                        data['approval'] = None
                    store.write_json(path, data)
        store.write_json(staging / 'format.json', {'version': 2, 'migrated_at': now_iso()})
        os.environ['RESUSKILL_HOME'] = str(staging)
        profile.load()
        for job in saved:
            jobs.load(job['id'])
            package.load(job['id'])
            package.load_proposal(job['id'])
        # Never replace an existing destination, including an empty directory.
        if target.exists() or target.is_symlink():
            raise ResuError('Migration destination appeared during preparation; refusing replacement.')
        staging.rename(target)
    finally:
        if previous is None:
            os.environ.pop('RESUSKILL_HOME', None)
        else:
            os.environ['RESUSKILL_HOME'] = previous
        if staging.exists():
            shutil.rmtree(staging)
    return {'data_dir': str(target), 'source_unchanged': str(source), 'version': 2,
            'next_step': 'Use this data_dir as RESUSKILL_HOME. Review packages again before approval.'}
