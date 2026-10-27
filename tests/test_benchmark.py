import json
import sys
from unittest.mock import Mock

import pytest

from kaggle import benchmark


@pytest.mark.parametrize(
    "responses, methods, completed, skipped, successes",
    [
        pytest.param([(201, {"id": 42}, 1), (200, [{"id": 42}], 2), (204, None, 3)],
                     ["POST", "GET", "DELETE"], 1, 0, 3, id="success"),
        pytest.param([(500, {"detail": "error"}, 1)], ["POST"], 0, 2, 0, id="post-fails"),
        pytest.param([(201, {"id": 42}, 1), (500, {"detail": "error"}, 2), (204, None, 3)],
                     ["POST", "GET", "DELETE"], 0, 0, 2, id="get-fails-cleanup-runs"),
        pytest.param([(201, {"id": 42}, 1), (200, [{"id": 42}], 2), (500, {}, 3)],
                     ["POST", "GET", "DELETE"], 0, 0, 2, id="delete-fails"),
        pytest.param([(201, {"id": 42}, 1), (200, [], 2), (204, None, 3)],
                     ["POST", "GET", "DELETE"], 0, 0, 3, id="task-missing-cleanup-runs"),
    ],
)
def test_worker_records_requests_and_counts_cycles(
    monkeypatch, responses, methods, completed, skipped, successes
):
    fake_request = Mock(side_effect=responses * 2)
    monkeypatch.setattr(benchmark, "request", fake_request)
    result = benchmark.worker("http://test", "test-token", iterations=2, worker_id=7)

    assert result["completed_cycles"] == completed * 2
    assert result["skipped_requests"] == skipped * 2
    assert sum(item["success"] for item in result["measurements"]) == successes * 2
    assert [call.args[1] for call in fake_request.call_args_list] == methods * 2
    for iteration in range(2):
        for offset, (method, (status, _, latency)) in enumerate(zip(methods, responses)):
            assert result["measurements"][iteration * len(methods) + offset] == {
                "worker_id": 7,
                "iteration": iteration,
                "method": method,
                "status": status,
                "latency_ms": latency,
                "success": status == benchmark.EXPECTED_STATUS[method],
            }
    for call in fake_request.call_args_list:
        if call.args[1] == "DELETE":
            assert call.args[2] == "/api/tasks/42"


def test_summary_aggregates_workers_and_preserves_raw_measurements(monkeypatch):
    monkeypatch.setattr(benchmark, "request", Mock(side_effect=[
        (201, {"id": 42}, 10), (200, [{"id": 42}], 20), (204, None, 30),
        (500, {}, 40),
    ]))
    first = benchmark.worker("http://test", "token-a", 1, 0)
    second = benchmark.worker("http://test", "token-b", 1, 1)
    report = benchmark.summarize([first, second], duration=2, concurrency=2, iterations=1)
    assert report["expected_requests"] == 6
    assert report["attempted_requests"] == 4
    assert report["successful_requests"] == 3
    assert report["failed_requests"] == 1
    assert report["skipped_requests"] == 2
    assert report["expected_cycles"] == 2
    assert report["completed_cycles"] == 1
    assert report["incomplete_cycles"] == 1
    assert report["throughput_rps"] == 2
    assert report["measurements"] == first["measurements"] + second["measurements"]
    assert report["methods"]["POST"] == {"n": 2, "mean_ms": 25, "p50_ms": 10, "p95_ms": 40}
    assert report["methods"]["GET"]["mean_ms"] == 20
    assert report["methods"]["DELETE"]["mean_ms"] == 30


@pytest.mark.parametrize("scenario", ["success", "post-fails", "task-missing"])
def test_main_writes_report_before_exiting(tmp_path, monkeypatch, capsys, scenario):
    destination = tmp_path / "nested" / "results" / "run.json"
    monkeypatch.setattr(sys, "argv", [
        "benchmark.py", "--concurrency", "1", "--iterations", "1",
        "--output-json", str(destination),
    ])
    prepare = Mock(return_value="private-token-not-for-report")
    monkeypatch.setattr(benchmark, "prepare_user", prepare)
    responses = [(500, {}, 1)] if scenario == "post-fails" else [
        (201, {"id": 42}, 1),
        (200, [] if scenario == "task-missing" else [{"id": 42}], 2),
        (204, None, 3),
    ]
    monkeypatch.setattr(benchmark, "request", Mock(side_effect=responses))
    if scenario == "success":
        benchmark.main()
    else:
        with pytest.raises(SystemExit) as error:
            benchmark.main()
        assert error.value.code == 1

    prepare.assert_called_once_with("http://127.0.0.1:8000")
    text = destination.read_text(encoding="utf-8")
    assert "private-token-not-for-report" not in text
    report = json.loads(text)
    assert report["completed_cycles"] == int(scenario == "success")
    assert report["expected_requests"] == 3
    assert report["attempted_requests"] + report["skipped_requests"] == 3
    assert report["successful_requests"] + report["failed_requests"] == report["attempted_requests"]
    output = capsys.readouterr().out
    for key in ("expected_requests", "attempted_requests", "successful_requests",
                "failed_requests", "skipped_requests", "completed_cycles"):
        assert f"{key}: {report[key]}" in output
    if scenario == "post-fails":
        assert report["methods"]["GET"] == {"n": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}


def test_json_output_is_optional(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--concurrency", "1", "--iterations", "1"])
    monkeypatch.setattr(benchmark, "prepare_user", Mock(return_value="token"))
    monkeypatch.setattr(benchmark, "request", Mock(side_effect=[
        (201, {"id": 42}, 1), (200, [{"id": 42}], 2), (204, None, 3),
    ]))
    benchmark.main()
    assert "completed_cycles: 1" in capsys.readouterr().out
