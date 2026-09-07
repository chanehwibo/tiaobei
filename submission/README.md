# 挑战杯提交目录模板

本目录只保存结构和打包清单，不保存身份证件、报名表、签字授权、真实案例原件或平台回执。运行 `scripts/build_submission.py` 后，实际暂存包默认生成到 Git 忽略的 `dist/competition_submission_draft/`。

目录分为五部分：

1. `01_项目报告与PPT`：可编辑答辩稿、逐页讲稿和项目说明；
2. `02_技术方案与测试`：技术方案、测试报告、评测与兼容性证据；
3. `03_源代码与说明`：可复现源码、测试、样例和许可文件；
4. `04_演示视频`：人工录制并复核的最终视频；
5. `05_报名与外部证明`：盖章报名表、授权案例和真实环境证明。

当前五项证据位于`02_技术方案与测试/第五轮逐请求/`，Windows、V11及SDK各有子目录，避免同名JSON冲突。第三、四轮放在明确标记的历史目录。视频最长7分钟；已有V11客户机报告和旧ABI单探针不能替代出题方认可、完整原生集成或独立Judge。

最终结果分别位于 `Windows最终验收/` 和 `V11最终验收/`，初次通过与失败另存，不覆盖历史。封存后的独立解包复验和最终状态记录作为仓库外置审计，不写回已封存ZIP；包内任务清单是封存时快照。

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

`03_源代码与说明/project/` 保留项目原有相对目录，包含测试依赖的文档、固定证据、可编辑材料和打包清单；解压后可独立运行测试并再次生成草案。外部材料的文件名不能重复。

完成内容核验后，使用 K04 归档流程生成 SHA-256 清单。最终文件名、格式、大小和邮件主题必须以当届比赛通知为准。

开发机草案归档示例：

```powershell
python .\scripts\archive_submission.py `
  --staging ".\dist\competition_submission_draft" `
  --archive ".\artifacts\release\OS_Agent_记忆优化_开发机交付草案_INCOMPLETE.zip" `
  --allow-incomplete
```
