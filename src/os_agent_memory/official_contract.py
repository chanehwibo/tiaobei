"""Official rubric, separate from developer retrieval diagnostics."""
from __future__ import annotations

import math
import re

TARGETS = {
    "preference_accuracy": ("ge", .85),
    "knowledge_recall": ("ge", .85),
    "conflict_accuracy": ("ge", .88),
    "retrieval_p95_ms": ("le", 500.0),
    "sensitive_f1": ("ge", .90),
}
MIN_REQUESTS = 50


def environment_identity(system, release):
    """Reject similarly named distributions and names in arbitrary host paths."""
    identity = str(release.get("ID", "")).lower()
    name = str(release.get("NAME", "")).lower()
    galaxy = (system == "Linux" and identity in {"kylin", "kylin-desktop"}
              and not any(word in name for word in ("openkylin", "neokylin", "中标")))
    version = str(release.get("VERSION_ID") or release.get("VERSION", ""))
    v11 = galaxy and bool(re.match(r"^v?11(?:\D|$)", version, re.IGNORECASE))
    return {"is_galaxy_kylin": galaxy, "is_required_v11": v11}


def assess_official_metrics(metrics, request_counts):
    rows = {}
    for name, (operator, target) in TARGETS.items():
        value = metrics.get(name)
        count = request_counts.get(name, 0)
        numeric = type(value) in (int, float) and math.isfinite(value) and value >= 0
        numeric = numeric and (name == "retrieval_p95_ms" or value <= 1)
        enough = type(count) is int and count >= MIN_REQUESTS
        rows[name] = {
            "value": value, "target": target, "operator": operator,
            "requests": count, "minimum_requests": MIN_REQUESTS,
            "passed": bool(numeric and enough and (value >= target if operator == "ge" else value <= target)),
        }
    return {"metrics": rows, "all_targets_met": all(row["passed"] for row in rows.values()),
            "scope": "developer_held_measurements_not_official_certification"}
