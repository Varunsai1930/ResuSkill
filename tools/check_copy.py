"""Smoke-test an isolated manual copy, using no modules or data from the checkout."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='resuskill installed copy ') as temporary:
        base = Path(temporary)
        installed = base / 'skills with spaces' / 'resuskill'
        shutil.copytree(root / 'skills/resuskill', installed,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        env = dict(os.environ, RESUSKILL_HOME=str(base / 'empty home'), PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        script = str(installed / 'scripts/resuskill.py')
        def run(*args):
            result = subprocess.run([sys.executable, script, *args], cwd=base, env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=60)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
            return result.stdout
        run('--help')
        demo = json.loads(run('demo', '--output', str(base / 'fictional demo'), '--json'))
        env['RESUSKILL_HOME'] = demo['data_dir']
        assert Path(demo['review']).is_file()
        assert Path(demo['resume']).is_file()
        assert json.loads(run('insights', '--json'))['recorded_jobs'] == 1
        assert len(json.loads(run('pipeline', '--json'))['jobs']) == 1
        migrated = json.loads(run('migrate', '--output', str(base / 'migrated data')))
        env['RESUSKILL_HOME'] = migrated['data_dir']
        prof = json.loads(run('profile', 'show', '--json'))
        job = json.loads(run('jobs', '--json'))[0]['id']
        run('followup', 'set', job, '--date', '2028-02-29', '--note', 'Manual test')
        assert len(json.loads(run('followup', 'list', job, '--json'))) == 1
        run('insights', '--historical', '--json')
        def write(name, data):
            path = base / name
            path.write_text(json.dumps(data), encoding='utf-8')
            return str(path)
        part = {'text': prof['summary'], 'sources': ['summary']}
        letter = write('letter.json', {'paragraphs': [part]})
        run('letter', 'propose', job, '--file', letter)
        run('letter', 'accept', job)
        run('letter', 'render', job, '--output', str(base / 'letter export'))
        story = write('story.json', {'situation': part, 'task': part, 'action': part,
                                    'result': None, 'contribution_scope': 'personal'})
        ident = json.loads(run('stories', 'propose', '--file', story))['id']
        run('stories', 'accept', ident)
        run('stories', 'check', ident)
        run('stories', 'suggest', job)
        run('stories', 'export', ident, '--output', str(base / 'story export'))
        assert (base / 'story export/story.html').is_file()
        assert (base / 'letter export/letter.html').is_file()
        print('PASS: copied CLI, demo, reports, migration, follow-ups, history, letters and stories outside checkout')


if __name__ == '__main__':
    main()
