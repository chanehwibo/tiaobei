"""Build a fresh review package with current public material and reproducible source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_submission import build_submission, preflight_submission
from scripts.generate_review_materials import (
    CURRENT_EVIDENCE, DOCUMENTS, EVIDENCE, OFFICE_NAMES, OUTPUT, WINDOWS_EVIDENCE, verify_outputs,
)

MANIFEST = Path("submission/review_implementation_manifest.json")
WINDOWS_FILES = (
    "ablations.json", "action-readiness.json", "actions.json",
    "compatibility_windows_dev.json", "compatibility_windows_dev.md",
    "evaluation_v1_final.json", "evaluation_v2_test_final.json", "evaluation_v3.json",
    "final_verification.json", "final_verification.md", "official_diagnostics.json",
    "performance_windows_dev.json", "performance_windows_dev.md", "requests.json", "service_workload.json",
)


def make_manifest(legacy):
    historical = {source for section in legacy["public_sections"] for source in section["files"]}
    source_files = sorted(historical | set(legacy["source_section"]["files"])
                          | set(legacy["source_section"].get("docs", [])) | {MANIFEST.as_posix()})
    return {
        "schema_version": 1,
        "package_name": "OS_Agent_反馈落实_已完成初版_待赛事验收",
        "public_sections": [
            {"target": "00_阅读说明",
             "files": ["submission/REVIEW_README.md", "docs/37_出题方反馈落实.md", "docs/42_四项反馈复核与验收.md"]},
            {"target": "01_当前技术材料",
             "files": [*(str(OUTPUT / name).replace("\\", "/") for name in OFFICE_NAMES),
                       (OUTPUT / "current_report.md").as_posix(), (OUTPUT / "evidence_summary.json").as_posix(),
                       *DOCUMENTS, "docs/测试报告.md", "docs/27_真实SDK接入与证据边界.md"]},
            {"target": "02_复测证据/Windows",
             "files": [(WINDOWS_EVIDENCE / name).as_posix() for name in WINDOWS_FILES]},
            {"target": "02_复测证据/复杂场景/当前源码",
             "files": [(CURRENT_EVIDENCE / name).as_posix() for name in
                       ("complex_current.json", "complex_ablations.json", "complex_constraints.json",
                        "complex_policy_comparison.json", "constraints_policy_comparison.json",
                        "development_current.json", "development_challenge_current.json")]},
            {"target": "02_复测证据/复杂场景/初次开发诊断",
             "files": [(CURRENT_EVIDENCE / name).as_posix() for name in
                       ("development_initial.json", "development_challenge_initial.json",
                        "complex_policy_initial.json", "constraints_policy_initial.json")]},
            {"target": "02_复测证据/复杂场景/约束改动前基线",
             "files": [(EVIDENCE / "followup-20260910/complex_before.json").as_posix()]},
            {"target": "02_复测证据/复杂场景/历史等输出配对",
             "files": [(EVIDENCE / name).as_posix() for name in
                       ("complex_before.json", "complex_after.json", "complex_comparison.json", "complex_ablations.json")]},
            {"target": "02_复测证据/SDK",
             "files": [(EVIDENCE / "sdk_risk.json").as_posix(),
                       (CURRENT_EVIDENCE / "native_windows_discovery.json").as_posix(),
                       "artifacts/verification/round5/native/legacy_runtime_started.json"]},
            {"target": "02_复测证据/主办方认可记录",
             "files": ["artifacts/verification/x01-x02/organizer_acceptance_reported_20260909.json"]},
            {"target": "02_复测证据/材料校验",
             "files": [(CURRENT_EVIDENCE / name).as_posix() for name in
                       ("review_materials.json", "review_doc_render.json",
                        "review_ppt_render.json", "review_visual_review.json")]},
        ],
        "source_section": {
            "target": "03_源代码与说明/project",
            "files": source_files,
            "trees": sorted(set(legacy["source_section"]["trees"]) | {"data/dev"}),
            "docs": [],
        },
        "external_inputs": list(legacy["external_inputs"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight-only", action="store_true",
                        help="write/check the allowlist and validate planned links without staging or packaging")
    parser.add_argument("--preflight-report", type=Path)
    args = parser.parse_args(argv)
    if args.preflight_only == (args.output is not None):
        parser.error("choose --preflight-only or --output, never both")
    if args.preflight_report and not args.preflight_only:
        parser.error("--preflight-report requires --preflight-only")
    if args.preflight_report and args.preflight_report.exists():
        raise ValueError("refusing to overwrite preflight evidence")
    if args.output and args.output.exists():
        raise ValueError("refusing to overwrite a review package")
    checks = verify_outputs(ROOT, ROOT / OUTPUT)
    if not checks["passed"]:
        raise ValueError("current material verification failed: " + json.dumps(checks, ensure_ascii=False))
    legacy = json.loads((ROOT / "submission/submission_manifest.json").read_bytes())
    manifest = make_manifest(legacy)
    path = ROOT / MANIFEST
    if path.exists():
        if json.loads(path.read_bytes()) != manifest:
            raise ValueError("existing review manifest differs; review it before regenerating")
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    if args.preflight_only:
        report = preflight_submission(ROOT, path)
        if args.preflight_report:
            args.preflight_report.parent.mkdir(parents=True, exist_ok=True)
            with args.preflight_report.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    else:
        report = build_submission(
            project_root=ROOT, output=args.output, manifest_path=path, external_files={}, allow_incomplete=True,
        )
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False, indent=2))
    if "files" in report:
        print("files=" + str(len(report["files"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
