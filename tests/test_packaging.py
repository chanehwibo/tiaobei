from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_submission import DEFAULT_MANIFEST, PROJECT_ROOT, PackagingError, build_submission


class SubmissionPackagingTest(unittest.TestCase):
    def test_complete_package_requires_external_materials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "submission"
            with self.assertRaisesRegex(PackagingError, "缺少正式提交"):
                build_submission(
                    project_root=PROJECT_ROOT,
                    output=output,
                    manifest_path=DEFAULT_MANIFEST,
                    external_files={},
                )
            self.assertFalse(output.exists())

    def test_incomplete_draft_is_labeled_and_privacy_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "submission"
            report = build_submission(
                project_root=PROJECT_ROOT,
                output=output,
                manifest_path=DEFAULT_MANIFEST,
                external_files={},
                allow_incomplete=True,
            )

            self.assertEqual(report["status"], "incomplete_draft")
            self.assertEqual(report["display_status"], "已完成初版，待赛事验收")
            self.assertIs(report["competition_ready"], False)
            self.assertEqual(len(report["missing_external"]), 4)
            status = (output / "PACKAGE_STATUS.md").read_text(encoding="utf-8")
            self.assertIn("禁止改名或宣称为完整正式包", status)
            self.assertIn("已完成初版，待赛事验收", status)
            self.assertTrue((output / "03_源代码与说明" / "project" / "src" / "os_agent_memory" / "service.py").is_file())
            packaged_root = output / "03_源代码与说明" / "project"
            for required in (
                "submission/submission_manifest.json",
                "docs/12_部署手册.md",
                "docs/测试报告.md",
                "artifacts/verification/round3/final_verification.json",
                "artifacts/verification/round3/evidence_summary.json",
                "artifacts/verification/round5/evidence_summary.json",
                "artifacts/verification/round5/kylin/requests.json",
                "artifacts/verification/round5/native/legacy_runtime_started.json",
                "docs/32_第五轮验收报告.md",
                "scripts/generate_round5_materials.py",
                "config/embedding.hash.json",
                "src/os_agent_memory/dashboard.html",
                "deliverables/ppt/OS_Agent_记忆优化_答辩稿.pptx",
            ):
                self.assertTrue((packaged_root / required).is_file(), required)
            rebuilt = build_submission(
                project_root=packaged_root,
                output=Path(temporary) / "rebuilt",
                manifest_path=packaged_root / "submission/submission_manifest.json",
                external_files={},
                allow_incomplete=True,
            )
            self.assertEqual(rebuilt["status"], "incomplete_draft")
            self.assertTrue((output / "02_技术方案与测试/第五轮逐请求/V11初次通过/requests.json").is_file())
            self.assertTrue((output / "02_技术方案与测试/第五轮逐请求/V11初次失败/requests.json").is_file())

            paths = [path.relative_to(output).as_posix().lower() for path in output.rglob("*") if path.is_file()]
            self.assertFalse(any("case_studies/private" in path for path in paths))
            self.assertFalse(any(path.endswith((".sqlite", ".pyc", ".pem", ".key")) for path in paths))
            self.assertFalse(any(".egg-info/" in path for path in paths))
            self.assertFalse(any(path.endswith("/latest_report.json") or path == "latest_report.json" for path in paths))

    def test_explicit_external_files_are_copied_and_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            external = {}
            for key, name in {
                "video": "demo.mp4",
                "registration_form": "registration.pdf",
                "real_case": "case.pdf",
                "kylin_report": "kylin.pdf",
            }.items():
                path = base / name
                path.write_bytes(f"synthetic test fixture for {key}".encode())
                external[key] = path

            output = base / "submission"
            report = build_submission(
                project_root=PROJECT_ROOT,
                output=output,
                manifest_path=DEFAULT_MANIFEST,
                external_files=external,
            )

            self.assertEqual(report["status"], "ready_for_manual_review")
            persisted = json.loads((output / "build_report.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["missing_external"], [])
            self.assertTrue((output / "04_演示视频" / "demo.mp4").is_file())
            self.assertTrue((output / "05_报名与外部证明" / "registration.pdf").is_file())
