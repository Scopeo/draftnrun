#!/usr/bin/env python3
"""
Memory profiling test script.

Runs repeated workloads against the local API and tracks RSS growth
to detect memory leaks.

Usage:
    python scripts/memory_profiling/run_memory_test.py --api-key <key> --iterations 10
    python scripts/memory_profiling/run_memory_test.py --api-key <key> --iterations 5 --base-url http://localhost:8000
"""

import argparse
import json
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_PROJECT_ID = "3f11f8b2-90e1-4037-88e9-0f105f17d19b"
DEFAULT_ENVIRONMENT = "production"


def get_headers(api_key: str) -> dict:
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


def get_snapshot(base_url: str, headers: dict) -> dict:
    resp = requests.get(f"{base_url}/debug/memory/snapshot", headers=headers)
    resp.raise_for_status()
    return resp.json()


def start_tracemalloc(base_url: str, headers: dict) -> dict:
    resp = requests.get(f"{base_url}/debug/memory/tracemalloc/start", headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_tracemalloc_diff(base_url: str, headers: dict, top_n: int = 25) -> dict:
    resp = requests.get(f"{base_url}/debug/memory/tracemalloc/diff", headers=headers, params={"top_n": top_n})
    resp.raise_for_status()
    return resp.json()


def get_gc_info(base_url: str, headers: dict) -> dict:
    resp = requests.get(f"{base_url}/debug/memory/gc", headers=headers)
    resp.raise_for_status()
    return resp.json()


def trigger_run(
    base_url: str,
    headers: dict,
    project_id: str,
    environment: str,
    input_data: dict,
    response_format: str | None = None,
) -> dict:
    url = f"{base_url}/projects/{project_id}/{environment}/run"
    params = {}
    if response_format:
        params["response_format"] = response_format
    resp = requests.post(url, headers=headers, json=input_data, params=params, timeout=300)
    result = resp.json()
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {result.get('detail', result)}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Memory profiling test runner")
    parser.add_argument("--api-key", required=True, help="API key for auth")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--environment", default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--settle-time", type=int, default=10, help="Seconds to wait after each run for GC")
    parser.add_argument(
        "--input",
        type=str,
        default='{"messages": [{"role": "user", "content": "Hello"}]}',
        help="JSON input for the run",
    )
    parser.add_argument(
        "--response-format",
        type=str,
        default=None,
        choices=["base64", "url"],
        help="Response format for file outputs",
    )
    args = parser.parse_args()

    headers = get_headers(args.api_key)
    input_data = json.loads(args.input)

    print("=" * 70)
    print("MEMORY PROFILING TEST")
    print("=" * 70)
    print(f"Target: {args.base_url}")
    print(f"Project: {args.project_id}")
    print(f"Iterations: {args.iterations}")
    print()

    # 1. Start tracemalloc
    print("[1/4] Starting tracemalloc...")
    try:
        tm = start_tracemalloc(args.base_url, headers)
        print(f"  tracemalloc started. RSS: {tm['rss_mb']} MB")
    except Exception as e:
        print(f"  WARNING: Could not start tracemalloc: {e}")

    # 2. Baseline snapshot
    print("[2/4] Recording baseline...")
    baseline = get_snapshot(args.base_url, headers)
    baseline_rss = baseline["rss_mb"]
    print(f"  Baseline RSS: {baseline_rss} MB")
    print(f"  Tracked objects: {baseline['total_tracked_objects']}")
    print()

    # 3. Run iterations
    print(f"[3/4] Running {args.iterations} iterations...")
    results = []
    for i in range(1, args.iterations + 1):
        snap_before = get_snapshot(args.base_url, headers)
        rss_before = snap_before["rss_mb"]

        print(f"  Run {i}/{args.iterations}: RSS before={rss_before:.1f}MB ", end="", flush=True)

        try:
            t0 = time.time()
            trigger_run(
                args.base_url,
                headers,
                args.project_id,
                args.environment,
                input_data,
                response_format=args.response_format,
            )
            duration = time.time() - t0
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({"run": i, "error": str(e)})
            continue

        snap_after = get_snapshot(args.base_url, headers)
        rss_after = snap_after["rss_mb"]
        spike = rss_after - rss_before

        # Wait for GC to settle
        time.sleep(args.settle_time)

        snap_settled = get_snapshot(args.base_url, headers)
        rss_settled = snap_settled["rss_mb"]
        retained = rss_settled - rss_before

        print(
            f"after={rss_after:.1f}MB spike=+{spike:.1f}MB "
            f"settled={rss_settled:.1f}MB retained=+{retained:.1f}MB ({duration:.1f}s)"
        )

        results.append({
            "run": i,
            "rss_before": rss_before,
            "rss_after": rss_after,
            "rss_settled": rss_settled,
            "spike_mb": round(spike, 2),
            "retained_mb": round(retained, 2),
            "duration_s": round(duration, 2),
        })

    print()

    # 4. Final analysis
    print("[4/4] Analysis")
    print("-" * 70)

    successful = [r for r in results if "error" not in r]
    if not successful:
        print("  No successful runs to analyze.")
        sys.exit(1)

    final_snap = get_snapshot(args.base_url, headers)
    total_growth = final_snap["rss_mb"] - baseline_rss
    avg_spike = sum(r["spike_mb"] for r in successful) / len(successful)
    avg_retained = sum(r["retained_mb"] for r in successful) / len(successful)

    print(f"  Baseline RSS:      {baseline_rss:.1f} MB")
    print(f"  Final RSS:         {final_snap['rss_mb']:.1f} MB")
    print(f"  Total growth:      +{total_growth:.1f} MB over {len(successful)} runs")
    print(f"  Avg spike/run:     +{avg_spike:.1f} MB")
    print(f"  Avg retained/run:  +{avg_retained:.1f} MB")
    print(f"  Leak rate:         ~{total_growth / len(successful):.2f} MB/run")
    print()

    # GC analysis
    print("  GC Analysis:")
    gc_info = get_gc_info(args.base_url, headers)
    print(f"    Unreachable collected: {gc_info['unreachable_collected']}")
    print(f"    gc.garbage count:      {gc_info['gc_garbage_count']}")
    if gc_info["gc_garbage_types"]:
        print(f"    gc.garbage types:      {gc_info['gc_garbage_types']}")
    print()

    # Top object types
    print("  Top object types (final):")
    for entry in final_snap["top_object_types"][:10]:
        print(f"    {entry['type']:30s} {entry['count']:>8d}")
    print()

    # Tracemalloc diff
    print("  Top tracemalloc allocations (since baseline):")
    try:
        tm_diff = get_tracemalloc_diff(args.base_url, headers)
        for entry in tm_diff["top_allocations"][:15]:
            print(f"    {entry['file']:60s} +{entry['size_diff_kb']:>8.1f} KB ({entry['count_diff']:+d} blocks)")
    except Exception as e:
        print(f"    Could not get tracemalloc diff: {e}")

    print()
    print("=" * 70)
    print("Done.")


if __name__ == "__main__":
    main()
