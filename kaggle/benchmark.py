"""Small repeatable CPU load test against a running Todo List API."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from http.client import HTTPException
from importlib import metadata
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from threading import Event
import time
import traceback
import urllib.error
import urllib.request
from urllib.parse import urlsplit
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


def request(base_url, method, path, body=None, token=None, expected_status=None, timeout=30):
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
            response = urllib.request.urlopen(req, timeout=timeout)
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


def prepare_user(base_url, timeout=30):
    email = f"bench-{uuid.uuid4().hex}@example.com"
    registered = request(
        base_url, "POST", "/api/auth/register", {"email": email, "password": "benchmark-pass-123"},
        timeout=timeout,
    )
    if not registered["success"]:
        raise SetupError("register", registered)
    logged_in = request(
        base_url, "POST", "/api/auth/login", {"email": email, "password": "benchmark-pass-123"},
        expected_status=200, timeout=timeout,
    )
    if not logged_in["success"]:
        raise SetupError("login", logged_in)
    return logged_in["payload"]["access_token"]


def worker(base_url, token, iterations, worker_id, stop_event=None, timeout=30):
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
                base_url, "POST", "/api/tasks", {"title": f"Benchmark task {index}"}, token,
                timeout=timeout,
            )
            record(index, "POST", created)
            if not created["success"]:
                result["skipped_requests"] += 2
                continue
            task_id = created["payload"]["id"]
            listed = request(base_url, "GET", "/api/tasks", token=token, timeout=timeout)
            if listed["success"] and not any(item["id"] == task_id for item in listed["payload"]):
                fail(listed, "consistency_error", "Created task missing from list")
            record(index, "GET", listed)
            deleted = request(base_url, "DELETE", f"/api/tasks/{task_id}", token=token, timeout=timeout)
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
    if "run_id" in report:
        print(f"Run ID: {report['run_id']}; started_at_utc: {report['started_at_utc']}")
        print(f"Timeout: {report['timeout_seconds']}s; warmup_iterations: {report['warmup_iterations']}")
        if report["warmup"] is not None:
            warmup = report["warmup"]
            print(f"Warm-up: {warmup['run_status']}; requests: {warmup['attempted_requests']}; "
                  f"completed_cycles: {warmup['completed_cycles']}")
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


def collect_metadata(concurrency, iterations, timeout, warmup_iterations):
    root = Path(__file__).resolve().parents[1]
    commit = dirty = None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
            check=True, timeout=5,
        ).stdout.strip() or None
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root,
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    versions = {
        dist.metadata["Name"]: dist.version
        for dist in metadata.distributions() if dist.metadata.get("Name")
    }
    return {
        "run_id": str(uuid.uuid4()),
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": commit, "git_dirty": dirty,
        "python_version": platform.python_version(),
        "dependency_versions": dict(sorted(versions.items())),
        "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "concurrency": concurrency, "iterations": iterations,
        "timeout_seconds": timeout, "warmup_iterations": warmup_iterations,
    }


def run_phase(base_url, tokens, iterations, timeout, stage):
    """Use the same workload for warm-up and measurement, with separate clocks/data."""
    results = []
    run_errors = []
    futures = {}
    pool = None
    started = time.perf_counter()
    stop_event = Event()
    try:
        pool = ThreadPoolExecutor(max_workers=len(tokens))
        for index, token in enumerate(tokens):
            future = pool.submit(worker, base_url, token, iterations, index, stop_event, timeout)
            futures[future] = index
        wait(futures)
    except (Exception, KeyboardInterrupt) as exc:
        # Run boundary: keep the error visible, then save all available evidence.
        run_errors.append(unexpected_error(stage, exc))
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
            run_errors.append(unexpected_error("worker" if stage == "measurement" else stage, exc.cause, index))
        except (Exception, KeyboardInterrupt) as exc:
            run_errors.append(unexpected_error("worker" if stage == "measurement" else stage, exc, index))
    duration = time.perf_counter() - started
    return summarize(results, duration, len(tokens), iterations, run_errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=25, help="Measured cycles per user")
    parser.add_argument("--warmup-iterations", type=int, default=0, help="Unmeasured warm-up cycles per user")
    parser.add_argument("--timeout", type=float, default=30, help="HTTP socket timeout in seconds")
    parser.add_argument("--output-json", type=Path, help="Save summary and per-request measurements as JSON")
    args = parser.parse_args()
    if args.concurrency < 1 or args.iterations < 1:
        parser.error("concurrency and iterations must be positive")
    if args.warmup_iterations < 0:
        parser.error("warmup-iterations must be nonnegative")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and greater than zero")
    try:
        url = urlsplit(args.base_url)
        safe_url = url.scheme in ("http", "https") and url.hostname and not (
            url.username is not None or url.password is not None or url.query or url.fragment
        )
    except ValueError:
        safe_url = False
    if not safe_url:
        parser.error("base-url must be HTTP(S), without credentials, query or fragment")
    base_url = args.base_url.rstrip("/")
    run_metadata = collect_metadata(args.concurrency, args.iterations, args.timeout, args.warmup_iterations)
    run_errors = []
    warmup = None
    worker_id = None
    try:
        tokens = []
        for worker_id in range(args.concurrency):
            tokens.append(prepare_user(base_url, timeout=args.timeout))
    except SetupError as exc:
        run_errors.append({
            "stage": "setup", "worker_id": worker_id, "operation": exc.operation, **exc.result,
        })
    except (Exception, KeyboardInterrupt) as exc:
        run_errors.append(unexpected_error("setup", exc, worker_id))

    if not run_errors and args.warmup_iterations:
        warmup = run_phase(base_url, tokens, args.warmup_iterations, args.timeout, "warmup")
        if warmup["run_status"] != "completed":
            run_errors.extend(warmup["run_errors"])
            run_errors.append({
                "stage": "warmup", "error_type": "warmup_failed",
                "error_message": "Warm-up did not complete successfully; measurement was not started",
            })
    if run_errors:
        report = summarize([], 0.0, args.concurrency, args.iterations, run_errors)
    else:
        report = run_phase(base_url, tokens, args.iterations, args.timeout, "measurement")
    report.update(run_metadata)
    report["warmup"] = warmup
    print_report(report)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if report["run_status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
