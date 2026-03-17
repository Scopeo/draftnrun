import gc
import logging
import os
import platform
import resource
import subprocess
import tracemalloc
from typing import Optional

from fastapi import APIRouter

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/debug/memory", tags=["Debug Memory"])

_baseline_snapshot: Optional[tracemalloc.Snapshot] = None


def _get_current_rss_mb() -> float:
    """Return *current* RSS in MB (not peak)."""
    try:
        # Works on macOS and Linux — reads from kernel, not from peak counter
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())]).strip()
        return int(out) / 1024  # ps reports KB
    except Exception:
        # Fallback: peak RSS via getrusage (better than nothing)
        return _get_peak_rss_mb()


def _get_peak_rss_mb() -> float:
    """Return peak RSS in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if platform.system() == "Darwin":
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


@router.get("/snapshot")
def memory_snapshot():
    """Current + peak RSS, GC stats, top object counts by type."""
    current_rss = _get_current_rss_mb()
    peak_rss = _get_peak_rss_mb()

    gc_stats = gc.get_stats()
    gc_counts = gc.get_count()

    # Top 20 object types by count
    type_counts: dict[str, int] = {}
    for obj in gc.get_objects():
        t = type(obj).__name__
        type_counts[t] = type_counts.get(t, 0) + 1
    top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    return {
        "rss_mb": round(current_rss, 2),
        "peak_rss_mb": round(peak_rss, 2),
        "gc_stats": gc_stats,
        "gc_counts": {"gen0": gc_counts[0], "gen1": gc_counts[1], "gen2": gc_counts[2]},
        "gc_garbage_count": len(gc.garbage),
        "total_tracked_objects": len(gc.get_objects()),
        "top_object_types": [{"type": t, "count": c} for t, c in top_types],
    }


@router.get("/tracemalloc/start")
def tracemalloc_start():
    """Start tracemalloc and save a baseline snapshot."""
    global _baseline_snapshot
    if not tracemalloc.is_tracing():
        tracemalloc.start(25)  # 25 frames deep
    _baseline_snapshot = tracemalloc.take_snapshot()
    return {"status": "started", "rss_mb": round(_get_current_rss_mb(), 2)}


@router.get("/tracemalloc/diff")
def tracemalloc_diff(top_n: int = 25):
    """Diff current allocations against the baseline snapshot."""
    global _baseline_snapshot
    if _baseline_snapshot is None:
        return {"error": "No baseline snapshot. Call /tracemalloc/start first."}

    current = tracemalloc.take_snapshot()
    stats = current.compare_to(_baseline_snapshot, "lineno")

    top_stats = []
    for stat in stats[:top_n]:
        top_stats.append({
            "file": str(stat.traceback),
            "size_diff_kb": round(stat.size_diff / 1024, 2),
            "size_kb": round(stat.size / 1024, 2),
            "count_diff": stat.count_diff,
            "count": stat.count,
        })

    return {
        "rss_mb": round(_get_current_rss_mb(), 2),
        "top_allocations": top_stats,
    }


@router.get("/gc")
def gc_info():
    """GC stats, force collect, and report unreachable + garbage."""
    stats_before = gc.get_stats()
    unreachable = gc.collect()
    stats_after = gc.get_stats()

    return {
        "rss_mb": round(_get_current_rss_mb(), 2),
        "gc_stats_before_collect": stats_before,
        "gc_stats_after_collect": stats_after,
        "unreachable_collected": unreachable,
        "gc_garbage_count": len(gc.garbage),
        "gc_garbage_types": [type(obj).__name__ for obj in gc.garbage[:20]],
    }
