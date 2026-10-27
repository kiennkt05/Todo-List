from http.client import IncompleteRead
import io
import json
import sys
from threading import Event
import urllib.error
from unittest.mock import Mock

import pytest

from kaggle import benchmark


def response_result(status, payload, latency):
    success = status in (200, 201, 204)
    return {
        "status": status, "payload": payload, "latency_ms": latency, "success": success,
        "error_type": None if success else "http_error",
        "error_message": None if success else f"Unexpected HTTP {status}",
    }


class FakeResponse(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(body)
        self.code = status


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
                     ["POST", "GET", "DELETE"], 0, 0, 2, id="task-missing-cleanup-runs"),
    ],
)
def test_worker_records_requests_and_counts_cycles(
    monkeypatch, responses, methods, completed, skipped, successes
):
    fake_request = Mock(side_effect=[response_result(*item) for item in responses * 2])
    monkeypatch.setattr(benchmark, "request", fake_request)
    result = benchmark.worker("http://test", "test-token", iterations=2, worker_id=7)

    assert result["completed_cycles"] == completed * 2
    assert result["skipped_requests"] == skipped * 2
    assert sum(item["success"] for item in result["measurements"]) == successes * 2
    assert [call.args[1] for call in fake_request.call_args_list] == methods * 2
    for iteration in range(2):
        for offset, (method, (status, _, latency)) in enumerate(zip(methods, responses)):
            measurement = result["measurements"][iteration * len(methods) + offset]
            assert {key: measurement[key] for key in (
                "worker_id", "iteration", "method", "status", "latency_ms",
            )} == {
                "worker_id": 7,
                "iteration": iteration,
                "method": method,
                "status": status,
                "latency_ms": latency,
            }
            assert "payload" not in measurement
            if method == "GET" and status == 200 and responses[offset][1] == []:
                assert measurement["success"] is False
                assert measurement["error_type"] == "consistency_error"
            else:
                assert measurement["success"] == (status == benchmark.EXPECTED_STATUS[method])
    for call in fake_request.call_args_list:
        if call.args[1] == "DELETE":
            assert call.args[2] == "/api/tasks/42"


def test_summary_aggregates_workers_and_preserves_raw_measurements(monkeypatch):
    monkeypatch.setattr(benchmark, "request", Mock(side_effect=[response_result(*item) for item in [
        (201, {"id": 42}, 10), (200, [{"id": 42}], 20), (204, None, 30),
        (500, {}, 40),
    ]]))
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
    assert report["success_throughput"] == 1.5
    assert report["error_rate"] == 0.25
    assert report["run_status"] == "completed_with_errors"
    assert report["methods"]["POST"] == {
        "n": 2, "successful_requests": 1, "failed_requests": 1,
        "mean_ms": 10, "p50_ms": 10, "p95_ms": 10,
        "failures_by_status": {"500": 1}, "failures_by_error_type": {"http_error": 1},
    }
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
    monkeypatch.setattr(benchmark, "request", Mock(side_effect=[response_result(*item) for item in responses]))
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
    assert report["run_status"] == ("completed" if scenario == "success" else "completed_with_errors")
    assert report["completed_cycles"] == int(scenario == "success")
    assert report["expected_requests"] == 3
    assert report["attempted_requests"] + report["skipped_requests"] == 3
    assert report["successful_requests"] + report["failed_requests"] == report["attempted_requests"]
    output = capsys.readouterr().out
    for key in ("expected_requests", "attempted_requests", "successful_requests",
                "failed_requests", "skipped_requests", "completed_cycles"):
        assert f"{key}: {report[key]}" in output
    if scenario == "post-fails":
        assert report["methods"]["GET"]["n"] == 0
        assert report["methods"]["POST"]["successful_requests"] == 0
        for method in ("POST", "GET", "DELETE"):
            assert all(report["methods"][method][key] is None for key in ("mean_ms", "p50_ms", "p95_ms"))
    if scenario == "task-missing":
        assert report["failures_by_status"] == {"200": 1}
        assert report["failures_by_error_type"] == {"consistency_error": 1}


def test_json_output_is_optional(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--concurrency", "1", "--iterations", "1"])
    monkeypatch.setattr(benchmark, "prepare_user", Mock(return_value="token"))
    monkeypatch.setattr(benchmark, "request", Mock(side_effect=[response_result(*item) for item in [
        (201, {"id": 42}, 1), (200, [{"id": 42}], 2), (204, None, 3),
    ]]))
    benchmark.main()
    assert "completed_cycles: 1" in capsys.readouterr().out


@pytest.mark.parametrize("exception, category", [
    (TimeoutError("timed out"), "timeout"),
    (urllib.error.URLError(TimeoutError("timed out")), "timeout"),
    (urllib.error.URLError("connection refused"), "network_error"),
    (ConnectionResetError("connection reset"), "network_error"),
])
def test_request_classifies_connection_errors_without_retry(monkeypatch, exception, category):
    opener = Mock(side_effect=exception)
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", opener)
    result = benchmark.request("http://test", "GET", "/api/tasks")
    assert result["status"] is None
    assert result["success"] is False
    assert result["error_type"] == category
    assert result["error_message"]
    assert result["latency_ms"] >= 0
    opener.assert_called_once()


@pytest.mark.parametrize("exception, category", [
    (TimeoutError("read timed out"), "timeout"),
    (IncompleteRead(b"partial"), "network_error"),
])
def test_request_preserves_status_when_body_read_fails(monkeypatch, exception, category):
    response = FakeResponse(200, b"")
    response.read = Mock(side_effect=exception)
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", Mock(return_value=response))
    result = benchmark.request("http://test", "GET", "/api/tasks")
    assert result["status"] == 200
    assert result["error_type"] == category
    assert not result["success"]
    assert response.closed


@pytest.mark.parametrize("status, body, method, path, expected", [
    (201, b"{}", "POST", "/api/tasks", 201),
    (201, b'{"id":true}', "POST", "/api/tasks", 201),
    (201, b'{"id":"42"}', "POST", "/api/tasks", 201),
    (200, b"{}", "GET", "/api/tasks", 200),
    (200, b"[{}]", "GET", "/api/tasks", 200),
    (200, b"[null]", "GET", "/api/tasks", 200),
    (200, b"<html>error</html>", "GET", "/api/tasks", 200),
    (200, b"\xff", "GET", "/api/tasks", 200),
    (204, b"{}", "DELETE", "/api/tasks/42", 204),
    (200, b'{"access_token":""}', "POST", "/api/auth/login", 200),
    (200, b"{}", "POST", "/api/auth/login", 200),
    (201, b'{"id":42}', "POST", "/api/auth/register", 201),
])
def test_request_rejects_invalid_response(monkeypatch, status, body, method, path, expected):
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", Mock(return_value=FakeResponse(status, body)))
    result = benchmark.request("http://test", method, path, expected_status=expected)
    assert result["status"] == status
    assert result["success"] is False
    assert result["error_type"] == "invalid_response"
    assert result["error_message"]


def test_http_error_takes_priority_over_non_json_body(monkeypatch):
    response = urllib.error.HTTPError("http://test", 503, "Unavailable", {}, io.BytesIO(b"<html>error</html>"))
    opener = Mock(side_effect=response)
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", opener)
    result = benchmark.request("http://test", "GET", "/api/tasks")
    assert result["status"] == 503
    assert result["error_type"] == "http_error"
    assert result["latency_ms"] >= 0
    assert response.closed
    opener.assert_called_once()


def test_unexpected_success_status_is_http_error(monkeypatch):
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", Mock(return_value=FakeResponse(202, b"{}")))
    result = benchmark.request("http://test", "POST", "/api/tasks")
    assert result["error_type"] == "http_error"
    assert result["status"] == 202


def test_request_does_not_hide_programming_errors(monkeypatch):
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", Mock(side_effect=RuntimeError("programming bug")))
    with pytest.raises(RuntimeError, match="programming bug"):
        benchmark.request("http://test", "GET", "/api/tasks")


@pytest.mark.parametrize("bad_method", ["POST", "GET"])
def test_worker_handles_invalid_payload_without_unsafe_access(monkeypatch, bad_method):
    responses = [FakeResponse(201, b"{}" if bad_method == "POST" else b'{"id":42}')]
    if bad_method == "GET":
        responses.extend([FakeResponse(200, b"[null]"), FakeResponse(204, b"")])
    opener = Mock(side_effect=responses)
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", opener)
    result = benchmark.worker("http://test", "token", 1, 0)
    assert result["completed_cycles"] == 0
    errors = [item for item in result["measurements"] if not item["success"]]
    assert len(errors) == 1
    assert errors[0]["method"] == bad_method
    assert errors[0]["error_type"] == "invalid_response"
    assert result["skipped_requests"] == (2 if bad_method == "POST" else 0)
    if bad_method == "GET":
        assert result["measurements"][-1]["method"] == "DELETE"
        assert result["measurements"][-1]["success"] is True


def test_worker_continues_after_timeout_and_counts_failed_attempt(monkeypatch):
    failure = benchmark.fail(response_result(None, None, 30), "timeout", "Timed out")
    fake = Mock(side_effect=[failure, response_result(201, {"id": 42}, 1),
                            response_result(200, [{"id": 42}], 2), response_result(204, None, 3)])
    monkeypatch.setattr(benchmark, "request", fake)
    result = benchmark.worker("http://test", "token", 2, 0)
    report = benchmark.summarize([result], 2, 1, 2)
    assert report["completed_cycles"] == 1
    assert report["skipped_requests"] == 2
    assert report["attempted_requests"] == 4
    assert report["failures_by_status"] == {"no_response": 1}
    assert report["failures_by_error_type"] == {"timeout": 1}
    assert report["methods"]["POST"]["mean_ms"] == 1


@pytest.mark.parametrize("operation", ["register", "login"])
def test_main_saves_setup_failure(tmp_path, monkeypatch, capsys, operation):
    destination = tmp_path / "setup.json"
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--output-json", str(destination)])
    responses = [] if operation == "register" else [FakeResponse(201, b'{"id":1,"email":"test@example.com"}')]
    responses.append(urllib.error.URLError("connection refused"))
    opener = Mock(side_effect=responses)
    monkeypatch.setattr(benchmark.urllib.request, "urlopen", opener)
    with pytest.raises(SystemExit) as exc:
        benchmark.main()
    assert exc.value.code == 1
    report = json.loads(destination.read_text())
    assert report["run_status"] == "aborted"
    assert report["run_errors"][0]["stage"] == "setup"
    assert report["run_errors"][0]["operation"] == operation
    assert report["run_errors"][0]["error_type"] == "network_error"
    assert report["attempted_requests"] == 0
    assert report["error_rate"] is None
    assert report["success_throughput"] is None
    assert "payload" not in report["run_errors"][0]
    assert opener.call_count == (1 if operation == "register" else 2)


@pytest.mark.parametrize("exception", [RuntimeError("setup bug"), KeyboardInterrupt()])
def test_main_saves_unexpected_setup_abort(tmp_path, monkeypatch, capsys, exception):
    destination = tmp_path / "setup-aborted.json"
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--output-json", str(destination)])
    monkeypatch.setattr(benchmark, "prepare_user", Mock(side_effect=exception))
    with pytest.raises(SystemExit) as exc:
        benchmark.main()
    assert exc.value.code == 1
    report = json.loads(destination.read_text())
    assert report["run_status"] == "aborted"
    assert report["run_errors"][0]["stage"] == "setup"
    assert report["run_errors"][0]["exception_type"] == type(exception).__name__
    assert report["measurements"] == []
    assert type(exception).__name__ in capsys.readouterr().err


def test_main_retains_partial_worker_and_other_workers(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "partial.json"
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--concurrency", "2", "--iterations", "1", "--output-json", str(destination)])
    monkeypatch.setattr(benchmark, "prepare_user", Mock(side_effect=["broken", "healthy"]))

    def fake_request(base_url, method, path, body=None, token=None):
        if method == "POST":
            return response_result(201, {"id": 42}, 1)
        if method == "GET" and token == "broken":
            raise RuntimeError("unexpected worker bug")
        if method == "GET":
            return response_result(200, [{"id": 42}], 2)
        return response_result(204, None, 3)

    monkeypatch.setattr(benchmark, "request", fake_request)
    with pytest.raises(SystemExit) as exc:
        benchmark.main()
    assert exc.value.code == 1
    report = json.loads(destination.read_text())
    assert report["run_status"] == "aborted"
    assert report["attempted_requests"] == 4
    assert report["completed_cycles"] == 1
    assert report["unrecorded_requests"] == 2
    assert {row["worker_id"] for row in report["measurements"]} == {0, 1}
    assert report["run_errors"][0]["stage"] == "worker"
    assert report["run_errors"][0]["exception_type"] == "RuntimeError"
    assert report["run_errors"][0]["worker_id"] == 0
    assert "unexpected worker bug" in capsys.readouterr().err


def test_main_saves_keyboard_interrupt_and_waits_for_partial_data(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "interrupt.json"
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--concurrency", "1", "--iterations", "100", "--output-json", str(destination)])
    monkeypatch.setattr(benchmark, "prepare_user", Mock(return_value="token"))
    entered = Event()
    release = Event()

    def fake_request(base_url, method, path, body=None, token=None):
        if method == "POST":
            entered.set()
            assert release.wait(timeout=5)
            return response_result(201, {"id": 42}, 1)
        if method == "GET":
            return response_result(200, [{"id": 42}], 2)
        return response_result(204, None, 3)

    def interrupt_wait(futures):
        assert entered.wait(timeout=5)
        raise KeyboardInterrupt()

    original_shutdown = benchmark.ThreadPoolExecutor.shutdown

    def shutdown(pool, **kwargs):
        release.set()
        return original_shutdown(pool, **kwargs)

    monkeypatch.setattr(benchmark, "request", fake_request)
    monkeypatch.setattr(benchmark, "wait", interrupt_wait)
    monkeypatch.setattr(benchmark.ThreadPoolExecutor, "shutdown", shutdown)
    with pytest.raises(SystemExit) as exc:
        benchmark.main()
    assert exc.value.code == 1
    report = json.loads(destination.read_text())
    assert report["run_status"] == "aborted"
    assert report["completed_cycles"] == 1
    assert report["attempted_requests"] == 3
    assert report["unrecorded_requests"] == 297
    assert report["run_errors"][0]["error_type"] == "interrupted"
    assert "KeyboardInterrupt" in capsys.readouterr().err
