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
        print('PASS: copied skill CLI, fictional demo, HTML, insights and pipeline outside checkout')


if __name__ == '__main__':
    main()
