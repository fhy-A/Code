"""Real two-process archive recovery. Parent never imports the service module."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'tests' / 'project_archive_process_worker.py'


@pytest.mark.parametrize('case', ['partial','stopped','bundle'])
def test_project_archive_survives_actual_process_exit(case):
    processes = []
    # Other pre-existing suites may import server during collection. This parent
    # must neither import nor replace it; subprocess exec never inherits it.
    parent_service = sys.modules.get('server')
    with tempfile.TemporaryDirectory(prefix='code072-process-') as directory:
        root = Path(directory).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        environment = dict(os.environ,CODE_DATA_DIR=str(root/'data'))
        def launch(phase, expected):
            process = subprocess.Popen([sys.executable,'-X','utf8','-B',str(WORKER),phase,case],
                cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
            processes.append(process)
            try:
                stdout,stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill();stdout,stderr = process.communicate(timeout=10)
                raise AssertionError(f'{case}/{phase} timed out: {stdout}\n{stderr}')
            assert process.returncode == expected, f'{case}/{phase}: {stdout}\n{stderr}'
            return process.pid,stdout
        try:
            pid_a,_ = launch('seed',73)
            assert all(p.poll() is not None for p in processes), 'A must exit before B starts'
            pid_b,stdout = launch('recover',0)
            result = json.loads((root/'result.json').read_text(encoding='utf-8'))
            assert result['processA'] == pid_a and result['processB'] == pid_b and pid_a != pid_b
            assert result['newInterpreter'] and result['freshRegistriesBeforeRecovery'] and result['passed']
            assert result['networkListenersOpened'] == result['connectionsOpened'] == 0
            assert sys.modules.get('server') is parent_service, 'The parent imported or replaced the service runtime'
            print(stdout.strip())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill();process.communicate(timeout=10)
            assert all(p.poll() is not None for p in processes)
    assert not root.exists(), 'Disposable shared data root was not removed'
    print(json.dumps({'case':case,'childrenExited':True,'rootRemoved':True,'portsOpened':0}))
