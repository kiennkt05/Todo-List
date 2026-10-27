import csv
import json
from pathlib import Path


NOTEBOOK = Path(__file__).resolve().parents[1] / 'kaggle/load_test.ipynb'


def test_notebook_has_clean_outputs_and_compilable_cells():
    notebook = json.loads(NOTEBOOK.read_text())
    assert notebook['nbformat'] == 4
    assert len({cell['id'] for cell in notebook['cells']}) == len(notebook['cells'])
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            assert cell['execution_count'] is None
            assert cell['outputs'] == []
            compile(''.join(cell['source']), cell['id'], 'exec')


def test_summary_preserves_failed_missing_and_mismatched_runs(tmp_path):
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    plan = [dict(label=f'c1-r{i}', repeat=i, concurrency=1, iterations=2) for i in range(1, 6)]
    save(tmp_path / 'plan.json', plan)
    save(tmp_path / 'environment.json', dict(warmup_iterations=1, http_timeout_seconds=10, git_commit='abc'))
    for i in range(1, 4):
        save(tmp_path / 'runs' / f'c1-r{i}' / 'orchestration.json', {
            'orchestration_status': 'benchmark_failed' if i == 2 else 'completed',
            'benchmark_exit_code': 1 if i == 2 else 0,
        })
        save(tmp_path / f'c1-r{i}.json', dict(
            run_id=str(i), run_status='completed_with_errors' if i == 2 else 'completed',
            concurrency=1, iterations=2, completed_cycles=1 if i == 2 else 2,
            attempted_requests=6, failed_requests=1 if i == 2 else 0,
            success_throughput=10, error_rate=1/6 if i == 2 else 0,
            git_commit='abc', git_dirty=False, warmup_iterations=1,
            timeout_seconds=99 if i == 3 else 10,
            methods={m: {'p95_ms': None if i == 2 else 2.5} for m in ('POST', 'GET', 'DELETE')},
        ))
    (tmp_path / 'c1-r5.json').write_text('not json')
    notebook = json.loads(NOTEBOOK.read_text())
    source = next(''.join(c['source']) for c in notebook['cells'] if c['id'] == 'summary')
    namespace = dict(json=json, csv=csv)
    exec(source.split('\nrows = summarize_batch')[0], namespace)
    rows = namespace['summarize_batch'](tmp_path)
    assert [r['comparable'] for r in rows] == [True, False, False, False, False]
    assert rows[1]['post_p95_ms'] is None
    assert 'Configuration mismatch' in rows[2]['note']
    assert rows[3]['run_status'] == 'missing'
    assert rows[4]['run_status'] == 'invalid_report'
    with (tmp_path / 'runs.csv').open() as file:
        exported = list(csv.DictReader(file))
    assert len(exported) == 5
    assert exported[1]['post_p95_ms'] == ''
    assert exported[3]['success_throughput'] == ''
