#!/usr/bin/env python3
"""
Assert Locust's results against a threshold, from the CSV it already writes.

Locust's own exit code only says "did any request fail". It says nothing about
whether the service was *fast enough*, so a run where every request succeeds in
four seconds still passes. This reads the Aggregated row of
``<prefix>_stats.csv`` and fails on failures or on a p95 above the threshold.

  P95_THRESHOLD_MS  p95 ceiling in ms (default 750)
  MAX_FAILURE_RATE  tolerated failure fraction, 0..1 (default 0.0)

Usage: python3 check_locust_thresholds.py /tmp/locust-stats_stats.csv
"""

from __future__ import annotations

import csv
import os
import sys


def _num(row: dict, *names: str) -> float | None:
    """Locust has renamed these columns across versions; try each spelling."""
    for name in names:
        raw = row.get(name)
        if raw not in (None, "", "N/A"):
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def main(path: str) -> int:
    if not os.path.exists(path):
        print(f"::error::Locust stats file not found: {path}", file=sys.stderr)
        print("The load test produced no results - treating as failure.", file=sys.stderr)
        return 1

    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        print(f"::error::{path} has no rows - the load test recorded nothing", file=sys.stderr)
        return 1

    aggregated = next(
        (r for r in rows if (r.get("Name") or "").strip() == "Aggregated"), None
    )
    if aggregated is None:
        print("::error::No 'Aggregated' row in Locust stats", file=sys.stderr)
        return 1

    threshold = float(os.getenv("P95_THRESHOLD_MS", "750"))
    max_fail_rate = float(os.getenv("MAX_FAILURE_RATE", "0"))

    requests = _num(aggregated, "Request Count", "Requests") or 0.0
    failures = _num(aggregated, "Failure Count", "Failures") or 0.0
    p95 = _num(aggregated, "95%", "95%ile", "95th percentile")
    median = _num(aggregated, "Median Response Time", "50%")

    print(f"requests={requests:.0f} failures={failures:.0f} "
          f"median={median if median is not None else 'n/a'}ms "
          f"p95={p95 if p95 is not None else 'n/a'}ms "
          f"(threshold {threshold:.0f}ms)")

    problems: list[str] = []

    # Zero requests means the load generator never reached the service. That is
    # the exact failure mode this whole job used to hide, so it must not pass.
    if requests <= 0:
        problems.append("Locust recorded 0 requests - the load test never ran")

    if requests > 0:
        fail_rate = failures / requests
        if fail_rate > max_fail_rate:
            problems.append(
                f"failure rate {fail_rate:.1%} ({failures:.0f}/{requests:.0f}) "
                f"exceeds the allowed {max_fail_rate:.1%}"
            )

    if p95 is None:
        problems.append("no p95 column in Locust stats - cannot assert latency")
    elif p95 > threshold:
        problems.append(f"p95 {p95:.0f}ms exceeds threshold {threshold:.0f}ms")

    if problems:
        for problem in problems:
            print(f"::error::Performance check failed: {problem}", file=sys.stderr)
        return 1

    print("OK: performance within thresholds.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
