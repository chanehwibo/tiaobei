# 发布归档说明

该目录保存由 `scripts/archive_submission.py` 生成的归档证据。

当前仓库中的归档是开发机交付草案，文件名带 `INCOMPLETE`，因为真实演示视频、盖章报名表、授权案例和银河麒麟/SDK 报告尚未提供。它用于验证目录、哈希和归档流程，不能直接当作正式完整比赛包。

每次归档包含：

- `*.zip`：只读 ZIP，内部含逐文件 `SHA256SUMS.txt`；
- `*_CONTENTS_SHA256.txt`：归档内容逐文件摘要；
- `*.zip.sha256`：ZIP 本身摘要；
- `*_archive_report.json`：文件数、体积、完整性、只读状态和外部缺口。

只读属性在归档创建的本机设置，Git 克隆或复制到其他介质后可能不保留；文件内容是否一致以 SHA-256 校验为准。

校验 ZIP 摘要：

```powershell
$archive = ".\artifacts\release\OS_Agent_记忆优化_开发机交付草案_INCOMPLETE.zip"
$expected = (Get-Content "$archive.sha256" -Encoding UTF8).Split()[0]
$actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$actual -eq $expected
```

外部材料齐全后，应重新运行打包脚本生成 `ready_for_manual_review` 暂存目录，再生成不带 `INCOMPLETE` 的新归档；不要改名冒充或覆盖本草案。
