# 挑战杯提交目录模板

本目录只保存结构和打包清单，不保存身份证件、报名表、签字授权、真实案例原件或平台回执。运行 `scripts/build_submission.py` 后，实际暂存包默认生成到 Git 忽略的 `dist/competition_submission_draft/`。

目录分为五部分：

1. `01_项目报告与PPT`：可编辑答辩稿、逐页讲稿和项目说明；
2. `02_技术方案与测试`：技术方案、测试报告、评测与兼容性证据；
3. `03_源代码与说明`：可复现源码、测试、样例和许可文件；
4. `04_演示视频`：人工录制并复核的最终视频；
5. `05_报名与外部证明`：盖章报名表、授权案例和真实环境证明。

## 构建草案

```powershell
python .\scripts\build_submission.py --allow-incomplete
```

草案会写入 `PACKAGE_STATUS.md` 和 `build_report.json`，逐项列出缺失的外部证据。草案不能作为“全部完成”的正式包。

## 构建完整暂存包

```powershell
python .\scripts\build_submission.py `
  --output .\dist\competition_submission_ready `
  --video "<最终演示视频路径>" `
  --registration-form "<盖章报名表路径>" `
  --real-case "<经授权脱敏的案例证明路径>" `
  --kylin-report "<真实银河麒麟与SDK验证报告路径>"
```

目标目录必须不存在，脚本不会覆盖旧包。只有四类外部材料均存在时，状态才会是 `ready_for_manual_review`；该状态仍不等于平台审核或邮件发送成功。

完成内容核验后，使用 K04 归档流程生成 SHA-256 清单。最终文件名、格式、大小和邮件主题必须以当届比赛通知为准。
