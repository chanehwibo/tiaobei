# 挑战杯提交目录模板

本目录只保存结构和打包清单，不保存身份证件、报名表、签字授权、真实案例原件或平台回执。运行 `scripts/build_submission.py` 后，实际暂存包默认生成到 Git 忽略的 `dist/competition_submission_draft/`。

目录分为五部分：

1. `01_项目报告与PPT`：可编辑答辩稿、逐页讲稿和项目说明；
2. `02_技术方案与测试`：技术方案、测试报告、评测与兼容性证据；
3. `03_源代码与说明`：可复现源码、测试、样例和许可文件；
4. `04_演示视频`：人工录制并复核的最终视频；
5. `05_报名与外部证明`：盖章报名表、授权案例和真实环境证明。

当前执行入口为 `docs/35_接管实施与交付记录.md` 和 `docs/36_正式评测资源与外部交接.md`。
允许列表已补入 `02_技术方案与测试/接管补验/`：T01至T03、Windows275项/17检查、
V11两轮275项测试但HTTP服务失败的完整记录，以及参赛者转述的认可来源。
每批证据分目录保存，同名JSON不覆盖；新测试依赖的两份固定报告也镜像到包内源码原路径。
当前V11核心仅7/8通过，当前版Office、最终新包及新HEAD CI尚未完成；
打包成功或包内测试通过均不能代替这些门禁，也不能把历史Office当作当前实测材料。
下文R08/C05和已有五个封存ZIP均为历史版本，保持原字节。

T05a已在私有实验室完成草案独立解包重建、275项测试和17项Windows工程检查，
115项源码及打包前78份接管证据摘要一致。复测后的15份报告及
`artifacts/verification/takeover/t05a_package_preflight.json`为包外审计，不回写被测ZIP，
也不视为最终新包封存或成功V11证明。

发布前另有`t06a_git_checkout.json`，记录其注明内容提交的558项文件、115项源码、
275项Windows测试和17项工程检查核对。该报告同样为包外审计，不代替后续新HEAD
远端CI；推送前快照与发布后核验的边界见第35号记录T06。

R08五项证据位于`02_技术方案与测试/第五轮逐请求/`，Windows、V11及SDK各有子目录，避免同名JSON冲突。第三、四轮放在明确标记的历史目录。视频最长7分钟；已有V11客户机报告和旧ABI单探针不能替代出题方认可、完整原生集成或独立Judge。

R08结果分别位于 `Windows最终验收/` 和 `V11最终验收/`，初次通过与失败另存，不覆盖历史。C03修复后的当前源码另有 `02_技术方案与测试/第五轮续作补验/`，分别存放Windows166项测试、V11实际166项测试、95项源码一致性、完整UTF-8演示及DOCX分页验收。首次表格文本误报也原样保留，不能只挑成功报告。PPT/DOCX正文仍引用明确标记的R08原始指标，排版修复后的材料摘要另有记录。

封存后的独立解包复验、Git检出核对和最终状态记录作为仓库外置审计，不写回已封存ZIP，避免自引用摘要；包内任务清单是封存时快照，最新结果见仓库 `docs/35_接管实施与交付记录.md`，历史结果见 `docs/29_续作任务清单.md` 与 `docs/33_第五轮交付复核.md`。

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
