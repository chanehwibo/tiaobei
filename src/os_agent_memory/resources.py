"""Process resource snapshots without optional packages or model-size estimates."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import time


def _resident_memory() -> tuple[int | None, int | None, str]:
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize), "GetProcessMemoryInfo"
    values = {}
    for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] in {"VmRSS:", "VmHWM:"} and fields[2] == "kB":
            values[fields[0]] = int(fields[1]) * 1024
    return values.get("VmRSS:"), values.get("VmHWM:"), "proc_self_status"


def resource_snapshot() -> dict:
    error = None
    try:
        rss, peak, source = _resident_memory()
    except (OSError, ValueError, AttributeError) as exc:
        rss, peak, source, error = None, None, "unavailable", type(exc).__name__
    return {
        "wall_seconds": time.perf_counter(),
        "cpu_seconds": time.process_time(),
        "rss_bytes": rss,
        "lifetime_peak_rss_bytes": peak,
        "source": source,
        "error_type": error,
    }


def resource_usage(before: dict, after: dict) -> dict:
    wall = max(0.0, after["wall_seconds"] - before["wall_seconds"])
    cpu = max(0.0, after["cpu_seconds"] - before["cpu_seconds"])
    return {
        "wall_ms": round(wall * 1000, 3),
        "cpu_ms": round(cpu * 1000, 3),
        "cpu_percent_one_core": round(cpu / wall * 100, 3) if wall else None,
        "rss_before_bytes": before["rss_bytes"],
        "rss_after_bytes": after["rss_bytes"],
        "lifetime_peak_rss_bytes": after["lifetime_peak_rss_bytes"],
        "source": after["source"],
        "available": after["rss_bytes"] is not None,
        "error_type": after["error_type"],
        "scope": "current_process_only; excludes separate model servers and child processes",
        "peak_definition": "OS high-water mark since process start, not a per-workload peak",
    }
