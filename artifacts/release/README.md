# 发布归档说明

该目录保存由 `scripts/archive_submission.py` 生成的归档证据。

R08封存第五轮草案：`OS_Agent_第五轮_双环境_交付草案_INCOMPLETE.zip`。
338个内容文件，另含 `SHA256SUMS.txt`，ZIP体积1,112,103字节。
ZIP SHA256：`6bce17e442630fa5a3d2e45aef502f2896d8ae3ca1f91c9ce1be586526478da1`。
Windows和真实安装V11虚拟机各164项测试及冻结逐请求五项指标的原始结果已纳入包内，95个公开被测文件摘要一致。
独立解包重建、逐文件摘要、ZIP CRC和隐私审计见 `artifacts/verification/round5/package_integrity.json`；完整解包源码复验另见 `artifacts/verification/round5/package/`。

C03随后修复当前DOCX的重复页脚及独立列表编号，166项测试和11页实际视觉检查通过；该修复不在R08包内。旧ZIP保持原字节，只证明封存时版本。当前源码的新双环境及新包验收跟踪于C05，完成前不要把旧包当成最新版本。

前三轮ZIP均为历史证据，不改写。原 `OS_Agent_记忆优化_开发机交付草案_INCOMPLETE.zip` 是2026-09-05历史基线，不能当作本轮源码。

当前归档仍是 `INCOMPLETE` 草案：最终视频、盖章报名表、授权案例、赛事部署认可和完整真实Agent/SDK/Judge证据尚未齐备。已有V11客户机测试和原生单探针不替代上述验收。

封存后的解包复验、Git检出复核和最终任务状态作为外置审计保留，不写回ZIP，避免自引用摘要。包内TODO是封存时快照，最终状态以仓库最新 `docs/29_续作任务清单.md`、`docs/33_第五轮交付复核.md` 和实际CI运行记录为准。

每次归档包含：

- `*.zip`：只读 ZIP，内部含逐文件 `SHA256SUMS.txt`；
- `*_CONTENTS_SHA256.txt`：归档内容逐文件摘要；
- `*.zip.sha256`：ZIP 本身摘要；
- `*_archive_report.json`：文件数、体积、完整性、只读状态和外部缺口。

只读属性在归档创建的本机设置，Git 克隆或复制到其他介质后可能不保留；文件内容是否一致以 SHA-256 校验为准。

校验 ZIP 摘要：

```powershell
$archive = ".\artifacts\release\OS_Agent_第五轮_双环境_交付草案_INCOMPLETE.zip"
$expected = (Get-Content "$archive.sha256" -Encoding UTF8).Split()[0]
$actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$actual -eq $expected
```

外部材料齐全后，应重新运行打包脚本生成 `ready_for_manual_review` 暂存目录，再生成不带 `INCOMPLETE` 的新归档；不要改名冒充或覆盖本草案。
