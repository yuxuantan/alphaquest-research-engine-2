"""Benchmark any normal optimization request through the real API, saving jobs.

Run only when the portal is otherwise idle; elapsed job time excludes queue wait.
Every measurement forces fresh reports and verifies metrics and CSV bytes against
the ordinary CSV reader. No strategy IDs, parameters or worker counts are fixed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
from urllib.request import Request, urlopen


def benchmark(url, request, workers, repeats, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)

    def fetch(path, body=None):
        operation = Request(url.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                            headers={"Content-Type": "application/json"})
        with urlopen(operation, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if "application/json" in response.headers.get("Content-Type", "") else raw

    settings = fetch("/api/optimizations/settings")
    if any(type(value) is not int or not 1 <= value <= settings["max_workers"] for value in workers):
        raise ValueError(f"Worker counts must be between 1 and {settings['max_workers']}.")
    measurements = []
    reference = None
    counts = list(dict.fromkeys(workers))
    plan = [(prepared, count) for count in counts for prepared in (False, True)]
    for prepared, count in plan:
        for repeat in range(repeats):
            body = {**request, "workers": count, "reuse_results": False, "prepare_data": prepared}
            job = fetch("/api/optimizations", body)
            path = f"/api/optimizations/{job['id']}"
            print(f"Started {job['id']}: prepared={prepared}, workers={count}, repeat={repeat + 1}", flush=True)
            while job["status"] in ("queued", "running"):
                time.sleep(.2)
                job = fetch(path)
            if job["status"] != "complete":
                (output / f"failed-{job['id']}.json").write_text(json.dumps(job, indent=2))
                raise RuntimeError(f"Benchmark job failed: {job.get('error')}")
            fingerprints = []
            for offset in range(0, job["total_trials"], 1000):
                for row in fetch(path + f"/results?limit=1000&offset={offset}")["items"]:
                    fingerprints.append({"trial": row["trial"], "parameters": row["parameters"], "metrics": row["metrics"],
                                         "csv_sha256": {kind: hashlib.sha256(fetch(f"/api/backtests/{row['run_id']}/exports/{kind}")).hexdigest()
                                                        for kind in ("trades", "equity")}})
            if reference is None:
                reference = fingerprints
            if reference != fingerprints:
                (output / f"parity-failure-{job['id']}.json").write_text(json.dumps({"reference": reference, "actual": fingerprints}, indent=2))
                raise ValueError("Results differ from the CSV baseline; inspect parity-failure evidence.")
            measurement = {"prepared": prepared, "workers": count, "repeat": repeat + 1, "job": job,
                           "fingerprints": fingerprints, "exact_parity": True}
            measurements.append(measurement)
            (output / f"job-{job['id']}.json").write_text(json.dumps(measurement, indent=2))
            (output / f"results-{job['id']}.csv").write_bytes(fetch(path + "/exports/results"))
            print(f"  {job['elapsed_seconds']:.3f}s; exact parity", flush=True)
    summary = [{"prepared": prepared, "workers": count,
                "median_seconds": statistics.median(m["job"]["elapsed_seconds"] for m in measurements
                                                    if m["prepared"] == prepared and m["workers"] == count)}
               for prepared, count in plan]
    result = {"request": request, "settings": settings, "repeats": repeats, "summary": summary,
              "measurements": measurements,
              "fastest_measured_workers": min((row for row in summary if row["prepared"]), key=lambda row: row["median_seconds"])["workers"]}
    (output / "verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--request", type=Path, required=True, help="Normal optimization POST body as JSON")
    parser.add_argument("--workers", default="1,4,6,7", help="Comma-separated counts within this host's displayed limit")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory; reports remain in the portal")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be >= 1")
    benchmark(args.url, json.loads(args.request.read_text()), [int(value) for value in args.workers.split(",")], args.repeats, args.output)


if __name__ == "__main__":
    main()
