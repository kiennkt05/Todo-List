"""Small repeatable CPU load test against a running Todo List API."""

import argparse
from collections import Counter
from http.client import HTTPException
import json
import statistics
import sys
from threading import Event
import time
import traceback
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path


EXPECTED_STATUS = {"POST": 201, "GET": 200, "DELETE": 204}


def fail(result, error_type, message):
    result.update(success=False, error_type=error_type, error_message=message)
    return result


def valid_id(value):
    return type(value) is int and value > 0


def validate_payload(method, path, payload):
    if path == "/api/auth/register":
        if not isinstance(payload, dict) or not valid_id(payload.get("id")) or not isinstance(payload.get("email"), str):
            return "Registration response must contain a positive integer id and email string"
    elif path == "/api/auth/login":
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str) or not payload["access_token"].strip():
            return "Login response must contain a nonempty access_token string"
    elif method == "POST":
        if not isinstance(payload, dict) or not valid_id(payload.get("id")):
            return "Created task must contain a positive integer id"
    elif method == "GET":
        if not isinstance(payload, list) or any(
            not isinstance(item, dict) or not valid_id(item.get("id")) for item in payload
        ):
            return "Task list must be an array of objects with positive integer ids"
    return None


def request(base_url, method, path, body=None, token=None, expected_status=None):
    """Classify expected transport/response errors; let programming errors propagate."""
    expected_status = EXPECTED_STATUS[method] if expected_status is None else expected_status
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    result = {
        "status": None, "payload": None, "latency_ms": None,
        "success": False, "error_type": None, "error_message": None,
    }
    start = time.perf_counter()
    try:
        try:
            response = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as exc:
            # An HTTP error is still a response. Do not require its body to be JSON.
            response = exc
        with response:
            result["status"] = response.code
            if result["status"] != expected_status:
                return fail(result, "http_error", f"Expected HTTP {expected_status}, received {result['status']}")
            payload = response.read()
    except TimeoutError as exc:
        return fail(result, "timeout", str(exc) or "Request timed out")
    except urllib.error.URLError as exc:
        category = "timeout" if isinstance(exc.reason, TimeoutError) else "network_error"
        return fail(result, category, str(exc.reason))
    except (OSError, HTTPException) as exc:
        return fail(result, "network_error", str(exc) or type(exc).__name__)
    finally:
        result["latency_ms"] = (time.perf_counter() - start) * 1000

    if expected_status == 204:
        if payload:
            return fail(result, "invalid_response", "HTTP 204 response must have an empty body")
    else:
        try:
            result["payload"] = json.loads(payload)
        except (ValueError, UnicodeError):
            return fail(result, "invalid_response", "Response body is not valid JSON")
        error = validate_payload(method, path, result["payload"])
        if error:
            return fail(result, "invalid_response", error)
    result["success"] = True
    return result


class SetupError(Exception):
    def __init__(self, operation, result):
        super().__init__(f"{operation}: {result['error_message']}")
        self.operation = operation
        self.result = {key: value for key, value in result.items() if key != "payload"}


class WorkerAborted(Exception):
    def __init__(self, result, cause):
        super().__init__(str(cause))
        self.result = result
        self.cause = cause


def prepare_user(base_url):
    email = f"bench-{uuid.uuid4().hex}@example.com"
    registered = request(
        base_url, "POST", "/api/auth/register", {"email": email, "password": "benchmark-pass-123"}
    )
    if not registered["success"]:
        raise SetupError("register", registered)
    logged_in = request(
        base_url, "POST", "/api/auth/login", {"email": email, "password": "benchmark-pass-123"},
        expected_status=200,
    )
    if not logged_in["success"]:
        raise SetupError("login", logged_in)
    return logged_in["payload"]["access_token"]


def worker(base_url, token, iterations, worker_id, stop_event=None):
    result = {"measurements": [], "completed_cycles": 0, "skipped_requests": 0}

    def record(iteration, method, response):
        result["measurements"].append({
            "worker_id": worker_id, "iteration": iteration, "method": method,
            **{key: value for key, value in response.items() if key != "payload"},
        })

    try:
        for index in range(iterations):
            if stop_event is not None and stop_event.is_set():
                break
            created = request(
                base_url, "POST", "/api/tasks", {"title": f"Benchmark task {index}"}, token
            )
            record(index, "POST", created)
            if not created["success"]:
                result["skipped_requests"] += 2
                continue
            task_id = created["payload"]["id"]
            listed = request(base_url, "GET", "/api/tasks", token=token)
            if listed["success"] and not any(item["id"] == task_id for item in listed["payload"]):
                fail(listed, "consistency_error", "Created task missing from list")
            record(index, "GET", listed)
            deleted = request(base_url, "DELETE", f"/api/tasks/{task_id}", token=token)
            record(index, "DELETE", deleted)
            if listed["success"] and deleted["success"]:
                result["completed_cycles"] += 1
    except (Exception, KeyboardInterrupt) as exc:
        # Only this worker boundary catches unexpected errors, retaining partial data.
        # main prints the original traceback and marks the run aborted.
        raise WorkerAborted(result, exc) from exc
    return result


def percentile(values, percent):
    values = sorted(values)
    index = round((len(values) - 1) * percent / 100)
    return values[index]


def failure_counts(measurements):
    failures = [item for item in measurements if not item["success"]]
    return {
        "failures_by_status": dict(Counter(
            str(item["status"]) if item["status"] is not None else "no_response" for item in failures
        )),
        "failures_by_error_type": dict(Counter(item["error_type"] for item in failures)),
    }


def summarize(results, duration, concurrency, iterations, run_errors=None):
    """Aggregate measured task requests; registration/login are excluded."""
    measurements = [item for result in results for item in result["measurements"]]
    attempted = len(measurements)
    successful = sum(item["success"] for item in measurements)
    completed = sum(result["completed_cycles"] for result in results)
    methods = {}
    for method in EXPECTED_STATUS:
        samples = [item for item in measurements if item["method"] == method]
        latencies = [item["latency_ms"] for item in samples if item["success"]]
        methods[method] = {
            "n": len(samples),
            "successful_requests": len(latencies),
            "failed_requests": len(samples) - len(latencies),
            "mean_ms": statistics.mean(latencies) if latencies else None,
            "p50_ms": percentile(latencies, 50) if latencies else None,
            "p95_ms": percentile(latencies, 95) if latencies else None,
            **failure_counts(samples),
        }
    skipped = sum(result["skipped_requests"] for result in results)
    incomplete = concurrency * iterations - completed
    run_errors = run_errors or []
    run_status = "aborted" if run_errors else (
        "completed_with_errors" if attempted != successful or incomplete else "completed"
    )
    return {
        "run_status": run_status,
        "run_errors": run_errors,
        "concurrency": concurrency,
        "iterations": iterations,
        "duration_seconds": duration,
        "throughput_rps": attempted / duration if duration > 0 else None,
        "success_throughput": successful / duration if duration > 0 else None,
        "error_rate": (attempted - successful) / attempted if attempted else None,
        "expected_requests": 3 * concurrency * iterations,
        "attempted_requests": attempted,
        "successful_requests": successful,
        "failed_requests": attempted - successful,
        "skipped_requests": skipped,
        "unrecorded_requests": 3 * concurrency * iterations - attempted - skipped,
        "expected_cycles": concurrency * iterations,
        "completed_cycles": completed,
        "incomplete_cycles": incomplete,
        **failure_counts(measurements),
        "methods": methods,
        "measurements": measurements,
    }


def print_report(report):
    print(f"Run status: {report['run_status']}")
    print(f"Concurrency: {report['concurrency']}; cycles/user: {report['iterations']}")
    throughput = report["throughput_rps"]
    throughput_text = f"{throughput:.1f}" if throughput is not None else "n/a"
    print(f"Elapsed: {report['duration_seconds']:.2f}s; throughput: {throughput_text} req/s")
    for key in ("success_throughput", "error_rate"):
        print(f"{key}: {report[key] if report[key] is not None else 'n/a'}")
    for key in (
        "expected_requests", "attempted_requests", "successful_requests", "failed_requests",
        "skipped_requests", "unrecorded_requests", "expected_cycles", "completed_cycles", "incomplete_cycles",
    ):
        print(f"{key}: {report[key]}")
    for method, stats in report["methods"].items():
        if stats["successful_requests"]:
            print(
                f"{method:6} n={stats['n']:4} success={stats['successful_requests']:4} "
                f"mean={stats['mean_ms']:7.1f}ms "
                f"p50={stats['p50_ms']:7.1f}ms "
                f"p95={stats['p95_ms']:7.1f}ms"
            )
        else:
            print(f"{method:6} n={stats['n']:4} success=0 mean=n/a p50=n/a p95=n/a")
        print(f"  failures_by_status: {stats['failures_by_status']}")
        print(f"  failures_by_error_type: {stats['failures_by_error_type']}")
    for error in report["run_errors"]:
        print(f"Run error: {json.dumps(error, ensure_ascii=False)}")


def unexpected_error(stage, exc, worker_id=None):
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    return {
        "stage": stage,
        "worker_id": worker_id,
        "error_type": "interrupted" if isinstance(exc, KeyboardInterrupt) else "unexpected_error",
        "exception_type": type(exc).__name__,
        "error_message": str(exc) or type(exc).__name__,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=25, help="Create/list/delete cycles per user")
    parser.add_argument("--output-json", type=Path, help="Save summary and per-request measurements as JSON")
    args = parser.parse_args()
    if args.concurrency < 1 or args.iterations < 1:
        parser.error("concurrency and iterations must be positive")
    base_url = args.base_url.rstrip("/")

    results = []
    run_errors = []
    futures = {}
    pool = None
    started = None
    stop_event = Event()
    stage = "setup"
    worker_id = None
    try:
        tokens = []
        for worker_id in range(args.concurrency):
            tokens.append(prepare_user(base_url))
        stage = "measurement"
        worker_id = None
        started = time.perf_counter()
        pool = ThreadPoolExecutor(max_workers=args.concurrency)
        for index, token in enumerate(tokens):
            future = pool.submit(worker, base_url, token, args.iterations, index, stop_event)
            futures[future] = index
        wait(futures)
    except SetupError as exc:
        run_errors.append({
            "stage": "setup", "worker_id": worker_id, "operation": exc.operation, **exc.result,
        })
    except (Exception, KeyboardInterrupt) as exc:
        # Run boundary: keep the error visible, then save all available evidence.
        run_errors.append(unexpected_error(stage, exc, worker_id))
    finally:
        if run_errors:
            stop_event.set()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=bool(run_errors))

    # Read each future independently: a failed worker must not discard another's data.
    for future, index in futures.items():
        if future.cancelled():
            continue
        try:
            results.append(future.result())
        except WorkerAborted as exc:
            results.append(exc.result)
            run_errors.append(unexpected_error("worker", exc.cause, index))
        except (Exception, KeyboardInterrupt) as exc:
            run_errors.append(unexpected_error("worker", exc, index))
    duration = time.perf_counter() - started if started is not None else 0.0
    report = summarize(results, duration, args.concurrency, args.iterations, run_errors)
    print_report(report)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if report["run_status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
