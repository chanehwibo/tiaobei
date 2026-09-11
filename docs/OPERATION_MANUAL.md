# OS Agent 多源融合记忆优化系统：傻瓜式测试操作指南

适用工程：挑战杯“揭榜挂帅”赛题 XA-202612，`os-agent-memory-optimizer`。

文档日期：2026-09-11。项目状态：**已完成初版，待赛事验收**。

本文面向第一次接触工程的同学、项目负责人、测试人员和答辩录屏人员，参照中国软件杯工程 `docs/OPERATION_MANUAL.md` 的组织方式编写。不要求先读源码，按步骤即可完成本地启动、网页操作、接口验证、自动测试、指标复测和证据检查。

每项操作尽量说明：

- 在哪个窗口操作。
- 复制什么命令、点击什么按钮。
- 成功时应看到什么。
- 哪些数值允许变化，哪些条件必须满足。
- 哪些拒绝是安全机制正常工作，哪些是真正的失败。
- 出错后先检查什么。
- 可以保留什么截图、日志或报告作为证据。
- 建议红框框选什么，以及旁边可直接使用的红字短句。

**这是内部操作手册，不是已经通过赛事验收的证明。** 本文含本机目录，录屏和正式匿名材料中不要暴露用户名、个人信息或私有资料。

## 0. 先看这一章

### 0.1 本手册对应什么，不对应什么

本工程是“记忆优化系统”，不是参考工程 SafeOps Agent 的复制版本。

| 项目 | 本工程实际情况 |
| --- | --- |
| 核心运行环境 | Python 3.10 或更新版本，核心运行依赖仅标准库 |
| 默认向量实现 | 本地 `HashEmbedding`，无需联网、模型下载或 API 密钥 |
| 默认检索策略 | `focused_evidence_v2` |
| 本地界面 | “端侧智能记忆优化演示台” |
| 登录认证 | 本地演示台没有生产级认证或 TLS |
| 多租户字段 | 用于数据作用域隔离，不等于登录身份认证 |
| 操作系统控制 | 网页不会实际重启电脑、修改系统配置或执行任意 Shell |
| Node.js | 仅可选的前端脚本语法和 DOM 引用检查，不是启动依赖 |
| Word/PPT | 已有交付文件，可直接审阅；运行记忆系统不依赖 Office |
| 真实麒麟 SDK | 独立接入与复测路线，不能用 Hash 结果替代 |
| 真实 Agent/Judge | 独立验收路线；fixture 自检不等于真实模型行动评测 |
| 本次交付操作 | 不打包、不上传，不自动推送仓库 |

不要照搬参考项目中的登录令牌、DeepSeek、MCP、25 个工具或审计签名命令。本工程没有这些同名入口。

### 0.2 测试路线怎么选

| 目的 | 建议阅读及执行 | 完成后能说明什么 |
| --- | --- | --- |
| 第一次跑起来 | 第 1、2、4、5 章 | 环境和核心交互能够运行 |
| 一次验证本地主要流程 | 第 1、3 章 | 演示、冻结五项、数据库和工程测试执行结果 |
| 对照网页和接口逐项检查 | 第 4 至 8 章 | 接入、偏好、冲突、隔离、拒答、遗忘和持久化 |
| 检查现有能力是否退化 | 第 9 至 12 章 | 自动回归、冻结五项、复杂集和逐请求不退化门禁 |
| 排查检索延迟 | 第 10 至 13 章 | 质量不被牺牲的前提下检查计时边界和 P95 |
| 检查麒麟或真实 SDK | 第 15 章 | 实际环境、接入状态及仍需补证的项目 |
| 审阅 Word、PPT | 第 16 章 | 当前版本、四个评分重点和材料核验 |
| 做整体验证与录屏 | 第 17 至 21 章 | 验证清单、故障处理、证据记录和演示顺序 |

时间取决于电脑、后台负载和规模。不要把“通常几分钟”当作必须完成的超时时间；复杂矩阵和全量测试可能明显更久。

**第一次不要同时运行所有命令。** 建议先完成网页路线，再关闭网页服务，最后串行运行性能测试。

### 0.3 全程使用三个窗口

```text
窗口 A：PowerShell，准备环境、建立数据库、保持 Web 服务运行
窗口 B：浏览器，打开演示台并点击按钮
窗口 C：另一个 PowerShell，发送 HTTP 请求、运行测试、查看报告

窗口 A 的服务占用终端属于正常现象。
不要在正在运行服务的同一个提示行后继续粘贴测试命令。
```

窗口 A 和 C 的变量互不共享。本手册会在需要新窗口时重新给出初始化命令。

### 0.4 不要把这些状态混为一谈

| 看到的现象 | 正确解释 |
| --- | --- |
| Python 命令返回 `0` | 该入口按它自己的约定结束；有些诊断入口不以质量是否达标决定退出码 |
| `release_gate.passed=true` | 冻结公开回归的数值、分母、配置和安全条件通过 |
| `all_targets_met=true` | 当前报告定义的目标通过，不自动扩大到其他数据、模型或平台 |
| `optimization_gates_passed=true` | 当前三策略配对比较通过，不表示旧实验也通过 |
| `official_validation_ready=false` | 不具备正式验收证据，不能手动改为 `true` |
| `competition_ready=false` | 赛事验收仍独立处理，不是网页故障 |
| 检索返回 HTTP 200 和 `[]` | 可能是正确拒答或正确隔离，必须结合问题和作用域判断 |
| 缺少租户返回 400 | 接口拒绝不完整请求，属于预期安全现象 |
| 越权确认返回 403 | 拒绝在另一个用户作用域执行遗忘，属于预期安全现象 |
| 原生 SDK 在 Windows 未接通 | 记录接入边界，不用 Hash 回退冒充接通 |

### 0.5 禁止为了“通过”而做的操作

1. 不修改冻结数据、答案标签、样本数量或评测阈值来凑成绩。
2. 不删除失败报告，不覆盖 `artifacts/verification/` 下的历史证据。
3. 不将公开合成数据、重复测量或 fixture 宣称为独立盲测。
4. 不把一次 SDK 探针当成 P95。
5. 不为启动演示关闭系统防火墙、开启公网访问或绑定 `0.0.0.0`。
6. 不删除用户正在使用的 Office `~$` 锁文件。
7. 不用 `taskkill /IM python.exe /F` 停止所有 Python 程序。
8. 不重置、清空或覆盖已有数据库来掩盖故障。
9. 不把这份指南中的“预期结果”直接抄成“本次实测结果”。

### 0.6 章节导航

| 阶段 | 直接跳转 |
| --- | --- |
| 准备 | [环境准备](#1-第一次运行准备环境) · [命令行自检](#2-不开网页先检查核心是否能运行) · [一键脚本](#3-可选一条脚本跑通本地检查) |
| 网页 | [启动与三个窗口](#4-启动网页窗口-abc-各做什么) · [网页逐项测试](#5-网页逐项测试) · [多源接入](#6-多源接入从事件到可检索知识) |
| 接口 | [检索与复杂证据](#7-http-检索作用域与复杂证据测试) · [遗忘与重启](#8-http-两阶段遗忘与数据库重启) · [自动回归](#9-自动化回归先确认功能没有退化) |
| 指标 | [冻结五项](#10-冻结五项指标从运行到看懂报告) · [复杂场景](#11-复杂场景完整召回拒答与干扰必须一起看) · [三策略对照](#12-三策略对照证明修复没有损害原有能力) |
| 性能与平台 | [性能与资源](#13-性能测试把服务http初始化和模型分开) · [行动评测](#14-行动评测先自检框架再谈真实-agent) · [麒麟与 SDK](#15-麒麟-v11-与真实-sdk独立复测路线) |
| 验收排错 | [Word/PPT 与评分重点](#16-检查最新-wordppt-和四个评分重点) · [整体本地核验](#17-整体本地核验通过哪些失败哪些) · [故障排查](#18-故障排查按屏幕现象处理) |
| 留证收尾 | [测试记录](#19-测试记录和证据保存) · [录屏路线](#20-510-分钟演示路线与录屏检查) · [结束与恢复](#21-结束测试下次恢复和最终清单) |

截图标注先看[红框与红字规则](#07-红框与旁边红字怎么加)；录屏时可直接查[常用标注速查表](#206-常用红框与红字速查)。

### 0.7 红框与旁边红字怎么加

下文的“建议旁边红字说明”是**你添加在截图或视频中的说明文案，不是程序输出**。在截图编辑器或录屏软件里把这段文字设为红色即可；Markdown 代码块不依赖阅读器能否显示彩色字。

统一操作：

1. 先实际执行本节步骤，确认结果符合本节判据，再截取真实窗口。不要框选本文的示例输出冒充实测。
2. 红框只圈关键结果，保留附近的命令、问题、作用域或配置，让人能看懂结果来自哪里。
3. 红字放在对应框右侧或下方空白处；没有空白时给截图加留白，不遮盖字段、正文、按钮或异常信息。
4. 以 1080p 成片为例，边框可用 2–3 像素，红字约 24–30 像素，按最终导出效果调整。白底可用深红 `#C00000`，深色终端可用亮红 `#FF6B6B`。
5. 每个框配一两句短语。一屏重点较多时拆成数张，不把几十行结果挤进一张图；完整原始报告另行保留。
6. 下文通过类文案**仅在本节全部相关判据实际成立时使用**。未运行、跳过、失败或结果不同，应改用对应的真实状态文案。
7. 时间、次数、分母和比例以这次截图对应的报告为准。不要把作者上一轮的 392、48.145、50.828 等数值硬贴到你自己的结果上。
8. 对比前后状态时保留同一问题、目标 ID 和作用域；确需隐藏 ID 时使用一致的遮挡方式，不破坏相同与不同的判断。
9. 保留原始截图，另存带红框红字的标注版；公开前遮挡个人目录、通知、账号、密钥和私有资料。

红色表示“提醒观众看这里”，不统一表示成功或失败：

| 实际状态 | 红字应表达什么 | 不能写成什么 |
| --- | --- | --- |
| 本节通过 | 当前样例、当前配置或本轮报告的具体结论 | 全部场景或正式赛事已通过 |
| 预期安全拒绝 | 缺字段、跨主体、过期等请求被正确拒绝 | 服务故障，或任意 400 都是安全通过 |
| 已知失败 | 输入与实际错误结果，保留失败状态 | 因为有返回或退出 0，所以成功 |
| 未执行／待复测 | 实际缺项及证据边界 | 0 ms、100%、已完成真实 SDK 验收 |
| 准备与说明 | 环境已设置、参数说明或数学算例 | 功能已经测过、指标已经达标 |

已有报告可以展示，但应注明运行日期和报告文件名；这次只补标注文案，不代表又执行了一轮测试。

## 1. 第一次运行：准备环境

### 1.1 打开窗口 A

操作：

1. 按 `Win` 键。
2. 输入 `PowerShell`。
3. 打开普通“Windows PowerShell”，一般不需要管理员权限。
4. 最大化窗口；录屏时把字号调到清晰可读。

正确现象：

```text
PS C:\Users\你的用户名>
```

命令前面的 `PS ...>` 是提示符，不要复制进命令。

建议红框框选：PowerShell 窗口标题和命令提示符，遮挡个人目录。

建议旁边红字说明：

```text
PowerShell 已打开，后续命令在此执行。
```

### 1.2 进入本工程根目录

在窗口 A 执行：

```powershell
$Project = 'C:\Users\CanhuiBao\Desktop\项目、活动、比赛\挑战杯 揭榜挂帅\os-agent-memory-optimizer'
Set-Location -LiteralPath $Project
Get-Location
```

成功标志：路径最后是 `os-agent-memory-optimizer`，不是上一级“挑战杯 揭榜挂帅”，也不是 `docs`。

建议红框框选：`Get-Location` 输出中的工程目录名；不公开完整个人路径。

建议旁边红字说明：

```text
已进入本赛题工程根目录。
```

本机目录中有中文、空格和顿号，必须保留引号。其他电脑要把 `$Project` 改为实际工程路径，不要照抄一个不存在的用户目录。

如果提示“找不到路径”，先在资源管理器中打开工程，复制地址栏的完整路径，再修改 `$Project`。

### 1.3 检查关键文件

```powershell
Test-Path -LiteralPath '.\pyproject.toml'
Test-Path -LiteralPath '.\src\os_agent_memory\cli.py'
Test-Path -LiteralPath '.\src\os_agent_memory\dashboard.html'
Test-Path -LiteralPath '.\data\samples\events.jsonl'
Test-Path -LiteralPath '.\data\eval\office_memory_eval_v2.json'
Test-Path -LiteralPath '.\config\embedding.hash.json'
Test-Path -LiteralPath '.\scripts\run_demo.ps1'
Test-Path -LiteralPath '.\scripts\evaluate_complex_retrieval.py'
```

正确结果：连续 8 个 `True`。

建议红框框选：8 条检查及其连续 8 个 `True`，不要只截最后一个。

建议旁边红字说明：

```text
启动所需的 8 个关键文件齐全。
```

任意一个是 `False` 都先停下检查目录和资料完整性。不要自行新建同名空文件让检查变成 `True`。

### 1.4 检查 Python

```powershell
python --version
```

本机编写指南时使用 Python 3.14.3；你的版本不必相同，但必须为 3.10 或更新版本。

建议红框框选：实际可用的 `python --version` 或 `py -3 --version` 输出。

建议旁边红字说明：

```text
Python 版本满足核心运行要求。
```

如果找不到 `python`，再检查：

```powershell
py -3 --version
```

若只有 `py -3` 可用，第 1.5 节建立虚拟环境时用 `py -3 -m venv .venv`。建立后始终使用虚拟环境中的 `$Py`，不再混用不同解释器。

两条都失败时，先安装 Python 3.10+，确认勾选加入 PATH，并重新打开 PowerShell。不要继续执行后面的命令。

### 1.5 建立独立虚拟环境

推荐使用工程自己的 `.venv`，避免修改其他项目的 Python 环境。

```powershell
if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '虚拟环境创建失败，先不要继续。' }
}
$Py = Join-Path $Project '.venv\Scripts\python.exe'
& $Py --version
```

正确现象：

- 首次创建可能数秒没有输出，等待命令提示符返回。
- 最后一条输出 Python 版本。
- 已有可用 `.venv` 时直接复用，不删除、不覆盖重建。

建议红框框选：`$Py` 指向工程 `.venv` 的设置及随后版本输出，个人路径须遮挡。

建议旁边红字说明：

```text
本次使用工程独立的 Python 环境。
```

`&` 是 PowerShell 的调用运算符：它让 PowerShell 执行 `$Py` 所指向的程序。只输入 `$Py` 只会显示路径，不会启动 Python。

本手册不要求运行 `Activate.ps1`。显式调用 `$Py` 可以避免执行策略和多个环境混淆。

### 1.6 设置编码和源码路径

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $Project 'src'
$env:PYTHONHASHSEED = '0'
$env:PYTHONDONTWRITEBYTECODE = '1'
```

没有输出是正常现象。

建议红框框选：本节设置命令及重新出现的提示符；本图只展示环境准备。

建议旁边红字说明：

```text
当前窗口已设置 UTF-8 编码与源码导入路径。
```

| 设置 | 用途 |
| --- | --- |
| UTF-8 | 减少中文输出和重定向乱码 |
| `PYTHONPATH` | 直接从当前工程 `src` 导入模块 |
| `PYTHONHASHSEED=0` | 固定哈希相关顺序；三策略严格比较要求记录该值 |
| `PYTHONDONTWRITEBYTECODE=1` | 避免测试时额外写入 `.pyc` 缓存 |

这些设置只影响当前窗口及它启动的子进程。新开窗口 C 后必须再设置一次。

后面的 `-B -X utf8 -S` 分别表示不写字节码、UTF-8 模式、不加载第三方 site 包。核心功能只需标准库，配合 `PYTHONPATH` 即可离线运行。

**材料工具需要第三方包，执行材料工具时不能照搬 `-S`。**

### 1.7 是否需要安装依赖

首次只测试记忆系统、HTTP 和工程 unittest：**可以跳过 pip 安装**，直接进入第 1.8 节。

需要注册项目命令或开发态安装时，可选执行：

```powershell
& $Py -m pip install -e .
$InstallExit = $LASTEXITCODE
if ($InstallExit -ne 0) { throw '安装失败。离线核心测试可采用第 1.6 节源码路径方式。' }
& $Py -m pip check
```

正确现象：安装成功；`pip check` 显示 `No broken requirements found.`。

建议红框框选：安装成功信息与 `No broken requirements found.`。跳过安装时不要使用此文案。

建议旁边红字说明：

```text
可选开发依赖已安装，未发现依赖冲突。
```

虽然核心没有第三方运行依赖，构建工具仍可能需要联网下载。网络受限时不要反复安装，也不要修改系统代理或随意切换不可信镜像；使用前述源码路径方式。

只阅读已有 Word/PPT 不需要安装材料依赖。材料结构核验的依赖和命令见第 16 章。

### 1.8 选择端口

本手册统一使用 `18765`，避免与参考工程常见的 `8765` 混淆：

```powershell
$Port = 18765
$Base = "http://127.0.0.1:$Port"
```

所有窗口和浏览器必须使用同一个端口。

建议红框框选：`$Port` 与包含 `127.0.0.1` 的 `$Base` 设置，不以赋值成功证明端口空闲。

建议旁边红字说明：

```text
演示限定本机回环地址，端口待预检确认。
```

如果第 2.1 节提示端口占用，可以改为 `18766`，重新执行预检，再同步修改窗口 C 和浏览器地址。

不要因端口冲突结束来源不明的进程。先换一个空闲端口。

### 1.9 创建本轮专用输出目录

```powershell
$RunName = 'manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$Run = Join-Path $Project ('artifacts\runtime\' + $RunName)
if (Test-Path -LiteralPath $Run) { throw '本轮目录已存在，请稍等一秒后重新执行本节。' }
New-Item -ItemType Directory -Path $Run -ErrorAction Stop | Out-Null
Write-Host "本轮编号：$RunName"
Write-Host "本轮目录：$Run"
Write-Host "服务地址：$Base"
```

输出示例，仅看格式：

```text
本轮编号：manual-20260911-132102
本轮目录：...\artifacts\runtime\manual-20260911-132102
服务地址：http://127.0.0.1:18765
```

**记下你自己的“本轮编号”。** 第 4.4 节窗口 C 要输入它，不能复制示例编号当作当前编号。

建议红框框选：本轮编号、输出目录末尾和服务地址；隐藏目录中的个人信息。

建议旁边红字说明：

```text
本轮已建立独立输出目录，旧证据继续保留。
```

本轮数据库、报告、日志都放在 `$Run` 中。`artifacts/runtime/` 被 Git 忽略，但这不代表它永远不会被第三方备份或被其他扫描器读取。

重要区别：

- 重新做一轮独立测试：新建一个 `$Run`。
- 验证数据库重启持久化：继续使用原 `$Run`，不能换成新目录。
- 同一报告文件已存在：换一个新文件名或新一轮目录，不删除旧报告后重跑冒充首次结果。

### 1.10 可选：记录终端日志

```powershell
Start-Transcript -LiteralPath (Join-Path $Run 'window-a.txt') -NoClobber
```

成功标志：提示正在开始记录，并显示日志路径。

建议红框框选：记录开始提示和 `window-a.txt` 文件名。

建议旁边红字说明：

```text
当前窗口开始记录本轮操作日志。
```

如果宿主不支持 Transcript，可跳过，使用后文生成的 JSON 报告。不要把“没有 Transcript”说成“没有测试结果”。

日志可能包含用户名和本机路径，只用于内部核查；结束时执行 `Stop-Transcript`。窗口 C 如需记录，请用另一个文件名 `window-c.txt`。

## 2. 不开网页，先检查核心是否能运行

### 2.1 运行 doctor 预检

在哪里：窗口 A，尚未启动 Web 服务时。

```powershell
& $Py -B -X utf8 -S -m os_agent_memory.cli doctor --workspace . --input data/samples/events.jsonl --suite data/eval/office_memory_eval_v2.json --host 127.0.0.1 --port $Port
$DoctorExit = $LASTEXITCODE
Write-Host "doctor 退出码：$DoctorExit"
```

必须看到：

```json
{
  "ready_for_local_demo": true,
  "blocking_failures": []
}
```

这是关键字段摘录，不是完整输出。退出码应为 `0`。

| 检查项 | 本地演示要求 |
| --- | --- |
| `python_3_10_or_newer` | 通过 |
| `sample_input_exists` | 通过 |
| `evaluation_suite_exists` | 通过 |
| `workspace_writable` | 通过 |
| `sqlite_fts5_available` | 通过 |
| `dashboard_port_available` | 通过 |
| `real_kylin_sdk_ready` | Windows 本地路线允许警告 |
| `real_galaxy_kylin_environment` | Windows 本地路线允许警告 |

最后两项是不同层次的验收条件。出现警告不代表 Windows 演示不能运行，也不代表可以宣称 SDK 或 V11 已通过。

建议红框框选：`ready_for_local_demo=true`、空的 `blocking_failures`、退出码 0，同时保留 SDK 和 V11 警告。

建议旁边红字说明：

```text
本地演示预检通过，SDK 与麒麟平台另行验收。
```

失败时：

- `blocking_failures` 非空：按 `checks` 中对应 `detail` 排查。
- 端口检查失败：更换端口；已经运行了自己的服务时先正常停止服务再做预检。
- SQLite FTS5 不可用：检查 Python 的 SQLite 构建，不修改测试跳过它。
- 退出码 `2`：预检存在阻断，不继续录制“启动成功”。

注意：doctor 会测试端口绑定。**服务已经运行时再做 doctor，该端口显示占用是正常现象。**

### 2.2 运行纯命令行样例

```powershell
& $Py -B -X utf8 -S -m os_agent_memory.cli demo --input data/samples/events.jsonl
$DemoExit = $LASTEXITCODE
Write-Host "demo 退出码：$DemoExit"
```

应该依次看到：

```text
== Memory Stats ==
== Preferences ==
== Search: 报销流程模板 ==
== Forget: 删除报销模板相关记忆 ==
== Smoke Evaluation ==
```

成功判据：

1. 退出码 `0`，没有 traceback。
2. 能显示偏好键，如 `output.language`、`output.verbosity`。
3. 检索结果包含报销相关模板及分数。
4. 遗忘输出包含 `confirmed=true`、目标数量和 `audit_id`。
5. 最后有 smoke evaluation 输出。

当前样例常见初始统计为 6 项偏好、4 条知识、1 条知识冲突。首次样例中遗忘 1 条报销知识后，知识数量变化是正常现象。

**本命令使用独立的内存对象。** 它不会打开或删除后面创建的 `web.sqlite`；其中的直接遗忘演示也不能代替 HTTP 两阶段确认测试。

`knowledge_search_latency_ms` 是这次小样例的诊断数值，不是 1 万条、80 个查询的正式 P95。

建议红框框选：五段标题、偏好值、检索记录、遗忘回执及退出码。

建议旁边红字说明：

```text
本地合成事件完成偏好提取、知识检索与可审计遗忘；此处为功能演示。
```

分成多张图时，可分别使用：

| 画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| Memory Stats | 统计标题与偏好、知识、冲突数量 | 合成事件已形成可检查的记忆状态。 |
| Preferences | 偏好键及当前值 | 当前偏好由输入事件提取，可逐项核对。 |
| Search | 报销标题与关键正文 | 本例报销知识已召回，正文可核验。 |
| Forget | 确认状态、数量及回执 ID | CLI 遗忘回执已返回；HTTP 两阶段另测。 |
| Smoke Evaluation | 诊断标题与实际数值 | 小样例诊断用于自检，不是正式性能指标。 |

### 2.3 需要查看命令帮助时

```powershell
& $Py -B -X utf8 -S -m os_agent_memory.cli --help
& $Py -B -X utf8 -S -m os_agent_memory.cli serve --help
& $Py -B -X utf8 -S scripts/evaluate_complex_retrieval.py --help
```

不同入口的参数不同。例如 `demo` 没有 `--embedding-config`，不要把 `serve` 的参数直接复制给 `demo`。

建议红框框选：对应入口的 `usage` 和参数列表，保留入口名。

建议旁边红字说明：

```text
当前入口的可用参数已列出，按对应帮助执行。
```

## 3. 可选：一条脚本跑通本地检查

这一章是便捷路线，与后面的逐项路线存在重复。已经执行过的测试不必为了凑次数重复运行。

### 3.1 执行一键脚本，但暂不启动网页

前提：

- 已完成第 1 章。
- `$Port` 未被占用。
- 本节三个输出路径不存在。

在窗口 A 执行：

```powershell
$DemoArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', '.\scripts\run_demo.ps1',
    '-PythonCommand', $Py,
    '-HostAddress', '127.0.0.1',
    '-Port', "$Port",
    '-ReportPath', (Join-Path $Run 'quick-legacy-v2.json'),
    '-RequestReportPath', (Join-Path $Run 'quick-frozen-requests.json'),
    '-StorePath', (Join-Path $Run 'quick-demo.sqlite'),
    '-NoServer'
)
powershell @DemoArgs
$QuickExit = $LASTEXITCODE
Write-Host "一键检查退出码：$QuickExit"
```

`ExecutionPolicy Bypass` 只用于这次子 PowerShell，不更改系统永久执行策略。

脚本依次执行：

1. Preflight。
2. Sample memory pipeline。
3. Legacy v2 diagnostic，历史诊断，不是最终质量门禁。
4. Frozen request quality gate。
5. Build SQLite v2 store。
6. Automated tests。
7. 输出结束提示。

成功时结尾应出现：

```text
Local demo verification finished.
Dashboard was not started because -NoServer was supplied.
```

退出码为 `0`。

建议红框框选：上述两个结束提示和“一键检查退出码：0”；须实际执行本章后再标注。

建议旁边红字说明：

```text
一键本地检查结束，本次未启动网页服务。
```

浏览器打不开是正常的，因为你明确传了 `-NoServer`。按第 4 章再启动网页。

### 3.2 查看脚本生成了什么

```powershell
Get-Item -LiteralPath (Join-Path $Run 'quick-legacy-v2.json'), (Join-Path $Run 'quick-frozen-requests.json'), (Join-Path $Run 'quick-demo.sqlite') | Select-Object Name,Length,LastWriteTime
$QuickReport = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $Run 'quick-frozen-requests.json') | ConvertFrom-Json
$QuickReport.release_gate | ConvertTo-Json -Depth 8
```

必须有三个非空文件；冻结报告 `release_gate.passed` 应为 `true`。

建议红框框选：三个文件的名称与非零长度，以及冻结报告 `passed=true`。

建议旁边红字说明：

```text
本轮报告与数据库已生成，冻结门禁通过。
```

历史 v2 输出可能有低于目标的诊断项。脚本已明确标注它不是当前冻结五项门禁，不要删掉该报告，也不要因此把历史低分写成当前冻结结果。

### 3.3 常见误用

| 做法 | 问题 |
| --- | --- |
| 每次直接用脚本默认输出路径 | 容易反复使用 `latest_*` 和同一个数据库，难以区分不同轮次 |
| 加 `-SkipTests` 后称全部测试通过 | 实际没有运行 unittest，必须记录“跳过” |
| 服务已运行时执行一键脚本 | 第一阶段的同端口 doctor 会失败 |
| 未等脚本结束就打开另一份性能评测 | 后台竞争会干扰时延 |
| 直接关闭窗口 | 可能导致本轮日志不完整；保留当前报告并另开新一轮 |

## 4. 启动网页：窗口 A、B、C 各做什么

### 4.1 建立专用网页数据库

在哪里：窗口 A。

```powershell
$WebDb = Join-Path $Run 'web.sqlite'
if (Test-Path -LiteralPath $WebDb) { throw 'web.sqlite 已存在。新演示换新一轮目录；重启验证不要重新建库。' }
& $Py -B -X utf8 -S -m os_agent_memory.cli build-store --input data/samples/events.jsonl --output $WebDb --embedding-config config/embedding.hash.json
$BuildExit = $LASTEXITCODE
Write-Host "建库退出码：$BuildExit"
```

成功标志：

- 退出码 `0`。
- 输出 `output` 指向本轮 `web.sqlite`。
- `stats` 中有知识和偏好。
- `Test-Path -LiteralPath $WebDb` 为 `True`。

建议红框框选：建库退出码、`web.sqlite` 文件名和 `stats` 中的知识与偏好。

建议旁边红字说明：

```text
合成样例已写入本轮独立数据库。
```

`quick-demo.sqlite` 和 `web.sqlite` 是不同文件。前者属于第 3 章脚本，后者用于本手册网页与接口测试。

### 4.2 启动前台服务

```powershell
& $Py -B -u -X utf8 -S -m os_agent_memory.cli serve --database $WebDb --host 127.0.0.1 --port $Port --embedding-config config/embedding.hash.json
```

应该出现：

```text
Memory dashboard: http://127.0.0.1:18765
```

端口以你实际设置为准。

此后窗口 A 不再返回 `PS ...>` 提示符，这是服务正在运行，不是卡死。把窗口 A 保持打开，转到浏览器。

建议红框框选：实际 `Memory dashboard:` 地址及服务终端；地址以本轮端口为准。

建议旁边红字说明：

```text
本地服务已启动，保持窗口运行并连接浏览器。
```

这里没有再次传 `--input`，因为数据库已经建立。重启验证也采用同一方式，避免把重复入库与恢复流程混在一起。

### 4.3 打开窗口 B：浏览器

1. 打开 Edge、Chrome 或其他现代浏览器。
2. 在地址栏输入 `http://127.0.0.1:18765`。
3. 按回车。
4. 核对页面标题是“端侧智能记忆优化演示台”。

建议红框框选：浏览器本地 HTTP 地址和“端侧智能记忆优化演示台”标题。

建议旁边红字说明：

```text
已通过本地 HTTP 服务打开记忆演示台。
```

注意：

- 是 `http`，不是 `https`。
- 不是 `file:///.../dashboard.html`。
- 不是其他工程的 `8765`，除非你有意修改了端口。
- 不需要账号、密码或登录令牌。
- 不向其他人公开此端口。

能看到页面但显示加载失败时，进入第 4.5 节区分 HTTP 服务和页面问题。

### 4.4 打开窗口 C，并重新设置变量

新开一个 PowerShell，复制执行：

```powershell
$Project = 'C:\Users\CanhuiBao\Desktop\项目、活动、比赛\挑战杯 揭榜挂帅\os-agent-memory-optimizer'
Set-Location -LiteralPath $Project
$Py = Join-Path $Project '.venv\Scripts\python.exe'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $Project 'src'
$env:PYTHONHASHSEED = '0'
$env:PYTHONDONTWRITEBYTECODE = '1'
$Port = 18765
$Base = "http://127.0.0.1:$Port"
$RunName = Read-Host '粘贴窗口 A 显示的本轮编号，如 manual-年月日-时分秒'
if ($RunName -notmatch '^manual-\d{8}-\d{6}$') { throw '编号格式不正确，请重新核对窗口 A。' }
$Run = Join-Path $Project ('artifacts\runtime\' + $RunName)
if (-not (Test-Path -LiteralPath $Run -PathType Container)) { throw '本轮目录不存在，请检查编号和工程路径。' }
$WebDb = Join-Path $Run 'web.sqlite'
Write-Host "本窗口连接：$Base"
Write-Host "本窗口查看：$Run"
```

在 `Read-Host` 后输入本轮编号，不要输入完整路径，不要加引号。

如果窗口 A 改了端口，在执行本段前同步修改 `$Port`。

建议红框框选：“本窗口连接”和“本窗口查看”的实际输出，核对与窗口 A 一致。

建议旁边红字说明：

```text
接口窗口已对齐本轮服务地址与证据目录。
```

### 4.5 用只读接口确认服务存活

在窗口 C 执行：

```powershell
$Stats = Invoke-RestMethod -Method Get -Uri ($Base + '/api/stats') -TimeoutSec 10
$Stats | ConvertTo-Json -Depth 6
```

成功时返回包含以下键的 JSON：

```text
preferences
preference_versions
knowledge
knowledge_conflicts
pending_forget_plans
audit_events
conflict_decisions
```

数量取决于此前做过哪些操作，不要求每次一致。

建议红框框选：`/api/stats` 请求及返回的统计字段，不仅圈一个非零数字。

建议旁边红字说明：

```text
本地统计接口正常响应，数量随实际操作变化。
```

本工程没有 `/api/health` 入口。对不存在的 health 路径返回 404 不能据此判定服务故障。

`/api/stats` 是本地开发统计，不是按用户隔离的业务明细。生产环境不能直接照搬本演示台的鉴权方式。

### 4.6 先认识网页布局

顶部有四个按钮：

1. 恢复演示样例。
2. 场景一：偏好变化。
3. 场景二：规则冲突。
4. 场景三：安全遗忘。

下面是三个作用域输入框和“刷新”按钮：

```text
租户 / 用户 / 场景
```

主体六个区域：

| 区域 | 做什么 |
| --- | --- |
| 偏好画像与变化记录 | 看当前偏好和版本历史 |
| 知识检索 | 输入查询、查看正文和匹配分数 |
| 冲突前后对照 | 比较待决记录与已有记录，选择处理策略 |
| 安全遗忘 | 先预览目标，再确认软删除 |
| 记忆状态 | 查看当前作用域的知识状态和中期证据数量 |
| 多源接入 | 粘贴事件 JSON 数组，查看接收、重复和拒绝结果 |

窗口窄时区域会竖向排列，向下滚动即可，不是功能消失。

建议红框框选：当前要演示的区域标题及顶部作用域；逐区介绍时分屏标注。

建议旁边红字说明：

```text
查询、冲突与遗忘操作均需核对当前作用域。
```

## 5. 网页逐项测试

### 5.1 恢复可重复的合成演示场景

在哪里：窗口 B。

1. 点击顶部“恢复演示样例”。
2. 等待通知变成“演示样例已恢复。”。
3. 核对三个输入框自动变成：

```text
租户：local-demo
用户：presenter
场景：office
```

4. 查看“偏好画像与变化记录”中的语言、详略和输出形式。
5. 查看“记忆状态”中的“报销流程模板”。

正确现象：

- 能看到中文、简洁、表格等初始偏好。
- 有报销流程模板。
- 不要求整个数据库的全局统计回到零。

**恢复按钮仅清理保留的 `local-demo` 合成演示租户。** 它不是整个数据库的出厂重置，其他租户数据应保留。

不要把真实业务记录放进 `local-demo`，否则恢复演示样例会影响这些记录。

建议红框框选：恢复成功通知、三个作用域输入框、初始偏好与报销模板。

建议旁边红字说明：

```text
合成演示样例已恢复，当前作用域已切换。
```

### 5.2 测试知识检索

1. 在“知识检索”输入框中输入 `报销流程模板`。
2. 点击“检索”。
3. 查看返回标题、正文和匹配分数。

当前合成基线应返回的核心内容：

```text
报销流程模板：先核验票据和金额，再提交审批，最后归档。
```

成功判据：正文与问题相关，不只看“有一条结果”。

建议红框框选：查询词、报销模板标题及“核验、审批、归档”正文；不要只框分数。

建议旁边红字说明：

```text
报销流程已召回，正文与本例问题一致。
```

匹配分数不是答案正确率，不要把 `0.6` 解释为“60% 准确率”。具体分数和排序不能代替完整召回、拒答与干扰统计。

### 5.3 测试偏好变化与版本

1. 先确认当前详略是“简洁”。
2. 点击顶部“场景一：偏好变化”。
3. 等待“场景已接入，可查看变化及证据。”。
4. 再看“详略”，应变为“详细”。
5. 展开“查看版本历史”。
6. 比较当前值与历史值。

成功判据：

- 当前详略发生变化。
- 历史记录保留，版本或证据可以追踪。
- 不是只改页面文字，而是刷新后仍能看到变化。

重复点击同一场景可能被去重，不会每点一次都无限增加新版本。需要重新演示变化时，先点“恢复演示样例”，再点一次偏好场景。

建议红框框选：操作前的“简洁”、刷新后的“详细”及展开的版本历史，可用前后两张图。

建议旁边红字说明：

```text
显式偏好修正更新当前画像，旧证据和版本仍可追溯。
```

### 5.4 测试规则冲突隔离

1. 点击“场景二：规则冲突”。
2. 查看“冲突前后对照”。
3. 阅读“待决”和“已有”两段正文。
4. 应能看到“允许使用未登记移动介质”和“禁止使用未登记移动介质”的相反规则。
5. 查看“记忆状态”，至少有一条“待决冲突”。

成功判据：相反规则没有无条件一起成为默认可检索的有效规则；冲突进入可检查状态。

建议红框框选：“允许”与“禁止”两段正文及“待决冲突”状态。

建议旁边红字说明：

```text
相反规则已进入待决区，等待明确处置。
```

**先读正文，不要假设列表第一条一定时间最新。** 批量事件的聚合处理次序可能与原数组顺序不同。

### 5.5 选择正确的冲突决策

这一合成场景的演示目标是保留“禁止使用未登记移动介质”的规则。

先选中待决记录，再根据正文选择：

| 当前待决正文 | 已有正文 | 为保留“禁止”应选择 |
| --- | --- | --- |
| 允许使用未登记移动介质 | 禁止使用未登记移动介质 | 保留原规则 |
| 禁止使用未登记移动介质 | 允许使用未登记移动介质 | 采用新规则 |

然后点击“应用决策”，检查：

- 通知为“冲突决策已保存。”。
- 待决数量减少。
- “禁止”一条为“可用”。
- 被舍弃的“允许”一条为“已遗忘”。

建议红框框选：所选规则正文、决策保存通知、两条记录的状态，以及重新检索得到的“禁止”规则。

建议旁边红字说明：

```text
冲突按所选正文处理，本例保留禁止规则。
```

界面“采用新规则”对应 API 的 `accept_incoming`，实际含义是接受当前选中的待决项，**不是根据自然语言判断哪条更新**。因此必须结合正文选择，不能机械点击。

“按权威度与时效决策”在证据不足时可能继续保留人工复核；看到仍待决不一定是按钮失效。

“继续人工复核”本来就应保留待决状态，不应期待冲突消失。

若另外演示“继续人工复核”，框选所选决策与仍保留的待决状态，使用这句红字，不使用“冲突已解决”：

```text
本次选择人工复核，待决规则未强行覆盖原规则。
```

测试完可以重新检索外设相关规则，核对返回正文；不要只看状态徽标截图。

### 5.6 测试遗忘预览，不确认

前提：当前仍为 `local-demo / presenter / office`，报销模板尚未删除。

1. 先检索一次 `报销流程模板`，确认它存在。
2. 点击“场景三：安全遗忘”，或输入 `删除报销相关记忆` 后点“预览影响范围”。
3. 查看影响数量、目标标题、正文和有效期。
4. **此时不要点击确认。**
5. 回到知识检索，再点一次“检索”。

正确现象：报销模板仍可检索。

预览会生成待确认计划，但不会删除知识；待确认计划数量变化不等于已经删除。

建议红框框选：预览目标与有效期，以及预览后新一次检索仍返回的同一报销模板。

建议旁边红字说明：

```text
预览只展示影响范围，尚未执行删除。
```

当前默认有效期是 300 秒。过期后重新预览，不修改电脑时间来绕过有效期。

### 5.7 确认软删除并再次检索

1. 核对预览只包含你打算删除的合成报销记录。
2. 点击“确认软删除”。
3. 看到删除数量和审计回执。
4. 再次点击“检索”，而不是只盯着上一轮搜索结果。
5. 查看“记忆状态”中的目标状态。

正确现象：

- 显示“遗忘已保存，可重新检索核实。”。
- 有 `audit_id` 对应的回执标识。
- 目标成为“已遗忘”。
- 新一次报销检索不再返回该记录。

建议红框框选：保存通知、回执、目标“已遗忘”状态和重新检索后的空结果。

建议旁边红字说明：

```text
本例软删除已保存，目标不再被检索召回。
软删除不代表磁盘安全擦除。
```

页面可能保留上一次搜索的显示内容直到你重新检索。这不等于后端仍然召回被删除记录。

软删除是业务状态和检索可见性的删除，不是对磁盘、备份、截图或日志做物理擦除。

### 5.8 测试作用域切换

前提：已按第 5.5 节保留“禁止使用未登记移动介质”的规则。第 5.7 节删除的报销模板不能再用作隔离测试的正例。

1. 保持 `local-demo / presenter / office`，查询 `外设规则更新`。
2. 先确认能返回“禁止使用未登记移动介质”的有效规则；如果本来就没有结果，先回到第 5.5 节排查，不继续判定隔离成功。
3. 只把“用户”从 `presenter` 改为 `other-user`，点击“刷新”。
4. 再次查询相同的 `外设规则更新`，检查不出现 `presenter` 的记录。
5. 只把用户改回 `presenter`，刷新后再次查询，应重新出现原来的“禁止”规则。

成功判据是“本人有结果 -> 其他用户无结果 -> 本人仍有结果”。如果三个步骤都为空，不能证明作用域隔离。

建议红框框选：每张图同时圈“用户”、相同查询词和结果区，按下列顺序展示三张。

| 画面 | 建议旁边红字说明 |
| --- | --- |
| `presenter` 有禁止规则 | 本人作用域可检索到这条有效规则。 |
| `other-user` 无结果 | 相同查询切换用户后，不返回原用户知识。 |
| 切回 `presenter` 再次有结果 | 切回本人后结果恢复，本例作用域过滤有效。 |

三张合并展示时，建议旁边红字说明：

```text
本人可见、其他用户不可见、切回本人仍可见。
本例验证作用域过滤，不代表登录认证。
```

这里只验证数据作用域过滤。本地界面允许操作者填写租户和用户，因此它不是抵抗恶意客户端冒充身份的生产认证系统。

作用域改变后旧遗忘计划不能继续使用；请重新预览。不要拿不同用户的旧计划 ID 尝试“补完删除”。

### 5.9 网页测试顺序与恢复

一轮建议顺序：

```text
恢复样例 -> 基线检索 -> 偏好变化 -> 冲突检查与决策
-> 遗忘预览 -> 再检索仍存在 -> 确认 -> 再检索为空
```

需要第二次录屏时，重新点“恢复演示样例”即可。不要删除 `web.sqlite`，也不要覆盖整个证据目录。

下一章将用独立的 `guide-api` 租户测试接入，避免与网页预设场景互相影响。

## 6. 多源接入：从事件到可检索知识

### 6.1 先在网页接入一条合成事件

在哪里：窗口 B 的“多源接入”。

1. 把作用域改为 `guide-ui / tester / office`，点“刷新”。
2. 将“事件 JSON 数组”里的 `[]` 全部替换为以下内容。
3. 点击“校验并接入”。

```json
[
  {
    "id": "guide-ui-001",
    "tenant_id": "guide-ui",
    "user_id": "tester",
    "scene": "office",
    "source_type": "manual_config",
    "timestamp": "2026-09-01T10:00:00+08:00",
    "content": "重启演练流程模板：先保存文件，再检查任务，确认后进行演练，最后记录结果。",
    "metadata": {
      "title": "重启演练流程模板"
    }
  }
]
```

第一次、在本轮新数据库中操作，预期显示：

```text
接收 1 条，重复 0 条，拒绝 0 条。
```

展开“技术详情”，查看 `knowledge` 和 `promotion_decisions`。再搜索 `重启演练流程模板`，应出现对应正文。

建议红框框选：接收、重复、拒绝三个计数，以及随后检索到的模板标题和正文。

建议旁边红字说明：

```text
合成事件已接收，并形成可检索知识。
```

这是文本记忆，不会真的重启电脑。

页面上的作用域输入框不会自动重写事件内部的 `tenant_id` 和 `user_id`。两者必须对应，否则接入后当前页面可能看不到记录。

### 6.2 测试重复接入

不改 JSON，再点击一次“校验并接入”。

预期：

```text
接收 0 条，重复 1 条，拒绝 0 条。
```

再次检索不应因此多出一条相同知识。

只有重复计数变化而知识数量不增加，是去重成功，不是数据丢失。

建议红框框选：第二次接入的“接收 0、重复 1、拒绝 0”，配合未增加的知识结果。

建议旁边红字说明：

```text
重复事件已去重，未新增同一份知识。
```

同一个 ID 的内容修改属于“事件 ID 冲突”，不是同一条事件的正常更新。真实修改应采用新的事件 ID 和明确的时间、来源证据。

### 6.3 在窗口 C 定义统一 HTTP 辅助函数

后面的接口步骤都在窗口 C 执行，窗口 A 的服务须保持运行。

复制整个代码块，只需定义一次：

```powershell
function Post-MemoryJson {
    param([string]$Path, [hashtable]$Body)
    $Json = ConvertTo-Json -InputObject $Body -Depth 20
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Response = Invoke-RestMethod -Method Post -Uri ($Base + $Path) -ContentType 'application/json; charset=utf-8' -Body $Bytes -TimeoutSec 30 -ErrorAction Stop
    $Response | ForEach-Object { $_ }
}

function Save-GuideJson {
    param([string]$Path, [object]$Value)
    if (Test-Path -LiteralPath $Path) { throw "不覆盖已有记录：$Path" }
    $Json = ConvertTo-Json -InputObject $Value -Depth 30
    $Utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Json, $Utf8)
}
```

没有输出就是定义成功。

建议红框框选：两个完整函数定义后的提示符；本图只记录准备步骤，不作为接口测试通过的证据。

建议旁边红字说明：

```text
中文 JSON 请求与留证函数已定义。
```

这两个函数的用途：

- `Post-MemoryJson` 用 UTF-8 字节发送中文，避免 Windows PowerShell 5.1 的请求编码问题。
- 最后一行展开 HTTP 返回数组，确保后面用 `@(...).Count` 统计时，空数组真的是 0 条。
- `Save-GuideJson` 保存无 BOM 的 UTF-8 JSON，并拒绝覆盖旧文件。

不要把第一个函数简化成直接返回未经展开的 `Invoke-RestMethod` 数组。某些 PowerShell 版本会把一个空数组包装成“1 个数组对象”，让 `.Count` 看起来是 1，造成错误判断。

这些函数只存在于当前窗口。关闭窗口 C 后须重新定义。

### 6.4 用 HTTP 接入另一条独立事件

注意网页文本框接收数组，而 HTTP `/api/ingest` 接收的是包含 `records` 数组的对象，两者格式不同。

```powershell
$Records = @(
    @{
        id = 'guide-api-001'
        tenant_id = 'guide-api'
        user_id = 'tester'
        scene = 'office'
        source_type = 'manual_config'
        timestamp = '2026-09-01T10:00:00+08:00'
        content = '重启演练流程模板：先保存文件，再检查任务，确认后进行演练，最后记录结果。'
        metadata = @{ title = '重启演练流程模板' }
    }
)
$FirstIngest = Post-MemoryJson '/api/ingest' @{ records = $Records }
$FirstIngest | Select-Object accepted_records,rejected_records,duplicate_records | Format-List
$FirstIngest.promotion_decisions | ConvertTo-Json -Depth 8
```

本轮首次接入 `guide-api`，预期：

```text
accepted_records  : 1
rejected_records  : 0
duplicate_records : 0
```

再执行：

```powershell
$DuplicateIngest = Post-MemoryJson '/api/ingest' @{ records = $Records }
$DuplicateIngest | Select-Object accepted_records,rejected_records,duplicate_records | Format-List
```

预期接收 0、拒绝 0、重复 1。

两次输出分开标注，不能把首次接收的截图当成去重证据：

| 画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 首次接入 | 三个计数 `1 / 0 / 0`，保留字段名 | HTTP 首次接收 1 条，拒绝和重复均为 0。 |
| 原样重发 | 三个计数 `0 / 0 / 1`，保留字段名 | 原事件重发被识别为重复，未重复接收。 |

同一份合成数据从网页 `guide-ui` 和接口 `guide-api` 分别接入，作用域不同，应分别存在。不要把跨作用域的两条记录算成同一用户的重复。

### 6.5 看懂接入报告

| 字段 | 看什么 |
| --- | --- |
| `accepted_records` | 本次接受并继续处理的新事件数 |
| `duplicate_records` | 已处理事件或相同指纹的重复数 |
| `rejected_records` | 校验问题数；结合 `issues` 看原因 |
| `issues` | 输入格式、来源、事件 ID 等问题 |
| `promotion_decisions` | 从中期证据晋升到长期记忆的判定及原因 |
| `preferences` | 本批事件关联的偏好 |
| `knowledge` | 本批事件关联的结构化知识 |
| `stats` | 处理后的存储统计 |

**接收一条事件，不保证立即新增一条长期知识。**

例如：

- 证据不足的普通行为可能仍留在中期。
- 失败工具结果或高风险输入可能被降权、拒绝或不晋升。
- 只有一个标题、没有足够正文，不保证形成知识。
- 当前知识抽取是规则式的，正文需要足够长度，并包含流程、步骤、模板、规则等知识线索。
- 一段没有这些线索的纯英文普通短句，即使已接收，也可能不生成知识。

因此排错顺序是：先看 `issues`，再看晋升判定，再看 `knowledge`，最后查作用域和检索条件。

不要在 HTTP 返回 200 后就宣称“所有事件都成功转成了知识”。

建议红框框选：同一批报告的 `issues`、`promotion_decisions` 和 `knowledge`；长报告可分图保留批次关联。

建议旁边红字说明：

```text
接收与知识晋升分别核查，原因可追溯。
```

### 6.6 测试错误事件被记录

下面故意省略必需的正文，只在合成租户测试：

```powershell
$BadIngest = Post-MemoryJson '/api/ingest' @{
    records = @(
        @{
            id = 'guide-invalid-001'
            tenant_id = 'guide-api'
            user_id = 'tester'
            scene = 'office'
            source_type = 'manual_config'
            timestamp = '2026-09-01T10:01:00+08:00'
        }
    )
}
$BadIngest | Select-Object accepted_records,rejected_records,issues | ConvertTo-Json -Depth 8
```

预期：该事件不被接受，`rejected_records` 非零，`issues` 给出原因。

这是“批内单条数据不合格”的报告，不一定使整个 HTTP 请求返回 400。接口格式本身错误，例如把 `records` 写成字符串，则属于另一类请求错误。

可截图：拒绝计数和原因，不要只截图“处理完成”的通知。

建议红框框选：`accepted_records=0`、非零 `rejected_records` 和指向缺少正文的 `issues`。

建议旁边红字说明：

```text
缺少正文的事件被拒绝，原因已记录。
```

### 6.7 敏感数据与提示注入怎么测试

不要把真实手机号、证件、密钥、真实邮件或私人聊天粘贴进演示台来试脱敏。

本工程已有合成夹具，优先执行第 9 章中的敏感数据、安全对抗和请求质量测试，以及第 10 章冻结敏感实体 F1。

正确边界：

- 合成夹具通过不等于任意格式的真实敏感信息都能识别。
- 输入 JSON、浏览器记录和终端日志本身也可能含原文，后端脱敏不自动清理这些副本。
- 私有案例需授权、去标识并按 `case_studies/` 的流程处理，不直接替换公开样例。

建议红框框选：实际执行的安全测试名称、最终汇总和退出码，或冻结敏感实体报告；不框选真实敏感原文。

建议旁边红字说明：

```text
本次合成安全用例通过，不外推到任意真实输入。
```

只有完成对应测试且结果通过时使用此句；具体截图字段见第 9.2、10.4、10.6 节。

## 7. HTTP 检索、作用域与复杂证据测试

### 7.1 检索刚刚接入的中文知识

```powershell
$Query = @{
    query = '重启演练流程模板'
    tenant_id = 'guide-api'
    user_id = 'tester'
    scene = 'office'
    top_k = 3
}
$Hits = @(Post-MemoryJson '/api/search' $Query)
Write-Host "返回数量：$($Hits.Count)"
$Hits | Select-Object memory_id,title,content,score,status | Format-List
```

在尚未执行第 8 章遗忘的情况下，应有 1 条相应模板。

成功判据：

- 标题和正文正确。
- 状态为 `active`。
- 返回的不是其他租户或其他主体的相似文本。

建议红框框选：`guide-api / tester / office` 查询条件、返回数量 1、模板标题与正文，以及 `active` 状态。

建议旁边红字说明：

```text
当前作用域召回 1 条有效模板，标题与正文匹配。
```

普通网页检索未显式指定时使用默认阈值 `0.265`。HTTP 默认 `top_k` 是 5，而本手册显式设为 3，与这里讨论的 `@3` 指标保持一致。

### 7.2 查看默认策略的证据归因

```powershell
$Hits | Select-Object title,evidence | ConvertTo-Json -Depth 10
```

应能看到 `evidence.policy` 为 `focused_evidence_v2`。

建议红框框选：知识标题、`evidence.policy` 和实际返回的来源、分数等证据字段。

建议旁边红字说明：

```text
默认聚焦证据策略生效，返回依据可查看。
```

其他字段如 `origin`、`seed_id`、`direct_score`、`document_score`、`passage_score` 或 `coverage` 用于说明分数和证据来源，具体组合随查询类型变化。

短关键词查找与完整问题的证据处理分支不同，不能要求每条结果的 `coverage` 都必须是一个非空数字。

“聚焦证据”仍主要基于词面和主题规则，不是通用语义蕴含模型。

### 7.3 测试另一个用户不能读到这条知识

```powershell
$OtherQuery = $Query.Clone()
$OtherQuery.user_id = 'other-user'
$OtherHits = @(Post-MemoryJson '/api/search' $OtherQuery)
Write-Host "其他用户返回数量：$($OtherHits.Count)"
```

应显示 `0`。HTTP 状态仍可以是 200。

建议红框框选：仅修改为 `other-user` 的条件和返回数量 0；与第 7.1 节本人返回 1 条的截图配对。

建议旁边红字说明：

```text
同一查询切换用户后返回为空，本例作用域过滤有效。
```

同理可以复制 `$Query`，把租户改为一个未接入数据的合成租户，结果应为空。不要同时把租户和用户都改掉后就认为分别验证了两种隔离；每次只改一个条件更容易定位问题。

### 7.4 测试缺少作用域被拒绝

下面是故意构造的错误请求：

```powershell
try {
    Post-MemoryJson '/api/search' @{ query = '重启演练流程模板' } | Out-Null
    throw '异常：缺少作用域的请求没有被拒绝。'
} catch {
    if (-not $_.Exception.Response) { throw }
    $Status = [int]$_.Exception.Response.StatusCode
    if ($Status -ne 400) { throw }
    Write-Host "符合预期：HTTP $Status，缺少作用域被拒绝。"
}
```

正确现象：输出预期的 HTTP 400。

建议红框框选：缺少作用域的请求和“符合预期：HTTP 400”提示。

建议旁边红字说明：

```text
缺少作用域的请求被拒绝，符合本例预期。
```

这里不用 `$LASTEXITCODE` 判断 HTTP 请求。`Invoke-RestMethod` 是 PowerShell cmdlet，不是 Python 等原生进程，须检查异常和 HTTP 状态。

### 7.5 复杂接口示例：两份互补知识与近似型号

这一小例子检查接口参数、互补证据和明确的型号约束，**不并入冻结数据集，不产生正式指标**。

在窗口 C 执行：

```powershell
$EvidenceRecords = @(
    @{
        id = 'guide-seed'
        tenant_id = 'guide-evidence'
        user_id = 'tester'
        scene = 'office'
        source_type = 'manual_config'
        timestamp = '2026-09-01T09:00:00+08:00'
        content = '流程说明：calibration readout procedure.'
        metadata = @{ title = 'Sensor H7 procedure' }
    },
    @{
        id = 'guide-support'
        tenant_id = 'guide-evidence'
        user_id = 'tester'
        scene = 'office'
        source_type = 'manual_config'
        timestamp = '2026-09-01T09:01:00+08:00'
        content = '规则说明：two reviewers approve calibration.'
        metadata = @{ title = 'Sensor H7 requirements' }
    },
    @{
        id = 'guide-distractor'
        tenant_id = 'guide-evidence'
        user_id = 'tester'
        scene = 'office'
        source_type = 'manual_config'
        timestamp = '2026-09-01T09:02:00+08:00'
        content = '流程说明：calibration readout requires three reviewers.'
        metadata = @{ title = 'Sensor H70 procedure' }
    }
)
$EvidenceIngest = Post-MemoryJson '/api/ingest' @{ records = $EvidenceRecords }
$EvidenceIngest | Select-Object accepted_records,rejected_records,duplicate_records | Format-List
Write-Host "本批关联知识数量：$($EvidenceIngest.knowledge.Count)"
```

首次应接收 3 条，关联 3 条知识。重复执行则应查看重复计数，不再期待接收 3 条。

建议红框框选：三个接入计数、关联知识数量 3，以及输入中的两条 H7 和一条 H70。

建议旁边红字说明：

```text
两份 H7 证据与一份 H70 干扰已接入。
```

接下来提出一个同时需要“流程”和“审批要求”的问题：

```powershell
$EvidenceQuery = @{
    query = 'what calibration readout and reviewers are required for sensor h7'
    tenant_id = 'guide-evidence'
    user_id = 'tester'
    scene = 'office'
    top_k = 3
    min_score = 0.265
    required_terms = @('Sensor H7')
    evidence_policy = 'focused_evidence_v2'
}
$EvidenceHits = @(Post-MemoryJson '/api/search' $EvidenceQuery)
$EvidenceHits | Select-Object title,content,evidence | ConvertTo-Json -Depth 10
```

成功判据：

1. 返回 `Sensor H7 procedure`。
2. 返回 `Sensor H7 requirements`。
3. 不返回 `Sensor H70 procedure`。
4. 不能只有其中一份 H7 知识，就称“完整召回”。

这里的 `required_terms` 来自问题中明确指定的型号，不是从答案标签生成的条件。

建议红框框选：问题、`required_terms = @('Sensor H7')`，以及同时返回的两份 H7 标题和正文；保留完整返回以确认没有 H70。

建议旁边红字说明：

```text
显式型号约束下，两份 H7 证据完整召回。
```

### 7.6 复杂拒答：询问知识库没有支持的属性

```powershell
$UnsupportedQuery = $EvidenceQuery.Clone()
$UnsupportedQuery.query = 'what insurance settlement currency covers sensor h7'
$UnsupportedHits = @(Post-MemoryJson '/api/search' $UnsupportedQuery)
Write-Host "无支持属性的返回数量：$($UnsupportedHits.Count)"
```

预期为 `0`。

现有三份记录只有校准流程和审批要求，没有保险结算币种。即使它们都出现了 sensor 或 calibration，也不能拿来充当保险问题的依据。

这一结果说明该合成例子正确拒答，不代表任意未知问题都能可靠拒答。大范围结论必须看第 11、12 章。

建议红框框选：保险结算币种问题、保留的 H7 约束和返回数量 0。

建议旁边红字说明：

```text
本例缺少保险币种证据，正确返回为空。
```

### 7.7 保留一个额外的探索性反例

不要只测已知能够通过的写法。保留相同问题和数据，仅去掉调用方显式型号约束：

```powershell
$WithoutConstraint = $EvidenceQuery.Clone()
$WithoutConstraint.Remove('required_terms')
$UnconstrainedHits = @(Post-MemoryJson '/api/search' $WithoutConstraint)
$UnconstrainedHits | Select-Object title,content,score | Format-List
```

**编写本指南时，这个新增的中英混合 H7/H70 例子在没有显式约束时出现了错误主体返回，不能算通过。**

建议红框框选：去掉 `required_terms` 的操作、问题中的 H7 和错误返回的 H70 标题；不要隐藏失败结果。

建议旁边红字说明：

```text
新增反例：无约束时返回 H70，本例失败。
```

此句对应指南实测的失败现象。以后代码发生变化时按新实测更新记录，不能只修改红字把失败改成通过。

正确的测试记录方式：

- 保存约束开启和关闭的两份原始返回。
- 标注“新增探索性反例，词面主体识别的适用边界”。
- 不能把补上约束之后的成功回填成无约束成功。
- 不能把该例加入冻结集后修改旧分母或覆盖旧报告。
- 也不能因为冻结 168 个复杂请求通过，就删除这个额外失败。

该例属于指南实测发现的额外输入风险；本次只编写操作文档，没有改运行算法。复核记录见[第 48 号文档](48_测试操作指南核验.md)。

保存记录：

```powershell
Save-GuideJson (Join-Path $Run 'http-evidence-example.json') @{
    scope = 'manual_exploratory_example_not_frozen_benchmark'
    constrained = $EvidenceHits
    unsupported = $UnsupportedHits
    unconstrained = $UnconstrainedHits
}
```

### 7.8 接口错误速查

| 现象 | 含义或先查什么 |
| --- | --- |
| 200 + `[]` | 无足够证据、作用域不匹配或条件过滤；结合真值判断 |
| 400 | 缺少字段、参数类型错误、无效模式、错误 JSON、过期计划等 |
| 403 | 越权目标或跨来源修改请求 |
| 404 | 路由不存在，先核对路径 |
| 409 | 运行状态冲突，查看响应中的具体错误 |
| 503 | 存储操作失败，检查数据库路径、磁盘和权限 |
| 请求超时或连接失败 | 服务未运行、端口不一致、代理或系统网络策略 |

JSON 中布尔值写 `true/false`；PowerShell 哈希表中写 `$true/$false`。不要把 `"false"` 字符串传给 `hard_delete` 或 `reset`。

请求体有大小限制。不要一次粘贴真实大型日志测试极限；规模评测使用专门的受控脚本。

## 8. HTTP 两阶段遗忘与数据库重启

本章只操作第 6.4 节的合成租户 `guide-api`、主体 `tester`。窗口 A 保持运行，命令在窗口 C 执行。

前提：第 6.3 节函数已定义，第 7.1 节的 `$Query` 仍存在且能查到 1 条知识。

### 8.1 第一步：只做预览

```powershell
$Preview = Post-MemoryJson '/api/forget/preview' @{
    instruction = '删除重启演练相关记忆'
    tenant_id = 'guide-api'
    user_id = 'tester'
    hard_delete = $false
}
$Preview | ConvertTo-Json -Depth 8
```

重点检查：

| 字段 | 本例应看到什么 |
| --- | --- |
| `id` | 本次计划 ID，不要使用文档里的虚构 ID |
| `tenant_id` / `user_id` | `guide-api` / `tester` |
| `knowledge_ids` | 1 个目标知识 ID |
| `preference_ids` | 本例通常为空 |
| `hard_delete` | `false`，本次演示为软删除 |
| `confirmed` | `false` |
| `created_at` / `expires_at` | 创建时间及到期时间，按时间字符串中的时区理解 |

**看到目标不符合预期时，不执行确认。** 不要改成“删除全部”扩大范围来获得非零计数。

预览默认有效期是 300 秒。后续正常确认步骤请在有效期内完成；超时后重新预览，并重新检查目标。

建议红框框选：本次计划 ID、作用域、1 个目标 ID、`confirmed=false`、`hard_delete=false` 和有效期。

建议旁边红字说明：

```text
软删除计划已生成，范围可核对，尚未确认。
```

### 8.2 第二步：证明预览没有提前删除

```powershell
$BeforeConfirm = @(Post-MemoryJson '/api/search' $Query)
Write-Host "预览后、确认前，仍可检索数量：$($BeforeConfirm.Count)"
```

应仍为 `1`。

两阶段协议的意义是：先确认影响范围，再授权执行。仅仅返回一个计划 ID，而数据已经消失，属于失败。

建议红框框选：预览之后再次执行的查询及“仍可检索数量：1”。

建议旁边红字说明：

```text
仅预览不删除，目标知识仍可检索。
```

### 8.3 第三步：用错误主体确认，应拒绝

```powershell
try {
    Post-MemoryJson '/api/forget/confirm' @{
        plan_id = $Preview.id
        tenant_id = 'guide-api'
        user_id = 'other-user'
    } | Out-Null
    throw '异常：其他主体成功确认了本计划。'
} catch {
    if (-not $_.Exception.Response) { throw }
    $Status = [int]$_.Exception.Response.StatusCode
    if ($Status -ne 403) { throw }
    Write-Host "符合预期：HTTP $Status，跨主体确认被拒绝。"
}
```

成功判据：403，而不是 200。

如果得到 400，可能是 ID 为空、计划不存在或过期，不算证明了跨主体拒绝。先核对 `$Preview.id` 和时间。

再次用第 8.2 节查询，应仍有目标知识。被拒绝的请求不应造成部分删除。

建议红框框选：`other-user`、HTTP 403 提示和本人重新检索仍为 1 的结果。

建议旁边红字说明：

```text
跨主体确认被拒绝，原目标未被删除。
```

### 8.4 第四步：在正确作用域确认

确认这是本章合成数据，再执行：

```powershell
$ConfirmBody = @{
    plan_id = $Preview.id
    tenant_id = 'guide-api'
    user_id = 'tester'
}
$Receipt = Post-MemoryJson '/api/forget/confirm' $ConfirmBody
$Receipt | ConvertTo-Json -Depth 8
$AfterConfirm = @(Post-MemoryJson '/api/search' $Query)
Write-Host "确认后检索数量：$($AfterConfirm.Count)"
```

应看到：

- `confirmed=true`。
- `knowledge_count=1`。
- 非空 `audit_id`，计划 ID 与本次一致。
- 再次检索数量为 `0`。

如果计划到期，服务应拒绝。重新执行 8.1 至 8.4，使用新返回的 ID；不能修改数据库里的到期时间。

软删除会改变记录状态并同步检索索引，**不等于磁盘安全擦除**。历史备份、外部日志和截图不在这次删除范围内。

建议红框框选：本次计划的 `confirmed=true`、`knowledge_count=1`、`audit_id` 和确认后检索数量 0。

建议旁边红字说明：

```text
授权确认后目标不再召回，审计回执已生成。
本例为软删除，不是磁盘安全擦除。
```

### 8.5 第五步：重复确认，检查幂等回执

```powershell
$RepeatedReceipt = Post-MemoryJson '/api/forget/confirm' $ConfirmBody
[pscustomobject]@{
    first_audit_id = $Receipt.audit_id
    repeated_audit_id = $RepeatedReceipt.audit_id
    same_audit_id = ($Receipt.audit_id -eq $RepeatedReceipt.audit_id)
    confirmed = $RepeatedReceipt.confirmed
} | Format-List

Save-GuideJson (Join-Path $Run 'http-forget-receipt.json') @{
    preview = $Preview
    first_confirmation = $Receipt
    repeated_confirmation = $RepeatedReceipt
    results_after_confirmation = $AfterConfirm
}
```

正确结果：同一个审计 ID、相同的删除回执，不能再次扩大删除范围或产生第二次独立删除。

建议红框框选：首次与重复确认的审计 ID、`same_audit_id=True` 和 `confirmed=True`。

建议旁边红字说明：

```text
重复确认返回同一回执，不重复执行删除。
```

这里验证的是 `MemoryService` / HTTP 的幂等确认。不要拿底层 `MemoryStore.confirm_forget` 的直接调用行为替代服务接口约定。

### 8.6 第六步：停止并原路径重启

先回到窗口 A：

1. 按一次 `Ctrl+C`。
2. 等待 PowerShell 提示符返回。
3. 不运行 `build-store`，不运行演示重置。
4. 原样重启同一个数据库：

```powershell
& $Py -B -u -X utf8 -S -m os_agent_memory.cli serve --database $WebDb --host 127.0.0.1 --port $Port --embedding-config config/embedding.hash.json
```

如果窗口 A 已关闭，先按第 1.2、1.6 节恢复目录、编码和模块路径，再像第 4.4 节一样输入原 `$RunName`、恢复 `$Py`、`$WebDb` 和端口。**不要执行第 1.9 节创建新一轮目录。**

窗口 C 不要关闭，等待服务启动后执行：

```powershell
Invoke-RestMethod -Method Get -Uri "$Base/api/stats" -TimeoutSec 10
$AfterRestart = @(Post-MemoryJson '/api/search' $Query)
$RestartReceipt = Post-MemoryJson '/api/forget/confirm' $ConfirmBody
$RestartDuplicate = Post-MemoryJson '/api/ingest' @{ records = $Records }

[pscustomobject]@{
    forgotten_search_count = $AfterRestart.Count
    same_audit_id = ($RestartReceipt.audit_id -eq $Receipt.audit_id)
    accepted_on_reimport = $RestartDuplicate.accepted_records
    duplicates_on_reimport = $RestartDuplicate.duplicate_records
} | Format-List
```

本例应为：

```text
forgotten_search_count : 0
same_audit_id          : True
accepted_on_reimport   : 0
duplicates_on_reimport : 1
```

建议红框框选：原数据库路径对应的重启命令和上述四个实测字段；隐藏个人目录。

建议旁边红字说明：

```text
原库重启后遗忘与回执保留，重发事件不复活知识。
```

解释：

- 遗忘状态已持久化，服务重启后不会自行恢复。
- 已确认回执可重读，不是丢失后再执行一次。
- 原始事件的去重状态也保存了；重发同一事件不应偷偷复活已遗忘知识。

如果执行过第 7.5 节，再查未删除的另一个作用域：

```powershell
$SurvivingEvidence = @(Post-MemoryJson '/api/search' $EvidenceQuery)
$SurvivingEvidence | Select-Object title,content | Format-List
```

应仍有两份 H7 证据。这样才能同时证明“该删的没有回来、不该删的仍在”。

建议红框框选：重启后 `guide-evidence` 作用域仍返回的两份 H7 标题和正文。

建议旁边红字说明：

```text
另一个作用域的两份证据仍在，未被误删。
```

**未确认计划不作为保证持久化的对象。** 预览本身不强制落盘，服务重启前未确认的计划可能找不到；应重新预览。不要把已确认回执的持久化结论外推到所有临时状态。

### 8.7 可选：测试计划到期后被拒绝

使用仍保留的合成作用域 `guide-evidence`，只预览，不执行有效期内的确认：

```powershell
$Expiring = Post-MemoryJson '/api/forget/preview' @{
    instruction = '删除 calibration 相关记忆'
    tenant_id = 'guide-evidence'
    user_id = 'tester'
    hard_delete = $false
}
$Expiring | Select-Object id,expires_at,knowledge_ids | Format-List
```

保持服务不重启，等待超过 5 分钟。可以使用：

```powershell
Start-Sleep -Seconds 305
try {
    Post-MemoryJson '/api/forget/confirm' @{
        plan_id = $Expiring.id
        tenant_id = 'guide-evidence'
        user_id = 'tester'
    } | Out-Null
    throw '异常：到期计划被执行。'
} catch {
    if (-not $_.Exception.Response) { throw }
    $Status = [int]$_.Exception.Response.StatusCode
    if ($Status -ne 400) { throw }
    Write-Host "符合预期：HTTP $Status，请同时查看错误信息是否说明计划到期。"
    Write-Host $_.ErrorDetails.Message
}
```

应返回 400，错误信息指向计划过期。再执行第 8.6 节的 H7 检索，确认原知识仍在。

这一步是真实等待测试，可跳过；自动化测试已有对应的时间控制检查。未实际等待并验证时，记录“未执行”，不能勾选通过。

建议红框框选：到期时间、实际等待后的 HTTP 400、明确说明到期的错误信息，以及再次检索仍在的知识。

建议旁边红字说明：

```text
到期计划被拒绝，原知识仍保留。
```

仅在本步骤实际执行并满足上述条件后使用。未执行时红字写“本轮未执行真实等待过期测试”，不能使用成功文案。

HTTP 预览入口没有开放 `ttl_seconds` 参数。往 JSON 里加 `ttl_seconds=1` 不会缩短有效期，不要用它制造假过期测试。

### 8.8 硬删除、审计与安全限制

硬删除会移除当前存储中的目标对象，风险高于软删除。本手册默认不让新手对现有库手动演示硬删除，使用隔离临时目录的安全测试验证它。

不能据此宣称：

- SQLite 的所有旧页、WAL、副本或磁盘块已被安全覆写。
- 项目具有生产级身份认证。
- 任意关键词遗忘都能精确理解用户意图。
- 审计记录具有参考项目 SafeOps 的密码学链式签名能力。

本工程审计重点是作用域、操作、数量和可追踪回执。截图应保留本例回执与前后查询，不使用真实数据。

建议红框框选：回执中的作用域、操作、目标数量和审计 ID。

建议旁边红字说明：

```text
操作范围与结果可追溯，不代表密码学签名。
```

### 8.9 本章结束时，检查这一组状态

| 检查 | 预期 |
| --- | --- |
| 预览后查询 | 目标仍在 |
| 错误主体确认 | 403，目标仍在 |
| 正确确认 | 目标消失，审计 ID 非空 |
| 重复确认 | 返回相同回执 |
| 服务原库重启 | 遗忘状态与回执保留 |
| 重发同一事件 | 判为重复，不复活已遗忘知识 |
| 其他租户知识 | 仍可正常查询 |
| 过期计划，可选 | 拒绝执行，目标仍在 |

准备运行后续性能评测前，在窗口 A 正常停止网页服务。不要一边点击网页大量查询，一边把压力测试时延作为可比结果。

## 9. 自动化回归：先确认功能没有退化

### 9.1 使用哪个窗口

推荐窗口 C。已经停止窗口 A 的手工服务。

如果从本章开始：

1. 执行第 1.2 至 1.6 节初始化环境。
2. 执行第 1.9 节创建自己的 `$Run`。
3. 确认 `$Py`、`$Project`、`$Run` 均存在。

不需要先接入第 6 章的事件。自动化测试自己建立隔离数据，不依赖网页演示状态。

### 9.2 运行全部工程 unittest

```powershell
$TestLog = Join-Path $Run 'unit-tests.txt'
if (Test-Path -LiteralPath $TestLog) { throw '日志已存在，请换一个新文件名或测试轮次。' }
& $Py -B -X utf8 -S -m unittest discover -s tests -v 2>&1 | Tee-Object -FilePath $TestLog
$TestsExit = $LASTEXITCODE
Write-Host "工程测试退出码：$TestsExit"
Select-String -LiteralPath $TestLog -Pattern '^Ran [0-9]+ tests?', '^OK(?:\s|$)', '^FAILED(?:\s|$)' |
    ForEach-Object { $_.Line }
```

本次指南对应源码实际运行结果：

```text
Ran 392 tests in ...s

OK (skipped=1)
```

退出码为 `0`。本次耗时约 120 秒，只作等待时间参考，不是性能指标。

成功判据：

- 无 `FAIL` / `ERROR` 的最终汇总。
- 退出码为 0。
- 了解每个 `skip` 的原因，而不是只看“OK”。
- 测试数量与当前源码相符。以后新增测试后数量变化是正常的，不能为凑 392 删除测试。

`tests/` 下的 392 项与材料工具目录下的测试分开统计。它们也不是 392 个独立评测请求。

部分测试还会输出 fixture JSON，日志最后几行不一定是 unittest 汇总。上面的命令会定位 `Ran`、`OK` 或 `FAILED` 行；同时仍须保留完整日志与退出码。

建议红框框选：实际 `Ran ... tests`、最终 `OK`、退出码 0 和平台跳过原因；超出一屏时分图，不只圈最后一个 `ok`。

建议旁边红字说明：

```text
工程回归无失败，平台条件跳过项单列。
```

若本轮没有跳过项，可简写为“本轮工程回归全部通过”。测试数量以本轮实际输出为准。

### 9.3 红色文字、异常样例与退出码

测试中会故意构造：

- 未授权文件记忆接入。
- 跨租户读取和确认。
- SDK 未接通、错误参数、错误 JSON。
- 数据持久化失败与回滚。
- 打包路径越界或已有输出拒绝覆盖。

因此日志中可能有错误消息，但对应测试仍显示 `ok`。

Windows PowerShell 5.1 的 `2>&1` 还可能把 Python 的标准错误输出包装成 `NativeCommandError`，即使它只是 unittest 的普通进度文本。

判定顺序是：**最终汇总、原生命令退出码、具体失败用例**。既不能见红就判失败，也不能看到几行 `ok` 就忽略最后的 `FAILED`。

建议红框框选：被终端显示为红色的测试进度及同轮最终汇总、退出码，保留对应关系。

建议旁边红字说明：

```text
按最终汇总和退出码判定，不按终端字色判定。
```

### 9.4 只定位一类问题

完整回归通过前，局部测试不能替代全量测试。排障时可以单独运行：

```powershell
& $Py -B -X utf8 -S -m unittest discover -s tests -p 'test_web_server.py' -v
$WebTestsExit = $LASTEXITCODE
Write-Host "HTTP 测试退出码：$WebTestsExit"
```

更换 `-p` 后面的文件名即可选择以下范围：

| 文件名 | 适合定位什么 |
| --- | --- |
| `test_memory_pipeline.py` | 多源处理、偏好及知识主流程 |
| `test_incremental.py` | 增量存储、持久化与状态更新 |
| `test_security_adversarial.py` | 对抗输入、隔离、硬删除及重载 |
| `test_request_quality.py` | 冻结请求质量、提取和授权边界 |
| `test_request_contract.py` | 冻结分母、阈值和报告硬门禁 |
| `test_focused_evidence.py` | 新默认的聚焦证据与补全 |
| `test_query_subjects.py` | 查询中型号、版本等字面主体边界 |
| `test_evidence_constraints.py` | 显式约束处理 |
| `test_constraint_suite.py` | 复杂约束集 |
| `test_evidence_policy_comparison.py` | 三策略配对重算与不退化门禁 |
| `test_metric_privacy.py` | 数值指标与敏感信息扫描的区分 |
| `test_action_runtime.py` | 行动执行器边界 |

不要随意拼写不存在的测试模块名。若输出 `Ran 0 tests`，这不是通过了这一类测试；先核对文件名。

建议红框框选：本轮 `-p` 文件名、非零测试数量、最终 `OK` 和退出码 0。

建议旁边红字说明：

```text
所选测试子集通过，不替代完整回归。
```

### 9.5 一次执行安全与召回的重点子集

```powershell
$Patterns = @(
    'test_web_server.py',
    'test_incremental.py',
    'test_security_adversarial.py',
    'test_focused_evidence.py',
    'test_query_subjects.py',
    'test_evidence_policy_comparison.py'
)
foreach ($Pattern in $Patterns) {
    Write-Host "正在检查：$Pattern"
    & $Py -B -X utf8 -S -m unittest discover -s tests -p $Pattern -v
    if ($LASTEXITCODE -ne 0) { throw "此组失败，先定位：$Pattern" }
}
```

运行中不会改冻结数据或主数据库。测试产生临时隔离资源是正常现象。

建议红框框选：六组“正在检查”的文件名及各组非零测试数、最终 `OK`；可连续分图，不能只框最后一组。

建议旁边红字说明：

```text
六组重点回归均通过，覆盖安全与召回检查。
```

必须六组都实际执行且无失败时使用；中途抛错应保存对应失败组，不能套用此句。

### 9.6 可选：前端脚本语法与 DOM 引用检查

```powershell
node --version
```

能输出版本时，再执行：

```powershell
node scripts/check_dashboard.cjs
$DashboardExit = $LASTEXITCODE
Write-Host "前端静态检查退出码：$DashboardExit"
```

成功输出：

```text
Dashboard JavaScript syntax and DOM targets passed
```

建议红框框选：上述成功提示和“前端静态检查退出码：0”。

建议旁边红字说明：

```text
前端语法与 DOM 引用检查通过，界面仍需实看。
```

该检查证明脚本语法和引用目标一致，**不是截图验证或真实浏览器点击自动化**。第 5 章仍须手动操作检查布局、文字和交互。

找不到 Node 时，记为“可选前端静态检查未执行”，核心 Python 和网页仍可运行。不要为此修改工程运行依赖。

### 9.7 失败后先保留证据

1. 保留完整 `unit-tests.txt`。
2. 记录失败用例的完整名字。
3. 记录 Python 版本、当前 Git 提交和退出码。
4. 根据测试文件名做局部复现。
5. 修复后重跑局部，再跑完整测试。

不要改断言、提高容忍度、屏蔽测试或只提交成功日志。若源代码有变化，原有报告与 Word/PPT 的源码绑定需要重新检查。

建议红框框选：发生失败时的测试全名、断言差异、最终 `FAILED` 和非零退出码。

建议旁边红字说明：

```text
本轮存在回归失败，保留原始日志待定位。
```

## 10. 冻结五项指标：从运行到看懂报告

本章是最适合首次复核评分指标的路线。它不是主办方隐藏数据的正式验收。

### 10.1 运行前的四个条件

1. 手工 Web 服务已停，无其他评测脚本同时运行。
2. 使用默认 `config/embedding.hash.json` 对应的 HashEmbedding，不混入真实 SDK。
3. 当前目录是工程根目录，`$env:PYTHONHASHSEED='0'`。
4. 输出文件不存在。

关闭或保留 Office 由你决定，但不要在运行中修改源码、数据、配置和测试。记录机器上的明显后台负载；不需要强制结束系统进程。

### 10.2 一条命令运行冻结五项

```powershell
$FrozenOut = Join-Path $Run 'frozen-requests.json'
if (Test-Path -LiteralPath $FrozenOut) { throw '已有本轮报告，不覆盖。请使用新输出名称。' }
& $Py -B -X utf8 -S scripts/evaluate_requests.py --size 10000 --require-frozen --output $FrozenOut
$FrozenExit = $LASTEXITCODE
Write-Host "冻结五项退出码：$FrozenExit"
```

需要等待完成。控制台显示的是关键字段，完整逐请求证据写入 `$FrozenOut`。

本入口可能覆盖指定的旧输出，所以前面的存在检查不能省略。`--require-frozen` 同时检查指标和冻结约定，不只是“读了一份 JSON”。

建议红框框选：完整执行命令、`--size 10000`、`--require-frozen`、新报告路径和退出码。

建议旁边红字说明：

```text
冻结五项已运行，下一步核对报告与门禁。
```

本句只说明执行步骤结束；是否达标须继续检查第 10.3 节。

### 10.3 正确读取本次报告

```powershell
$Frozen = Get-Content -Raw -Encoding UTF8 -LiteralPath $FrozenOut | ConvertFrom-Json
$Frozen.metrics | Format-List
$Frozen.observation_counts | Format-List
$Frozen.safety_checks | Format-List
$Frozen.release_gate | ConvertTo-Json -Depth 10
Write-Host "正式验收就绪：$($Frozen.official_validation_ready)"
```

预期判据：

```text
冻结五项退出码：0
release_gate.passed = true
all_targets_met = true
official_validation_ready = false
```

最后一个 `false` 是正确的证据边界，不要改成 `true`。

建议红框框选：五项数值、观察数量、`release_gate.passed=true`、`all_targets_met=true` 和正式验收就绪 `false`。

建议旁边红字说明：

```text
本轮冻结指标与门禁通过，仍待正式赛事验收。
```

### 10.4 五项各在测什么

| 指标字段 | 本版分母 | 达标条件 | 不能误解成什么 |
| --- | --- | --- | --- |
| `preference_accuracy` | 68 个不同偏好请求 | >=0.85 | 不是单个槽位准确率或长期写入授权率 |
| `knowledge_recall` | 60 个正例知识请求 | >=0.85 | 不是 80 个全部查询的命中率 |
| `conflict_accuracy` | 60 个不同冲突请求 | >=0.88 | 不是仅检测到“有冲突”的比例 |
| `retrieval_p95_ms` | 80 个不同服务查询 | <=500 ms | 不是平均值、HTTP P99 或 SDK 探针 |
| `sensitive_f1` | 50 条不同合成敏感文本 | >=0.90 | 不是 50 个实体或第三方字符位置认证 |

其中 80 个检索查询包含 60 个正例、12 个无答案和 8 个作用域请求。60 是 80 的子集，不能把两个分母相加当作 140 个独立问题。

数值是 0 到 1 的比例时，`1.0` 表示 100%，不是 1%。时延字段单位已经是毫秒，不再乘 1000。

分项截图时，只有该项实际达到门槛才使用下列红字；数值保留程序原始输出，不手工替换。

| 画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 偏好 | `preference_accuracy`、68 个不同请求及其整题计分口径 | 偏好按整题键值集合计分，本轮准确率达标。 |
| 知识 | `knowledge_recall`、60 个正例和 `top_k=3` | 60 个正例的宏 Recall@3 达标。 |
| 冲突 | `conflict_accuracy`、60 个请求及检测与处置结果 | 冲突检测与处置联合计分，本轮达标。 |
| 时延 | `retrieval_p95_ms`、80 个服务查询及毫秒单位 | 服务检索 P95 达标，不含 SDK 与 HTTP 往返。 |
| 脱敏 | `sensitive_f1`、50 条合成文本和实体 TP/FP/FN | 合成文本的敏感实体微 F1 达标。 |

### 10.5 必须了解的计分规则

**偏好准确率：**

```text
完全正确的请求数 / 68
```

每个请求的预测键值集合必须与标签完全一致。多提取一个、少提取一个或值错误，都不能算该请求完全正确。额外的槽位 Precision/Recall/F1 只是诊断。

**知识 Recall@3：**

```text
每题 Recall@3 = 前 3 个返回中命中的相关知识数 / 该题全部相关知识数
最终值 = 60 个正例的 Recall@3 算术平均
```

空返回在有答案题中是漏召回，不能当拒答成功。入库漏掉标签知识时保留为失败，不从分母里删掉。

**冲突正确率：**

```text
冲突检测判断正确，且旧记录和新记录的处理状态均正确的请求数 / 60
```

仅报告检测到了冲突，但选择错误版本或没有进入人工队列，不够。

**敏感实体微 F1：**

```text
Precision = TP / (TP + FP)
Recall = TP / (TP + FN)
F1 = 2 * Precision * Recall / (Precision + Recall)
```

按实体类型、原始值和出现次数匹配；重复、重叠或多报也会受罚。报告同时检查脱敏结果是否仍保留应删除的敏感原值。

**P95：**

```text
把 80 个耗时从小到大排序，取第 ceil(0.95 * 80) = 76 个。
```

使用 nearest-rank，不是平均耗时，也不允许删掉慢请求后重算。首个请求另有 `cold_first_ms`，不意味着整台操作系统处于冷启动状态。

建议红框框选：报告中的实际计分配置、观察数量和对应逐请求数据；若截本节公式，明确标注为口径说明。

建议旁边红字说明：

```text
分母与计时边界固定，逐请求结果保留复核。
```

只展示公式时改用“评测口径说明，不是新增实测结果”，不要把计算示意当成绩截图。

### 10.6 五项之外的安全门禁

```powershell
$Frozen.safety_checks.PSObject.Properties |
    Select-Object Name,Value |
    Format-Table -AutoSize
```

全部应为 `True`：

| 字段 | 含义 |
| --- | --- |
| `durable_preferences` | 长期偏好写入结果符合授权和证据规则 |
| `knowledge_ingestion` | 标签知识按真实接入流程成功入库 |
| `no_scope_leaks` | 8 个作用域请求无泄漏 |
| `no_answer_85` | 12 个无答案请求正确率至少 85% |
| `no_redaction_leaks` | 合成敏感原值没有残留泄漏 |

`release_gate.checks` 还会检查冻结数据、分母、去重请求、检索配置、摘要与逐请求重算一致。

只截取五个好看的数字而不展示这些条件，不足以说明性能可信。

建议红框框选：五个安全字段的完整名称与全部 `True`，另保留 `release_gate.checks`。

建议旁边红字说明：

```text
五项安全检查通过，冻结约定另由门禁核对。
```

### 10.7 查看失败具体发生在哪一题

```powershell
$Frozen.preference.rows | Where-Object { -not $_.passed } | ConvertTo-Json -Depth 10
$Frozen.retrieval.rows | Where-Object { -not $_.passed } | ConvertTo-Json -Depth 10
$Frozen.conflict.rows | Where-Object { -not $_.passed } | ConvertTo-Json -Depth 10
$Frozen.sensitive.rows | Where-Object { -not $_.passed } | ConvertTo-Json -Depth 10
```

没有输出表示相应列表没有失败记录，不表示命令没运行。

单看慢查询：

```powershell
$Frozen.retrieval.rows |
    Sort-Object elapsed_ms -Descending |
    Select-Object -First 10 id,category,query,passed,elapsed_ms |
    Format-Table -Wrap
```

遇到失败，记录 `id`、输入、期望、实际返回和耗时，不修改答案集。

建议红框框选：已成功载入报告后执行的四类失败筛选命令，以及最慢 10 条的 ID、`passed` 和 `elapsed_ms`。

建议旁边红字说明：

```text
本轮未筛出失败请求，慢查询仍完整留证。
```

只有四类结果均无失败且报告确已载入时使用；空变量导致的无输出不算通过。有失败时改为“存在失败请求，已保留逐题结果与耗时”。

### 10.8 与现有材料中的数值怎么对照

当前 Word/PPT 固定证据中的五项：四项质量为 100%，P95 为 **48.145 ms**。

本指南编写期间另行实测：四项质量仍为 100%，P95 为 **50.828 ms**，所有冻结门禁通过。报告在本轮专用目录，详见[指南核验记录](48_测试操作指南核验.md)。

两次时延不同是正常的开发机测量波动，不能把新结果改写成旧值，也不必因此修改已经绑定固定证据的 Office。

你自己的复测只要求按相同口径判断是否达标，不要求精确复现 48.145 或 50.828。若跨过 500 ms，必须保留失败并按第 13、18 章排查。

建议红框框选：被比较的两份报告名称、所属轮次及各自 P95，不把不同轮次拼成同一张成绩单。

建议旁边红字说明：

```text
不同轮次分别留证，时延以各轮原始报告为准。
```

### 10.9 本章的合格截图

建议同一组截图包含：

1. 完整命令、规模 10000、报告输出位置。
2. 五个数值及各自分母。
3. 安全检查和 `release_gate.passed`。
4. `official_validation_ready=false`。

不要只截一行 100%，也不要把合成回归称为主办方认证。

建议红框框选：同轮报告的“指标、分母、安全门禁、验收边界”四组信息，可用连续四张图。

建议旁边红字说明：

```text
合成回归证据齐全，不等同于官方认证。
```

## 11. 复杂场景：完整召回、拒答与干扰必须一起看

### 11.1 两套复杂数据分别覆盖什么

| 数据集 | 不同请求 | 正例 | 无答案 | 作用域负例 | 多文档正例 |
| --- | --- | --- | --- | --- | --- |
| `complex_retrieval_v1` | 120 | 72 | 24 | 24 | 12，包含在 72 内 |
| `complex_constraints_v1` | 48 | 24 | 12 | 12 | 6，包含在 24 内 |
| 合计 | 168 | 96 | 36 | 36 | 18，包含在 96 内 |

原集包含近似实体、改写问题、条件、跨文档、长背景、全半角或编号变化，以及近似无答案和作用域问题。

约束集包含显式条件、多文档、混合日志上下文、全半角编号、不存在版本、关系缺证据和作用域问题。

数据规模与请求数量不同：1 万条说的是知识语料记录，不是 1 万道人工标注问题。

两套复杂评测直接装载受控知识快照以隔离检索问题，**不走完整事件抽取入库过程**。多源接入质量需结合第 6、9、10 章，不能用复杂检索全过替代。

建议红框框选：数据集名称、不同请求数和三类请求分布，不把执行次数当成新问题数量。

建议旁边红字说明：

```text
两套公开合成集共 168 个不同请求，重复轮次不扩充分母。
```

### 11.2 为什么必须保留相似干扰

测试矩阵包含：

```text
语料规模：1000、10000
相似填充比例：0、0.75
重复轮数：3
检索模式：hybrid
默认策略：focused_evidence_v2
top_k：3
min_score：0.265
HashEmbedding：256 维，ngram=2
```

`0.75` 的分母是**生成填充记录**，不是整份语料。原集固定 132 条文档、约束集固定 78 条文档始终保留，其中已经包含困难干扰。

因此：

- `0` 不等于“完全没有干扰”。
- `0.75` 不等于“全库精确 75% 都是错误答案”。
- 实际填充数量涉及取整，报告同时保存目标比例和实际比例。
- 不要把固定困难文档删掉再运行 0% 配置。

建议红框框选：本轮配置中的规模、填充比例、轮次、策略、阈值，以及固定文档数量。

建议旁边红字说明：

```text
两种规模与两档相似填充均测试，固定困难文档保留。
```

配置说明图只代表计划；只有第 11.6 节完整输出对应矩阵后，才使用“均测试”的文案。

### 11.3 运行原 120 请求的完整矩阵

在哪里：窗口 C；已停止手工服务，不与其他性能命令并行。

```powershell
$ComplexOut = Join-Path $Run 'complex-default.json'
if (Test-Path -LiteralPath $ComplexOut) { throw '已有复杂集报告，请换新输出。' }
$env:PYTHONHASHSEED = '0'
& $Py -B -X utf8 -S scripts/evaluate_complex_retrieval.py --evidence-policy focused_evidence_v2 --sizes 1000,10000 --hard-fractions 0,0.75 --rounds 3 --require-targets --output $ComplexOut
$ComplexExit = $LASTEXITCODE
Write-Host "原复杂集退出码：$ComplexExit"
```

运行中应看到每种配置的 `start ...` 和 `done recall=... no_answer=... p95_ms=...`。

一共有 4 个配置、每个 3 轮；每轮 120 个请求。1,440 次执行仍只有 120 个不同请求。

进度行只摘要显示该配置首轮的结果。不能只看 4 行进度就忽略后两轮，完整数据在 JSON 里。

建议红框框选：命令参数、四组完成进度、报告路径和退出码 0。

建议旁边红字说明：

```text
原复杂矩阵执行完成，三轮结果继续查 JSON。
```

### 11.4 运行约束 48 请求，同时检查开启与关闭

上一条命令完成后再执行：

```powershell
$ConstraintsOut = Join-Path $Run 'constraints-default.json'
if (Test-Path -LiteralPath $ConstraintsOut) { throw '已有约束集报告，请换新输出。' }
& $Py -B -X utf8 -S scripts/evaluate_complex_retrieval.py --suite complex_constraints_v1 --constraints compare --evidence-policy focused_evidence_v2 --sizes 1000,10000 --hard-fractions 0,0.75 --rounds 3 --require-targets --output $ConstraintsOut
$ConstraintsExit = $LASTEXITCODE
Write-Host "复杂约束集退出码：$ConstraintsExit"
```

一共有 8 个配置：2 个规模、2 个干扰比例、2 种约束状态；每个配置 3 轮。

`--constraints compare` 是把同样 48 个输入在约束开关两种模式下分别运行。不是添加新的标签，也不是把 48 算成 96 个独立问题。

关闭显式约束不等于关闭新策略所有主体保护：新策略仍可能从实际问题中识别字面的型号或版本，能力范围见第 7.7 节和第 45 号文档。

建议红框框选：`--constraints compare`、八组配置完成记录和退出码 0。

建议旁边红字说明：

```text
同样 48 个问题分别测试显式约束开启与关闭。
```

### 11.5 先看总门禁，不只看平均召回

```powershell
$Complex = Get-Content -Raw -Encoding UTF8 -LiteralPath $ComplexOut | ConvertFrom-Json
$Constraints = Get-Content -Raw -Encoding UTF8 -LiteralPath $ConstraintsOut | ConvertFrom-Json
$Complex | Select-Object quality_targets_met,strict_quality_targets_met,safety_passed,latency_target_met,all_targets_met,competition_ready | Format-List
$Constraints | Select-Object quality_targets_met,strict_quality_targets_met,safety_passed,latency_target_met,all_targets_met,competition_ready | Format-List
```

前五个标志都应为 `True`；`competition_ready` 应保留 `False`。两个原生命令退出码均应为 0。

| 层次 | 必须满足 |
| --- | --- |
| 旧质量目标 | 宏 Recall@3 >=85%，无答案正确率 >=85% |
| 本轮严格补充目标 | 每轮全部正例找齐、全部多文档找齐、全部无答案正确拒答 |
| 安全 | 异常为 0、非法或越域记录为 0 |
| 时延 | 每个配置每一轮有效 P95 <=500 ms |
| 一致性 | 运行期间源码未变 |

不能因为 Recall=99% 看起来很高，就忽略“仍有一个完整召回失败”的问题。

建议红框框选：两份报告各自前五项 `True`、`competition_ready=False` 和两个退出码 0。

建议旁边红字说明：

```text
指定复杂矩阵严格门禁通过，赛事验收仍独立进行。
```

### 11.6 展开全部配置、全部轮次

在窗口 C 定义显示函数：

```powershell
function Show-ComplexRows {
    param([object]$Report)
    foreach ($Profile in $Report.profiles) {
        foreach ($Round in $Profile.rounds) {
            $Summary = $Round.summary
            [pscustomobject]@{
                records = $Profile.corpus.records
                hard_fraction = $Profile.corpus.requested_hard_fraction_of_fillers
                constraints = [bool]$Profile.required_terms_enabled
                policy = $Profile.evidence_policy
                round = $Round.round
                complete = "$($Summary.full_evidence_correct)/$($Summary.positive_requests)"
                no_answer = "$($Summary.no_answer_correct)/$($Summary.no_answer_requests)"
                scope = "$($Summary.scope_empty_correct)/$($Summary.scope_requests)"
                recall = $Summary.macro_recall_at_3
                noise = $Summary.distractor_return_rate
                p95_ms = [math]::Round($Summary.p95_ms, 3)
                failures = @($Summary.failed_ids).Count
            }
        }
    }
}
Show-ComplexRows $Complex | Format-Table -Wrap
Show-ComplexRows $Constraints | Format-Table -Wrap
```

应分别有 12 行、24 行。

本版预期：原集每行 `complete=72/72`、`no_answer=24/24`、`scope=24/24`；约束集每行分别 `24/24`、`12/12`、`12/12`。

时延会随机器变化。本轮指南核验通过，不要求复测逐毫秒相同。

建议红框框选：原集 12 行、约束集 24 行中的规模、比例、约束状态、轮次、完整召回、拒答、隔离、时延和失败数。

建议旁边红字说明：

```text
全部配置逐轮核对，完整召回、拒答与时延均达标。
```

行数较多时分屏连续截图，不能裁掉未达标行。只有所有行的对应条件均满足时使用此句。

### 11.7 单独核查多文档完整性

```powershell
$Complex.profiles[0].rounds[0].completion | Format-List
$Constraints.profiles[0].rounds[0].completion | Format-List
```

原集应有：

```text
multi_document_requests : 12
multi_document_correct  : 12
multi_document_passed   : True
```

约束集应为 6/6。

这里先展示首格首轮以熟悉字段，最终仍需总门禁和全部配置通过，不能只挑第一格。

建议红框框选：当前展示的配置与轮次，以及两份报告中的多文档请求数、正确数和 `multi_document_passed`。

建议旁边红字说明：

```text
当前展示轮次多文档找齐：原集 12/12、约束集 6/6。
```

### 11.8 干扰比例、完整召回和精确率为什么不同

假设一道题需要两份证据，返回三条：

```text
真值 G = {g1, g2}
返回 R = [g1, d1, g2]
d1 是干扰记录
```

则：

| 指标 | 本算例 |
| --- | --- |
| Recall@3 | 2/2=100% |
| 完整证据是否找齐 | 是 |
| Precision@3 | 2/3 |
| 实际返回中的干扰 | 1/3 |
| 最终生成答案是否正确 | 还不知道，需要单独检查回答 |

这只是数学算例，不是新实测。

当前实现的 `precision_at_3` 使用 3 个固定槽位作分母；若只返回一份正确知识，另外两个空槽也仍在分母内。

`distractor_return_rate` 则是全部正例实际返回中，非相关记录数除以实际返回数。它不使用三个固定槽位，也不把无答案题混进同一分母。

已有固定证据在 1 万条、75% 填充下：原集仍有 39/123，即 31.71% 干扰；约束集仍有 9/39，即 23.08%。不能写成“干扰全部消除”。

建议红框框选：实际报告同一配置中的 `macro_recall_at_3`、`precision_at_3`、`distractor_return_rate` 和返回计数。

建议旁边红字说明：

```text
完整召回不等于零干扰，干扰返回率另行披露。
```

若截的是上面的集合算例，红字写“指标口径算例，不是本轮实测”。

### 11.9 分类型检查，防止少数快请求拉低总体时延

选择 1 万条、75% 填充的原集配置：

```powershell
$HardProfile = $Complex.profiles |
    Where-Object {
        $_.corpus.records -eq 10000 -and
        $_.corpus.requested_hard_fraction_of_fillers -eq 0.75
    } |
    Select-Object -First 1

$HardProfile.rounds[0].groups.kind.PSObject.Properties |
    ForEach-Object {
        [pscustomobject]@{
            kind = $_.Name
            requests = $_.Value.requests
            p95_ms = [math]::Round($_.Value.p95_ms, 3)
            errors = $_.Value.errors
            leaks = $_.Value.leaked_records
        }
    } |
    Format-Table -AutoSize
```

应分为 `positive`、`no_answer`、`scope`。三个组大小不同，P95 也可能差很多。

`groups.scenario` 可继续定位每个场景；`categories` 可查看长上下文、多文档等能力类别。

P95 仍用 nearest-rank：120 题取第 114 个，48 题取第 46 个，24 题取第 23 个，12 题取第 12 个。小组的“P95”可能就是最大值，不是大样本尾部稳定估计。

建议红框框选：选中的规模、比例与轮次，以及 `positive`、`no_answer`、`scope` 三行的请求数、P95、异常和泄漏数。

建议旁边红字说明：

```text
正例、拒答与隔离分别报时延，避免总体值掩盖慢请求。
```

### 11.10 展开所有失败请求

```powershell
$ComplexFailures = @(
    foreach ($Profile in $Complex.profiles) {
        foreach ($Round in $Profile.rounds) {
            foreach ($Row in $Round.rows) {
                if (-not $Row.passed) {
                    [pscustomobject]@{
                        records = $Profile.corpus.records
                        hard_fraction = $Profile.corpus.requested_hard_fraction_of_fillers
                        round = $Round.round
                        detail = $Row
                    }
                }
            }
        }
    }
)
Write-Host "失败执行次数：$($ComplexFailures.Count)"
$ComplexFailures | ConvertTo-Json -Depth 15
```

预期为 0。查看约束集时，把上述 `$Complex.profiles` 换成 `$Constraints.profiles`。

失败详情至少保留：

- `id`、场景、问题和类型。
- `expected` 与 `returned`。
- `scores` 和 `evidence`。
- `error_type`、`invalid_ids`、`elapsed_ms`。

异常、超时、重复结果或非法 ID 都不是“正确拒答”。不要把任何非正常空返回记成无答案成功。

建议红框框选：遍历全部配置和轮次的筛选命令、两套报告各自“失败执行次数：0”。

建议旁边红字说明：

```text
两套指定矩阵均未发现失败执行。
```

仅核查原集时改为“原复杂矩阵未发现失败执行”。任一计数非零时改为“本轮存在失败执行，详情已保留”，不使用成功短句。

### 11.11 开发反例单独运行、单独计数

原矩阵完成后，按顺序执行：

```powershell
$DevOut = Join-Path $Run 'development.json'
if (Test-Path -LiteralPath $DevOut) { throw '已有开发报告，请换新输出。' }
& $Py -B -X utf8 -S scripts/evaluate_evidence_development.py --output $DevOut
$DevExit = $LASTEXITCODE
Write-Host "开发集执行退出码：$DevExit"
```

```powershell
$ChallengeOut = Join-Path $Run 'development-challenge.json'
if (Test-Path -LiteralPath $ChallengeOut) { throw '已有追加反例报告，请换新输出。' }
& $Py -B -X utf8 -S scripts/evaluate_evidence_development.py --challenge --output $ChallengeOut
$ChallengeExit = $LASTEXITCODE
Write-Host "追加反例执行退出码：$ChallengeExit"
```

检查新默认，不要求旧实验全过：

```powershell
$Dev = Get-Content -Raw -Encoding UTF8 -LiteralPath $DevOut | ConvertFrom-Json
$Challenge = Get-Content -Raw -Encoding UTF8 -LiteralPath $ChallengeOut | ConvertFrom-Json
($Dev.profiles | Where-Object evidence_policy -eq 'focused_evidence_v2').summary | Format-List
($Challenge.profiles | Where-Object evidence_policy -eq 'focused_evidence_v2').summary | Format-List
```

新默认的预期：原 20 请求中 10/10 正例、10/10 无答案；追加 10 请求中 6/6 正例、4/4 无答案。

这两个脚本的退出码主要反映执行有效性和异常，不保证每个策略质量全过。必须读取对应策略的 `summary`。

20+10 都是可见开发数据，不能与冻结的 168 相加宣称 198 道独立盲测。第 7.7 节新增 H7/H70 探索例也另立记录，不修改这些冻结分母。

建议红框框选：筛选出的 `focused_evidence_v2` 及两份 `summary` 的正例、无答案分母和正确数。

建议旁边红字说明：

```text
新默认通过这 20+10 个可见开发请求，不作独立盲测。
```

## 12. 三策略对照：证明修复没有损害原有能力

### 12.1 三个名字分别是什么

| 策略 | 用途 |
| --- | --- |
| `similarity` | 旧业务默认，作为质量、排序、干扰等比较基准 |
| `content_coverage_v1` | 曾经损害召回的旧正文覆盖实验，仅保留为显式控制组 |
| `focused_evidence_v2` | 当前默认，聚焦问题、保护主体并补齐互补证据 |

不要把“旧实验默认关闭”理解为“当前没有证据检查”。当前运行的是新策略，而非直接打开旧实验。

建议红框框选：报告中的三个 `evidence_policy` 名称，明确区分当前默认与两组对照。

建议旁边红字说明：

```text
新默认与两组旧策略对照，旧实验只作控制组。
```

### 12.2 快速路线：复算已有同源证据

本路线不重新测时延，只重新读取每题的返回、摘要和源码绑定，核查比较结论。三份历史输入保持原样，新结果放进 `$Run`。

```powershell
$EvidenceRoot = Join-Path $Project 'artifacts\verification\feedback\focused-20260911'
$OriginalAudit = Join-Path $Run 'comparison-original.json'
& $Py -B -X utf8 -S scripts/compare_evidence_policies.py --input (Join-Path $EvidenceRoot 'complex-policies.json') --output $OriginalAudit
$OriginalAuditExit = $LASTEXITCODE
Write-Host "原复杂集配对复算退出码：$OriginalAuditExit"
```

```powershell
$EnforceAudit = Join-Path $Run 'comparison-enforce.json'
& $Py -B -X utf8 -S scripts/compare_evidence_policies.py --input (Join-Path $EvidenceRoot 'constraints-policies-enforce.json') --constraints enforce --output $EnforceAudit
$EnforceAuditExit = $LASTEXITCODE
Write-Host "约束开启配对复算退出码：$EnforceAuditExit"
```

```powershell
$NoneAudit = Join-Path $Run 'comparison-none.json'
& $Py -B -X utf8 -S scripts/compare_evidence_policies.py --input (Join-Path $EvidenceRoot 'constraints-policies-none.json') --constraints none --output $NoneAudit
$NoneAuditExit = $LASTEXITCODE
Write-Host "约束关闭配对复算退出码：$NoneAuditExit"
```

比较器拒绝覆盖已有输出；第二次执行须换文件名。

本指南对应源码的三份复算均应退出 0。将来源码、数据或检索配置改变后，比较器拒绝旧输入是正确保护，不能删掉源码检查让旧证据继续通过。

建议红框框选：三条命令的历史输入路径、新输出名称和各自退出码 0。

建议旁边红字说明：

```text
三份既有同源证据复算通过，本次未重新测时延。
```

### 12.3 查看七项硬检查

```powershell
$Audit = Get-Content -Raw -Encoding UTF8 -LiteralPath $OriginalAudit | ConvertFrom-Json
$Audit.checks | Format-List
$Audit | Select-Object optimization_gates_passed,all_controls_meet_targets,paired_request_count_per_reference,distinct_requests,competition_ready | Format-List
```

七项逐一对应：

1. 比较过程中绑定源码未变。
2. 新策略完整证据、多文档与无答案全部通过。
3. 对两组旧策略：原来正确的请求仍正确，每题 Recall 不降低。
4. 对旧业务默认：汇总排序与干扰等指标不退化。
5. 新策略没有失败请求，包括作用域负例。
6. 无执行错误或泄漏。
7. 每个配置每一轮 P95 都不超过 500 ms。

成功状态应包括：

```text
optimization_gates_passed : True
all_controls_meet_targets : False
competition_ready : False
```

第二个 `False` 合理：控制组里故意保留了有缺陷的旧实验。它不是新策略失败。

但如果 `optimization_gates_passed=False`，不能用“只是旧实验失败”解释过去；必须检查 `request_regressions`、`metric_regressions`、`candidate_failures`。

建议红框框选：七项 `checks`、`optimization_gates_passed=True`，同时保留两个 `False` 及比较数据集。

建议旁边红字说明：

```text
本组新策略七项门禁通过，旧控制组仍保留失败。
```

上面的显示命令只读取原复杂集审计。要说明三份全部通过，须对约束开启、关闭两份审计分别展示同样字段，不能仅凭这张图外推。

### 12.4 “不退化”不等于所有速度和精度都优于所有旧策略

比较边界必须完整描述：

- 两组旧策略的逐题成功和 Recall 都受到保护。
- 排序、精确率、干扰等汇总的比较对象是旧业务默认 `similarity`。
- 旧覆盖实验可能大量拒答，因此干扰率看起来更低；不能靠拒绝正确答案来赢干扰指标。
- 时延门槛是每格每轮 P95 <=500 ms，不是每题更快。
- 输出集合已经改变，不是等输出的纯性能加速实验。

固定证据中，原集 1 万条、75% 首轮 P95 从 39.399 ms 到 67.605 ms，存在新增证据检查成本。材料没有将这项变化说成加速。

建议红框框选：固定报告里相同规模、比例、轮次的旧默认与新默认 P95，以及 500 ms 门槛。

建议旁边红字说明：

```text
本格新策略仍达时延门槛，但证据检查增加了耗时。
```

### 12.5 完整路线：重新测三策略

这条路线耗时更多。先完成第 11 章，确认新策略独立运行通过，再考虑重建控制组。

**三条测量必须串行。** 不加 `--require-targets`，因为总报告包括已知会失败的旧对照。

```powershell
$PoliciesOut = Join-Path $Run 'policies-original-new.json'
& $Py -B -X utf8 -S scripts/evaluate_complex_retrieval.py --evidence-policy compare --sizes 1000,10000 --hard-fractions 0,0.75 --rounds 3 --output $PoliciesOut
if ($LASTEXITCODE -ne 0) { throw '三策略测量执行失败，先查看输出。' }
```

```powershell
$PoliciesEnforceOut = Join-Path $Run 'policies-enforce-new.json'
& $Py -B -X utf8 -S scripts/evaluate_complex_retrieval.py --suite complex_constraints_v1 --constraints enforce --evidence-policy compare --sizes 1000,10000 --hard-fractions 0,0.75 --rounds 3 --output $PoliciesEnforceOut
if ($LASTEXITCODE -ne 0) { throw '约束开启的三策略执行失败。' }
```

```powershell
$PoliciesNoneOut = Join-Path $Run 'policies-none-new.json'
& $Py -B -X utf8 -S scripts/evaluate_complex_retrieval.py --suite complex_constraints_v1 --constraints none --evidence-policy compare --sizes 1000,10000 --hard-fractions 0,0.75 --rounds 3 --output $PoliciesNoneOut
if ($LASTEXITCODE -ne 0) { throw '约束关闭的三策略执行失败。' }
```

这里将约束开启和关闭分开输出，而不是 `--constraints compare`，因为后面的严格比较器每次检查一种约束模式。

然后逐条复算新测量：

```powershell
& $Py -B -X utf8 -S scripts/compare_evidence_policies.py --input $PoliciesOut --output (Join-Path $Run 'policies-original-new-audit.json')
if ($LASTEXITCODE -ne 0) { throw '原集新测量不退化检查失败。' }
```

```powershell
& $Py -B -X utf8 -S scripts/compare_evidence_policies.py --input $PoliciesEnforceOut --constraints enforce --output (Join-Path $Run 'policies-enforce-new-audit.json')
if ($LASTEXITCODE -ne 0) { throw '约束开启新测量不退化检查失败。' }
```

```powershell
& $Py -B -X utf8 -S scripts/compare_evidence_policies.py --input $PoliciesNoneOut --constraints none --output (Join-Path $Run 'policies-none-new-audit.json')
if ($LASTEXITCODE -ne 0) { throw '约束关闭新测量不退化检查失败。' }
```

没有重新测量时，不运行这一组并声称“本轮新测三策略”。第 12.2 节的工作应明确写成“既有同源证据复算”。

建议红框框选：三份新测报告的本轮时间、全部策略配置，以及三份新审计的门禁结果。

建议旁边红字说明：

```text
本轮三策略重新测量，配对门禁均通过。
```

此句只适用于实际完成本节全部测量及复算，且三份审计门禁都通过的情况。只执行第 12.2 节时不得使用。

### 12.6 比较器拒绝时怎么定位

| 提示 | 先检查 |
| --- | --- |
| `measured retrieval source changed` | 当前 `src` 是否已改变，是否误选历史版本证据 |
| `measured evaluator changed` | 数据、评测入口及评测器是否变动 |
| `missing or unexpected comparison profile` | 是否漏规模、干扰、策略，是否把两种约束模式混在一份输入 |
| `missing environment identity or fixed tie-breaking seed` | 测量前是否设置 `PYTHONHASHSEED=0` |
| `measurement method, policies or repetitions changed` | 轮数、输入顺序和参数是否一致 |
| `refusing to overwrite` | 输出已经存在，换一个新名字 |
| 七项中某项为 False | 查看相应退化数组，不能删失败请求 |

比较器在结构或绑定错误时可能直接报错，不保证一定产生 JSON。此时命令非零退出本身就是失败证据，保留终端日志。

建议红框框选：实际错误字段、输入报告名与非零退出码；原始证据保留不动。

建议旁边红字说明：

```text
本次比较未通过，先核对报错与证据绑定。
```

不要把任意非零退出都标成“保护机制通过”；只有明确触发的负例检查才按其测试条件判定。

## 13. 性能测试：把服务、HTTP、初始化和模型分开

### 13.1 先明确计时边界

```text
事件或文档准备
  -> 接入、抽取、建索引、数据库落盘        单独记录，不冒充检索耗时
  -> MemoryService.search                 第10/11章的主要计时边界
       服务锁、查询编码、检索、证据处理、序列化
  -> HTTP请求与响应                       服务负载报告单列
  -> Agent组织答案或执行任务               另需真实Agent/Judge评测
```

注意：若模型或 SDK 初始化实际发生在 `search/provider` 调用内部，就必须计入这次服务耗时。不能为了达标把所有初始化一概从计时中剪掉。

建议红框框选：实际报告中的计时方法、调用路径与模型配置；截流程图时保留各层边界。

建议旁边红字说明：

```text
服务、HTTP 与模型计时分开，调用内初始化不删去。
```

### 13.2 可选：复核旧 v3 开发／测试切分

```powershell
$V3Out = Join-Path $Run 'evaluation-v3.json'
if (Test-Path -LiteralPath $V3Out) { throw '已有 v3 报告，请换新输出。' }
& $Py -B -X utf8 -S scripts/evaluate_v3.py --require-quality --embedding-config config/embedding.hash.json --output $V3Out
$V3Exit = $LASTEXITCODE
$V3 = Get-Content -Raw -Encoding UTF8 -LiteralPath $V3Out | ConvertFrom-Json
$V3.quality_targets | Format-List
$V3.test | Select-Object positive_queries,no_answer_queries,positive_queries_fully_recalled,no_answer_correct,positive_recall_at_3,no_answer_accuracy | Format-List
Write-Host "v3 退出码：$V3Exit"
```

本版结果：测试切分 12 个正例中 11 个找齐、6 个无答案正确拒答；Recall 为 91.67%，无答案正确率为 100%，满足该入口两个 85% 门槛。

**它仍有 1 个正例没有找齐。** 第 11 章两套复杂集的严格全过不代表整个工程的全部数据集都是 100%。

建议红框框选：`positive_queries=12`、`positive_queries_fully_recalled=11`、无答案 6/6，以及该入口的 85% 门槛。

建议旁边红字说明：

```text
旧 v3 达自身门槛，但仍有 1 个正例未找齐。
```

这是当前记录中的限制说明，不能因为退出码为 0 就标成“全部正例完整召回”。

v3 数据用于历史阈值校准与回归：历史 `similarity` 开发口径保留，当前策略在不重调阈值的条件下评估。不能把它当作新策略、真实 SDK 或新领域已经独立校准。

### 13.3 可选：运行机制诊断与消融

上一项完成后执行：

```powershell
$AblationOut = Join-Path $Run 'ablations.json'
& $Py -B -X utf8 -S scripts/run_ablations.py --require-diagnostics --output $AblationOut
$AblationExit = $LASTEXITCODE
$Ablations = Get-Content -Raw -Encoding UTF8 -LiteralPath $AblationOut | ConvertFrom-Json
$Ablations.diagnostic_gate | ConvertTo-Json -Depth 8
Write-Host "诊断退出码：$AblationExit"
```

该入口拒绝覆盖输出。成功时退出 0，`diagnostic_gate.passed=true`。

它包含词法／向量／混合检索对照、缓存编码次数、偏好衰减与冲突隔离等诊断。它不是 v2 每个子机制的完整因果消融实验。

保留平局和不利结果。例如开启／关闭衰减都通过某个简单探针，不应该写成“开启衰减显著提升”。

少量查询的平均耗时不能替代万条复杂场景 P95；编码调用次数是缓存工作量证据，不是跨机器加速比例。

建议红框框选：`diagnostic_gate` 的实际各项检查、`passed=true` 和退出码 0，保留平局或不利结果。

建议旁边红字说明：

```text
机制诊断门禁通过，不等于完整因果消融。
```

### 13.4 运行真实服务负载与 HTTP 检查

这是实际 `MemoryService`、SQLite 和本地 HTTP 的受控负载，不是只对空列表计时。脚本自行管理临时服务，不需要窗口 A 的服务在线。

```powershell
$WorkloadOut = Join-Path $Run 'service-workload.json'
& $Py -B -X utf8 -S scripts/benchmark_service.py --sizes 100,1000 --rounds 30 --embedding-config config/embedding.hash.json --require-integrity --output $WorkloadOut
$WorkloadExit = $LASTEXITCODE
$Workload = Get-Content -Raw -Encoding UTF8 -LiteralPath $WorkloadOut | ConvertFrom-Json
Write-Host "负载测试退出码：$WorkloadExit"
Write-Host "完整性通过：$($Workload.integrity_passed)"
```

预期退出 0、完整性为 True。本入口拒绝覆盖已有文件。

`--require-integrity` 主要要求查询目标及重启完整性通过，**不等于给所有时延字段强制设置了 500 ms 门禁**；还要检查结果中的 `retrieval_under_500ms`。

建议红框框选：实际服务负载命令、退出码 0 和 `integrity_passed=True`。

建议旁边红字说明：

```text
服务负载完整性通过，时延条件继续单独核对。
```

### 13.5 同时看命中、耗时和重启

```powershell
$Workload.results |
    Select-Object records,mixed_query_p50_ms,mixed_query_p95_ms,mixed_query_p99_ms,http_query_p99_ms,restart_load_ms,integrity_passed,retrieval_under_500ms |
    Format-Table -Wrap

foreach ($Result in $Workload.results) {
    Write-Host "语料配置：$($Result.records)"
    $Result.query_counts | Format-List
    $Result.correct_queries | Format-List
    $Result.integrity_checks | Format-List
}
```

默认 30 轮时，每个规模应检查：

| 路径 | 请求数 | 目标召回 |
| --- | --- | --- |
| 顺序服务调用 | 30 | 30 |
| 并发混合负载查询 | 30 | 30 |
| 本地 HTTP | 10 | 10 |
| 数据库重启 | 独立完整性条件 | 记录数保持符合预期 |

只是 `all_queries_nonempty=true` 不够：非空结果可能是错的，必须看目标命中。

`records` 是起始规模；工作负载会新增记录，所以 `persisted_knowledge` 不必等于起始数。应以脚本的重启完整性条件为准。

同一配置可拆成三张图，不把完整性通过当成所有时延达标：

| 画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 目标命中 | `query_counts` 与 `correct_queries` 的顺序 30/30、并发 30/30、HTTP 10/10 | 本配置三条查询路径均命中目标。 |
| 时延 | 服务 P50/P95/P99、HTTP P99 和 `retrieval_under_500ms`，保留各字段单位 | 服务与 HTTP 耗时分列，按各自口径判断。 |
| 重启 | `integrity_checks` 中持久化与重启条件，以及 `restart_load_ms` | 本配置重启完整性通过，加载耗时单列。 |

各规模都要检查。请求数会随参数改变，红框以实际配置为准；不能只框非空结果数。

### 13.6 内存与 CPU 应怎样报告

```powershell
foreach ($Result in $Workload.results) {
    Write-Host "语料配置：$($Result.records)"
    $Result.process_resources | Format-List
}
```

重点看：

- `available`：当前系统有没有真正取到资源数据。
- `rss_before_bytes` / `rss_after_bytes`：当前进程常驻内存。
- `lifetime_peak_rss_bytes`：进程启动以来高水位，不是单个配置独有峰值。
- `cpu_percent_one_core`：以一个逻辑核为参照的消耗。
- `scope`：不包含独立模型服务器和所有子进程。

`available=false` 时不能把缺失值写成 0 MB，须写“本平台该项未采集”。

RSS、SQLite 文件大小、Python 内存分配统计不是同一个概念，不能互相替换。

建议红框框选：`available`、RSS、进程生命周期峰值、CPU 及 `scope`，保持字节单位可辨。

建议旁边红字说明：

```text
资源数值仅覆盖所列进程，高水位不是单配置峰值。
```

若 `available=false`，改用“本平台资源数据未采集，不能记为 0 MB”。

### 13.7 发现时延偏长时的排查顺序

1. 先确认查的是哪一项：`retrieval_p95_ms`、`mixed_query_p95_ms`、HTTP P99，还是 SDK 单次探针。
2. 确认 Hash／SDK、参数、规模和干扰比例，没有拿不同配置硬比较。
3. 看正例目标是否命中、拒答是否正确，排除“变快只是因为不返回结果”。
4. 看完整逐题耗时和首查，不删除最慢样本。
5. 记录后台负载、节能模式、Python 版本和磁盘位置。
6. 保留本轮输出，另建新目录，在稳定条件下重新串行运行。
7. 若质量或 500 ms 门槛仍失败，记录为失败，交由实现修复后全量回归。

不要盲目降低 `top_k`、提高阈值、去掉干扰、缩小数据或关闭证据检查，只为了得到更小的时延。

建议红框框选：未达标的实际 P95、对应门槛、模型、规模、干扰比例和轮次。

建议旁边红字说明：

```text
本轮时延未达标，保留慢请求后复测。
```

只在对应时延门槛实际失败时使用；不能将 HTTP P99 或单次 SDK 探针误套成服务 P95 失败。

### 13.8 不应出现的性能结论

| 不正确说法 | 应如何表述 |
| --- | --- |
| “端到端 50 ms” | 本机 Hash 的进程内检索 P95，明确不含 HTTP 和 Agent |
| “所有请求小于 500 ms” | 若只检查 P95，则只能说明 P95 达标，另报告最大值 |
| “三轮相当于三倍独立样本” | 同一请求重复测量，分母分别报告 |
| “本机达标，麒麟必然达标” | 当前 Windows 结果，V11 与原生 SDK 单独复验 |
| “峰值内存仅为本配置消耗” | 先看高水位定义和进程边界 |
| “召回 100%，不存在干扰” | 同时报 Recall、完整率、P@3 和实际干扰比例 |
| “新方案全面加速” | 部分场景有新增检查成本，按同格数据报告收益与代价 |

## 14. 行动评测：先自检框架，再谈真实 Agent

### 14.1 本章测试什么

前面检查“返回了哪些记忆”，本章检查“跨会话使用记忆后，实际文件是否正确”。

```text
控制器保管样例和期望答案
  -> 第1会话植入记忆
  -> 清空本会话短期上下文，保留长期记忆
  -> 后续会话先使用旧记忆，再接收新值
  -> 5会话、50轮结束
  -> 检查真实输出文件、长期记忆终态及禁止持久化内容
  -> 真实模式还需要独立Judge与人工复核
```

先分清三种层级：

| 层级 | 本章入口 | 能证明什么 |
| --- | --- | --- |
| 公开 fixture 自检 | `evaluate_actions.py` 默认模式 | 调度、跨会话、文件、记忆与判分框架能够配合 |
| 运行前静态盘点 | `check_action_runtime.py`、`check_action_readiness.py` | 当前窗口可见的命令、环境、固定资源是否具备 |
| 真实模型行动评测 | 隔离 V11 内的 container 模式及独立 Judge | 只有实际执行后才能形成相应模型证据 |

fixture 会写真实的合成文件，但采用固定句式适配器，**不是调用真实大模型**。

如果直接从本章开始，先完成第 1.2、1.5、1.6、1.9 节，确保 `$Project`、`$Py`、`$Run` 已设置。本章不需要网页服务在线。

### 14.2 创建全新的自检工作区

在窗口 C 执行：

```powershell
$ActionWorkspace = Join-Path $Run 'action-workspace'
$ActionOut = Join-Path $Run 'actions-fixture.json'
if (Test-Path -LiteralPath $ActionWorkspace) { throw '请为行动自检换一个新工作区名称。' }
if (Test-Path -LiteralPath $ActionOut) { throw '请为行动报告换一个新文件名。' }
```

此时不必手动创建 `$ActionWorkspace`，评测器会创建。

报告放在 `$Run` 下，**不放在 `$ActionWorkspace` 里面**。真实模式下这用于避免 Agent 读到控制器报告或隐藏答案；自检也遵守同样的目录边界。

不要用存放个人文件的目录作为工作区，不要把项目根目录作为工作区。

建议红框框选：独立的 `action-workspace` 与位于其外的 `actions-fixture.json` 两个路径末尾。

建议旁边红字说明：

```text
行动工作区与控制器报告分开，使用合成数据。
```

### 14.3 运行 5 会话、50 轮自检

```powershell
& $Py -B -X utf8 -S scripts/evaluate_actions.py --workspace $ActionWorkspace --output $ActionOut
$ActionExit = $LASTEXITCODE
Write-Host "行动自检退出码：$ActionExit"
```

预期最后出现的 JSON 含：

```json
{
  "sample_id": "cross-session-a",
  "protocol": {
    "name": "cross_session_v1",
    "cross_session_verified": true,
    "probe_files": 12,
    "slot_checks": 50,
    "label_semantics_independently_verified": false
  },
  "execution_completed": true,
  "exit_code": 0,
  "official_accuracy_verified": false
}
```

以上是公开自检的预期结构，不是用户本次运行结果。自己运行后以新报告为准。

建议红框框选：实际报告的 `execution_completed=true`、`cross_session_verified=true`、退出码 0 和 `official_accuracy_verified=false`。

建议旁边红字说明：

```text
跨会话 fixture 执行完成，不是真实模型成绩。
```

### 14.4 看实际文件与后验检查

```powershell
$Actions = Get-Content -Raw -Encoding UTF8 -LiteralPath $ActionOut | ConvertFrom-Json
$Actions | Select-Object sample_id,sessions,turns,execution_completed,official_accuracy_verified | Format-List
$Actions.protocol | Format-List
$Actions.posthoc | Select-Object correct_files,total_files,action_accuracy,memory_active_slots_correct,passed | Format-List
$Actions.posthoc.independent_llm_judge | Format-List
Get-ChildItem -LiteralPath $ActionWorkspace -Recurse -File |
    Select-Object FullName,Length |
    Format-Table -Wrap
```

合格自检应满足：

| 条件 | 预期 |
| --- | --- |
| 会话数／轮次 | 5／50 |
| `cross_session_verified` | True |
| `correct_files`／`total_files` | 12／12 |
| `memory_active_slots_correct` | True |
| `posthoc.passed` | True |
| `independent_llm_judge.executed` | False，这是当前自检边界 |
| `official_accuracy_verified` | False，这是当前自检边界 |

文件数 12 和槽位检查数 50 不是同一个分母。后续 Judge 交换可构造 76 个检查，但仍共享这一个公开样例，不能说成 76 个独立请求，更不能替代冻结五项的独立分母。

不要使用 `--legacy-fixture` 来修复当前失败。它对应旧的同会话诊断，不符合当前跨会话证明目的。

建议红框框选：5 会话、50 轮、12/12 文件、记忆终态与 `posthoc.passed=True`；同时保留 Judge `executed=False` 和官方验证 `False`。

建议旁边红字说明：

```text
自检 12 份文件与记忆终态通过，未执行真实 Judge。
```

文件清单可另图展示，但文件存在本身不等于内容判分正确。

### 14.5 只读盘点当前电脑的运行资源

```powershell
$RuntimeOut = Join-Path $Run 'action-runtime.json'
& $Py -B -X utf8 -S scripts/check_action_runtime.py --output $RuntimeOut
$RuntimeExit = $LASTEXITCODE
$Runtime = Get-Content -Raw -Encoding UTF8 -LiteralPath $RuntimeOut | ConvertFrom-Json
$Runtime.commands_on_path | Format-List
$Runtime.engines | ConvertTo-Json -Depth 5
$Runtime | Select-Object model_endpoints_contacted,images_started_or_pulled,agent_executed,independent_judge_executed | Format-List
Write-Host "只读盘点退出码：$RuntimeExit"
```

这个脚本不会安装软件、拉镜像、启动引擎或调用模型；存在 Docker/Podman 命令时，只执行有超时上限的 `info` 查询。

本机核验时 Docker 客户端在 PATH 中，但没有取得有效可达的服务端版本，`reachable=false`。这两个字段并不矛盾。

环境变量只记录“是否存在”，不打印密钥值。未发现模型变量不等于全盘没有模型，它只说明当前窗口的选定变量没有提供模型配置。

**盘点退出 0 只表示盘点完成，不代表 Agent 已经能运行。**

建议红框框选：Docker 命令存在、引擎 `reachable=false`，以及模型调用、镜像启动和 Agent/Judge 执行的实际布尔值。

建议旁边红字说明：

```text
只读盘点完成，当前引擎未就绪，未运行真实模型。
```

本句对应当前核验状态；你复测时若引擎已可达，应据实修改“未就绪”，仍不能由盘点推导模型已执行。

### 14.6 检查正式运行前置条件

在没有私有样例及冻结清单时，可先运行环境检查：

```powershell
$ReadinessOut = Join-Path $Run 'action-readiness.json'
& $Py -B -X utf8 -S scripts/check_action_readiness.py --output $ReadinessOut
$ReadinessExit = $LASTEXITCODE
$Readiness = Get-Content -Raw -Encoding UTF8 -LiteralPath $ReadinessOut | ConvertFrom-Json
$Readiness | Select-Object static_prerequisites_passed,competition_submission_ready | Format-List
$Readiness.missing_static_prerequisites
Write-Host "运行前检查退出码：$ReadinessExit"
```

在当前 Windows 环境，预期退出 2，缺项包括：

- 有效冻结清单及其源码绑定。
- 指定的 V11 身份。
- 可达且架构匹配的 Linux 容器引擎及资源。
- 与固定摘要一致的 Agent、Judge 本地镜像。

这不是 Hash 演示故障，也不需要在 Windows 启动 Docker Desktop 来“消除红字”。

在真实资源齐全的 V11 内，静态检查全部通过也返回 **3**，表示“静态条件满足，实际模型执行仍待进行”。程序不以 0 表示正式赛事通过。

建议红框框选：实际 `missing_static_prerequisites`、两个就绪字段和退出码；长缺项列表不能只截第一条。

| 实际画面 | 建议旁边红字说明 |
| --- | --- |
| 当前退出 2，仍有静态缺项 | 真实行动评测前置条件不足，缺项逐条保留。 |
| 以后静态检查通过，退出 3 | 静态前置条件满足，真实模型尚待执行。 |

两种文案按本次报告二选一。缺项数不写死为历史数量，真实模型未运行时不标成“正式验收通过”。

### 14.7 真正运行前，负责人需要核对什么

| 要素 | 必须核实的内容 |
| --- | --- |
| 环境 | 已安装到磁盘的隔离银河麒麟 V11，不是 Windows、WSL 或 Live ISO |
| Agent | 真实程序、授权来源、固定模型版本、镜像摘要、绝对适配入口 |
| Judge | 与 Agent 区分的模型和角色、完整预装权重、固定摘要与许可 |
| 标签 | 私有控制器保管，不能挂载给 Agent，不能由公开题改名冒充盲测 |
| 冻结 | 在运行前冻结源码、样例、镜像、模型、资源和评测口径 |
| 资源 | 当前实现限制下确实能完成模型加载、推理和完整评分，不按镜像大小猜测内存 |
| 记录 | 50 轮轨迹、真实文件、失败、超时、原始模型响应和人工复核 |
| 外部认可 | 参赛者已确认获认可的方案不重复申请；适用配置和原始凭证仍需归档 |

一条正确的后续流程是：

```text
私有样例和真实身份核验
  -> freeze冻结
  -> readiness只读检查
  -> 单样本单容器运行Agent
  -> 停止容器并冻结真实文件
  -> prepare/validate构造独立Judge输入
  -> run或score处理实际模型响应
  -> 全部0分项与至少10%人工抽检
  -> 保留分歧，形成外部验收记录
```

完整参数、适配协议和真实 V11 命令见[官方行动评测协议](26_官方行动评测协议.md)及[资源交接](36_正式评测资源与外部交接.md)。

没有实际镜像、模型或独立标签时，在本章停留于 fixture 和静态盘点即可。不要填假 SHA256、借用别人的结果、手工改 `executed` 字段或把固定适配器改名为真实 Agent。

### 14.8 本章退出码速查

| 入口 | 0 | 2 | 3 |
| --- | --- | --- | --- |
| `evaluate_actions.py` | fixture 或结构校验通过 | 执行或证据失败 | 真实容器证据已采集，独立判分及验收待进行 |
| `check_action_runtime.py` | 盘点完成 | 不作为该入口的统一成功约定 | 不适用 |
| `check_action_readiness.py` | 不作为正式就绪结果 | 静态条件缺失或非法 | 静态检查通过，真实运行待进行 |

外层 PowerShell 有时会把非零原生退出概括为自身失败。应在命令之后立即保存 `$LASTEXITCODE`，并结合脚本 JSON；不能只看终端宿主显示的总退出码。

## 15. 麒麟 V11 与真实 SDK：独立复测路线

### 15.1 哪些事情 Windows 可以做

| 可以在 Windows 做 | 不可用 Windows 结果替代 |
| --- | --- |
| Hash 演示、自动测试、固定数据回归 | 当前源码在安装版 V11 中实际部署 |
| 只读 SDK 发现与参数检查 | 原生库真正执行向量编码 |
| 阅读配置示例、整理待复测清单 | 模型身份、版本和向量库往返 |
| 核对报告字段、源码及数据摘要 | 指定真实 SDK 的多请求时延与质量门禁 |

本章是可选环境验收路线。不具备真实 V11/SDK 条件时，记录待复测并完成本地测试，不要为本手册改动宿主系统。

### 15.2 运行无模型调用的 SDK 发现

在窗口 C 执行：

```powershell
$NativeOut = Join-Path $Run 'native-discovery.json'
& $Py -B -X utf8 -S scripts/check_kylin_native.py --output $NativeOut
$NativeExit = $LASTEXITCODE
$Native = Get-Content -Raw -Encoding UTF8 -LiteralPath $NativeOut | ConvertFrom-Json
$Native | Select-Object system,status,latency_status,real_embedding_executed,vector_database_connected,observations,single_probe_ms,native_p95_ms,native_latency_passed,competition_ready | Format-List
Write-Host "SDK 发现退出码：$NativeExit"
```

当前 Windows 预期：

| 字段 | 值 |
| --- | --- |
| `status` | `not_connected` |
| `latency_status` | 待复测风险项 |
| `real_embedding_executed` | False |
| `vector_database_connected` | False |
| `observations` | 0 |
| `single_probe_ms`、`native_p95_ms` | null，PowerShell 通常显示空白 |
| `native_latency_passed`、`competition_ready` | False |
| Python 脚本退出码 | 2 |

不能把空白时间解释为 0 ms。缺少 SDK 时也不自动切换 Hash 并标成真实 SDK 达标。

建议红框框选：`not_connected`、`待复测风险项`、观察数 0、空白 P95、未执行标志和退出码 2。

建议旁边红字说明：

```text
真实 SDK 尚未接通，时延仍为待复测风险项。
```

### 15.3 配置文件分别用于什么

```powershell
Get-Content -Raw -Encoding UTF8 -LiteralPath config\embedding.hash.json
Get-Content -Raw -Encoding UTF8 -LiteralPath config\embedding.kylin-native.example.json
```

| 文件 | 用途 |
| --- | --- |
| `embedding.hash.json` | 离线、确定性的本地 Hash 基线 |
| `embedding.kylin-native.example.json` | 原生 SDK 接入字段示例，不证明机器已有库和模型 |
| `embedding.kylin.example.json` | 另一种适配配置示例，不与原生库探针混淆 |

示例中的路径、模型、维度必须与实际安装环境一致。不要直接覆盖版本库中的示例；真实配置在经批准的本地私有位置另建，并排除凭据。

`check_kylin_native.py` 不接受 Hash 配置充当原生 SDK 证明。

建议红框框选：两份公开示例配置的文件名与实际 provider 类型；不要展示含凭据的私有配置。

建议旁边红字说明：

```text
Hash 与原生 SDK 配置分开，示例不代表已接通。
```

### 15.4 已具备原生库时，怎样做一次连通性探针

以下参数说明不是可直接复制的完整命令；**只在已核验的真实 SDK 环境操作**：

```text
方式A：check_kylin_native.py --embedding-config 实际原生配置 --output 新报告
方式B：check_kylin_native.py --library-path 实际动态库 --output 新的模型枚举报告
方式C：在枚举核实后，--library-path 实际动态库 --probe-model 实际模型名 --output 新报告
```

每次输出用新路径。方式 A 和显式库／模型参数互斥，不把两套方式拼在一条命令里。

成功标准至少是 `real_embedding_executed=true` 和预期维度；同时核对报告里的模型声明、版本验证状态、错误阶段及实际环境。

但即使成功，这个入口至多只是 **一次探针**：

- `observations=1` 不是至少 50 个独立查询。
- `single_probe_ms` 不是 P95。
- 成功向量编码不是向量数据库写入、检索、删除、重启往返已经验证。
- 模型名声明不是模型版本或权重摘要已经得到独立认证。
- 该入口不会自动把 `native_latency_passed` 或 `competition_ready` 改成 True。

旧 ABI 的一次历史探针为 **13,390.615 ms**，包含隔离进程、会话和初始化。它不是纯编码时间，也不是 P95；当前仍为**待复测风险项**。不得删除这次慢结果或用第 10 章 Hash 的约 50 ms 替换。

按实际展示的证据选择文案，不把下面的条件性成功句当成本次已运行：

| 画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 以后实际成功的单次探针 | `real_embedding_executed=true`、实际维度、`observations=1`、`single_probe_ms` 及身份核验状态 | 单次真实向量调用成功，尚不能证明 P95 达标。 |
| 当前引用的旧探针 | 历史报告名、旧 ABI、13,390.615 ms 和计时范围 | 历史单次探针含初始化，非 P95，风险仍待复测。 |

### 15.5 SDK 时延风险怎样才算闭合

实际复测至少应提交以下内容：

1. 指定安装版 V11、硬件、SDK ABI、库版本、模型名称、版本和权重身份。
2. 真实向量调用及向量数据库写入、搜索、遗忘、重启的往返记录。
3. 单独列出进程启动、模型加载、首次查询、后续查询和 HTTP 边界。
4. 固定语料、真实 SDK 查询编码、逐请求原始时间、超时与失败，不混入 Hash 回退。
5. 正例完整率、拒答、干扰、作用域和时延共同验收，不仅报一个速度。
6. 按实际样本数复算 P95，保留最大值及重复轮次，不挑最快一轮。
7. 新模型／新领域需独立开发校准，再冻结测试，不能假定 0.265 可直接通用。
8. 将达标或失败结论与新源码、配置和数据摘要绑定，由赛事口径验收。

本手册没有上述新 SDK 多请求测量，因此不会宣布风险已解除。

建议红框框选：待复测记录中缺少的模型身份、多请求质量与时延、向量库往返证据。

建议旁边红字说明：

```text
真实 SDK 多请求与向量库往返仍需补证。
```

### 15.6 可选：在已经安装的 V11 内运行同源验证

仅适用于负责人已有的、获准的隔离 V11 客户机。本手册不执行虚拟机开关机、磁盘分区、安装系统或修改网络策略。

先在客户机自己的 Linux 终端检查：

```bash
pwd
python3 --version
cat /etc/os-release
findmnt -n -o SOURCE,FSTYPE /
```

应确认：

- 位于同一源码版本的工程根目录，包含 `src`、`scripts`、`tests`。
- 系统身份是真实要求的银河麒麟 V11。
- 根文件系统在实际磁盘设备上，不是 Live ISO、overlay 或临时内存文件系统。
- Python 满足要求，`/var/tmp` 可用于受控临时文件。

运行前有一个重要细节：当前 V11 汇总脚本中的 v3 子检查仍使用默认 `artifacts/runtime/evaluation_v3.json`，可能覆盖该路径已有的运行输出。先由负责人在资源管理器或文件管理器中将重要旧报告另行留存，确认这个默认文件不存在后再运行；新 `--output` 目录不会自动隔离这一项。

以下命令在 **Linux 终端**，不是 PowerShell 中执行：

```bash
if test -e artifacts/runtime/evaluation_v3.json; then
    printf '%s\n' 'STOP: preserve the existing v3 report before running the guest verifier.'
    exit 1
fi
mkdir -p "$HOME/tiaobei-checks"
RUN="$HOME/tiaobei-checks/manual-$(date +%Y%m%d-%H%M%S)"
env TMPDIR=/var/tmp PYTHONHASHSEED=0 python3 -B -X utf8 -S scripts/verify_kylin_guest.py --output "$RUN"
```

`RUN` 必须不存在；脚本自己创建。运行可能较久，终端逐个显示 `Running ...`。先不要关闭客户机或启动其他性能任务。

这是受控 Hash 核心验证，不自动完成真实 SDK 或 Agent/Judge。若源码不是当前版本，即使通过，也只能算那个版本的记录。

建议红框框选：客户机实际系统版本、根文件系统设备、Python 版本和同源验证命令；只在已核实安装身份后标注。

建议旁边红字说明：

```text
安装版 V11 身份已核对，核心结果看完整报告。
```

只看到 `Running ...` 表示检查正在进行，不能提前加“全部通过”。没有执行本节时记录“本轮未执行 V11 同源验证”。

### 15.7 看懂 V11 结果

客户机输出目录里的 `kylin_vm.json` 是主要报告，旁边保留逐项日志。

| 字段 | 应怎样判断 |
| --- | --- |
| `installed` | 是否满足安装到磁盘的根文件系统条件 |
| `required_v11_verified` | 是否识别为指定 V11 |
| `tests_passed` | 当前客户机工程 unittest 是否成功 |
| `core_checks_passed` | 8 项核心检查与执行期间源码不变是否全部通过 |
| `source_unchanged_during_checks` | 执行前后源码、数据、配置是否一致 |
| `guest_verification_passed` | 安装身份、指定 V11、核心检查联合结果 |
| `official_validation_ready` | 当前保持 False，不因 Hash 验证通过自动变 True |

8 项核心检查为：工程测试、源码／隐私、v3、冻结请求、历史诊断、行动框架、服务负载、消融。

SDK 发现和行动 readiness 的预期非零结果也应保留，不能因它们不在 8 项核心联合门禁中就宣称真实 SDK、Agent 已通过。

既有 V11 记录的核心检查仅 7/8，通过 Windows 新回归不能替它补成 8/8。当前源码仍需单独 V11 复验。

| 实际画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 当前引用历史记录 | 历史版本、核心检查 7/8 与未通过项 | 旧 V11 记录仅 7/8，当前源码仍待独立复验。 |
| 以后本版真实复验全部通过 | 安装身份、V11 身份、8 项结果、源码绑定、`guest_verification_passed=true` 和官方就绪 `false` | 本版 V11 核心验证通过，SDK 与正式验收仍另行核验。 |

第二行只能用于真正取得新报告之后，不能用 Windows 的 8 项或旧客户机报告拼接。

### 15.8 V11 连接被拒绝时

如果客户机测试报告本地 HTTP 连接被网络管控拒绝：

1. 保留失败日志、平台版本、具体请求边界及已授权环境说明。
2. 区分服务没有启动、端口冲突、回环请求被管控等原因。
3. 在获准的客户机范围内处理，不关闭宿主机防火墙或整体安全软件。
4. 处理后对同一源码完整复验，而不是只补一张成功网页截图。
5. 对不能解决的项继续标记风险，不把失败子项从报告删除。

历史环境说明见[麒麟适配](07_银河麒麟适配说明.md)、[V11 实测](31_麒麟V11客户机实测.md)和[SDK 证据边界](27_真实SDK接入与证据边界.md)。

建议红框框选：客户机内具体失败子项、实际连接错误、平台版本及报告日期。

建议旁边红字说明：

```text
本轮 V11 子项失败，保留原因并在授权环境复验。
```

## 16. 检查最新 Word、PPT 和四个评分重点

### 16.1 先打开正确的版本

当前优先审阅目录：

```text
deliverables/submission-materials-20260911-revised/
```

| 文件 | 当前归档版本 |
| --- | --- |
| [项目报告 PPT](../deliverables/submission-materials-20260911-revised/OS_Agent_项目报告_20页精简版_20260911.pptx) | 20 页、10 张可编辑方案框图、7 张原生表格 |
| [技术方案 Word](../deliverables/submission-materials-20260911-revised/OS_Agent_技术方案_评分重点详述版_20260911.docx) | 18 章 79 节、25 图 49 表，本机既有渲染为 66 页 |
| [交付说明](../deliverables/submission-materials-20260911-revised/README.md) | 版本、阅读顺序和核验边界 |
| [第 47 号核验记录](47_精简PPT与评分重点Word修订核验.md) | 内容、源码绑定、实测分页、渲染及隐私记录 |

不要误用未带 `revised` 目录中的 53 页 PPT、54 页 Word，或更早的 23 页 PPT、39 页 Word。

本次操作指南不重新生成或覆盖这些 Office，不制作 PDF。负责人自行转换 PDF 后仍应复核分页、公式、图表和匿名性。

建议红框框选：`submission-materials-20260911-revised` 目录名与两份正式文件名；不选 `~$` 临时锁。

建议旁边红字说明：

```text
审阅当前修订版：20 页 PPT 与评分重点详述 Word。
```

### 16.2 用文件管理器审阅，避免误保存

1. 在工程根目录打开 `deliverables`。
2. 打开 `submission-materials-20260911-revised`。
3. 双击上表中的 PPTX 或 DOCX。
4. 首次只查看，不编辑或点击“保存”。
5. 若需要修改，在内部评审记录中写清页码、问题及建议，再安排新版本。

Word 页数会随字体、WPS/Office 版本、打印驱动和域更新变化，66 页是既有本机渲染结果，不保证所有电脑显示完全相同。不能为了保持 66 页而隐藏正文。

PPT 应有 20 页。用左侧缩略图和放映模式分别检查，正文表格、框图、箭头及备注都应完整。

建议红框框选：PPT 实际页数、放映画面中的方案框图，以及 Word 对应章节标题，分图展示。

建议旁边红字说明：

```text
核对页数、方案框图与章节，不以文件存在代替审阅。
```

### 16.3 按评分重点定位

| 重点 | PPT | Word | 审阅时具体问什么 |
| --- | --- | --- | --- |
| 相关工作对比 | 第 9–10 页 | 11.1–11.4，既有第 31–33 页；18.4–18.5 文献 | 比较的是目标、机制、边界还是仅列名字？有没有把未复现论文成绩拼成排行榜？ |
| 技术创新性 | 第 11–12、15 页 | 11.3、11.5–11.8，既有第 32–37 页 | 问题、实现、源码、证据、代价和可证伪条件是否对应？ |
| 评测口径说明 | 第 13–15 页 | 第 12 章，既有第 38–45 页 | 分母、真值、干扰、拒答、统计、异常和计时是否能复算？ |
| 性能可信度 | 第 16–18、20 页 | 第 13 章，既有第 46–52 页；SDK 第 30 页；正式验收第 61–63 页 | 是否有同条件比较、逐题结果、完整时延矩阵、不利结果和外部边界？ |

技术创新性 30 分、性能可信度 25 分作为反馈中的重点，不由本手册自评分；这两个权重不能错误归因于主要规定材料内容和提交方式的官方提交规则文件。

建议红框框选：实际材料中相关工作、创新性、评测口径、性能可信度四处章节或页标题。

建议旁边红字说明：

```text
四个评分重点均有对应章节，逐项核对论证与证据。
```

这里说明内容覆盖，不表示已经取得对应分数。

### 16.4 相关工作应检查到什么深度

审阅者逐项打勾：

- 是否覆盖 MemGPT、MemoryBank、Generative Agents、Mem0、MemoryOS 等相关记忆思路。
- 是否区分 LongMem 的神经外部记忆与 FAISS 的索引作用，不把它们都叫“同一种记忆系统”。
- 是否把 LongMemEval 等评测对象与本工程记忆 ID 召回、实际行动文件检查分开。
- 是否逐维解释输入来源、更新、层级、授权、冲突、遗忘、资源和评价对象。
- 是否明确三层记忆、混合检索、衰减并非单独首创。
- 是否说明未复现外部系统，因此不宣称本工程优于某论文系统的正式成绩。
- 是否有可追溯参考文献，正文的机制描述能与文献对应。

需要进一步阅读时，参照[相关工作与创新边界](38_相关工作与创新边界.md)、[近期相关工作与评测对照](43_近期相关工作与评测对照.md)。

建议红框框选：机制对比表、适用边界、未复现说明与对应文献编号，不只框论文名称。

建议旁边红字说明：

```text
相关工作按机制与边界对比，未作外部跑分排名。
```

### 16.5 创新性应检查到什么深度

建议把以下三条主张分别对照实现和测试：

| 主张 | 对照检查 | 不应夸大的部分 |
| --- | --- | --- |
| OS 事件治理一致性 | 清洗、去重、偏好修正、冲突隔离、遗忘、数据库事务是否相互一致 | 不能说所有独立机制均为原创发明 |
| 聚焦证据集合选择 | 请求聚焦、主体保护、主种子、互补章节、返回正文支持与归因 | 当前仍以词面规则为主，不是通用语义蕴含证明 |
| 逐请求不退化证据链 | 三策略同源测量、旧成功集合保护、Recall、排序、干扰、延迟门禁 | 不是 v2 每个子机制均已完成因果消融 |

可以用第 7.7 节新反例检验“可证伪”是否真的被执行：发现反例后如实留存、限定主张，不靠改描述把失败藏起来。

建议红框框选：每条创新主张对应的问题、实现框图、源码位置、验证证据与限制。

建议旁边红字说明：

```text
创新主张对应实现、证据、代价与限制。
```

### 16.6 评测口径应检查到什么深度

1. 冻结五项的 68／60／60／80／50 与复杂 120／48、开发 20+10 分开。
2. 12 个正例全找齐与 Recall@3 的平均值不是同一指标。
3. P@3 分母按固定 K 计，不能偷偷改为实际返回条数获得更高数值。
4. 无答案拒答与越域空返回分别计分，不能放到正例平均数里稀释失败。
5. 0%／75% 是生成填充干扰，不代表原始固定近邻被移除。
6. `expected` 标签不进入查询构造或约束生成。
7. 异常、超时、空答、误答、漏文档留在分母中。
8. P95 使用 nearest-rank，按轮次、规模、干扰和类型分开。
9. 三轮是重复测量，不当作三倍独立样本，不合并后挑有利百分位。
10. Hash、SDK、进程内服务、HTTP、Agent 最终答案计时分开。

逐项复算操作见本手册第 10 至 13 章及[评测口径与可信度](39_评测口径与可信度.md)。

建议红框框选：分母表、干扰定义、拒答计分、P95 公式和实际调用边界，可分屏展示。

建议旁边红字说明：

```text
分母、干扰、拒答与计时边界明确，按原始结果复核。
```

### 16.7 性能可信度应检查到什么深度

除通过结果外，应能找到：

- 同条件旧默认、新默认、旧实验比较，包含质量收益和新增耗时。
- 完整召回后仍有干扰片段的比例，不以“全找齐”替代“全正确”。
- 历史 v3 11/12 完整、旧策略失败等不利结果。
- 原生 SDK 慢探针、“待复测风险项”、当前 V11 待验收。
- 真实 Agent、独立 Judge、隐藏标签与授权案例缺少哪些实证。
- 当前报告对应哪次源码、数据、参数和原始结果。

本次手册中新测的 Hash P95 为约 50.828 ms，与 Office 使用的既有 48.145 ms 是不同运行。两者不能混成“一份同时测得的报告”，更不能静默改写旧 Office 里的值。

本次新增 H7/H70 无约束探索失败尚未写入既有 Office。负责人后续确认改稿时，应将该限制纳入新版材料或先完成算法修复及全量复验，不能只拿旧材料“复杂集通过”一句涵盖该新问题。

建议红框框选：材料的同条件对照、原始证据来源、不利结果和 SDK 风险说明；新 H7/H70 失败另展示本手册第 7.7 节的真实记录。

建议旁边红字说明：

```text
性能结论绑定原始证据，不利结果与外部边界单列。
```

不要加“所有新增反例已写入 Word”的红字，本次没有修改 Office。

### 16.8 可选：准备材料核验依赖

只用 Office 阅读时跳过本节。需要运行 Python 材料检查时，使用独立虚拟环境：

```powershell
& $Py -m pip install -e '.[deliverables]'
if ($LASTEXITCODE -ne 0) { throw '材料依赖安装失败，先不要继续核验。' }
& $Py -m pip install Pillow
if ($LASTEXITCODE -ne 0) { throw 'Pillow 安装失败，先不要继续核验。' }
& $Py -m pip check
```

这一步可能联网；网络受限时不影响前面的标准库核心测试。不要为了材料检查更改系统 Python 或其他工程环境。

仅严格结构核验不需要 PyMuPDF，也不需要运行 WPS 自动渲染。后续确需渲染时，按[材料工具说明](materials_20260911_revision/README.md)准备字体、WPS 及相关许可和依赖。

下面材料命令**不带 `-S`**，否则第三方包会不可见。

建议红框框选：同一虚拟环境的实际安装结果及 `No broken requirements found.`。

建议旁边红字说明：

```text
材料检查依赖已就绪，不代表材料核验已通过。
```

仅阅读 Office、跳过安装时，不使用此句。

### 16.9 关闭 Office 后再运行严格核验

先保存自己确实需要的编辑并正常关闭相关 Word/PPT 窗口；不代替他人关闭程序，不手动删除 `~$` 临时锁文件。

在窗口 C 查看目录，包括隐藏文件：

```powershell
$Materials = Join-Path $Project 'deliverables\submission-materials-20260911-revised'
Get-ChildItem -LiteralPath $Materials -Force |
    Select-Object Name,Length |
    Format-Table -Wrap
```

确认没有正在占用的 Office 锁文件后执行：

```powershell
& $Py -B -X utf8 docs/materials_20260911_revision/qa.py --materials $Materials
$MaterialsExit = $LASTEXITCODE
Write-Host "材料严格核验退出码：$MaterialsExit"
```

合格应退出 0，JSON 中 `passed=true`，运行文件数量 149、Word 79 节／25 图／49 表、PPT 20 页等与清单相符。

最终核验不要加 `--draft`。该参数会跳过材料工具摘要检查，不能用来绕开当前版本漂移。

本次编写手册时实际试跑因用户打开 Word 产生 `~$` 文件而失败：

```text
ValueError: expected exactly one Word and one project report
```

这是当前严格目录计数的行为，不代表已经确认正文损坏。该失败记录保留；第 47 号历史核验通过不替代此次执行结果。待负责人关闭文档后应重新运行。

若之后出现原始文件摘要不一致，先确认是否在 Office 中保存过变化。不能直接改清单中的预期 SHA256 来通过。

两种结果必须分开标注：

| 实际画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 本指南试跑时的失败 | `~$` 文件名、实际 `ValueError` 与非零退出码，隐藏个人路径 | Office 锁文件使本次严格核验失败，关闭文档后复跑。 |
| 以后重新核验通过 | 不带 `--draft` 的命令、`passed=true`、149 个运行文件、材料计数及退出码 0 | 本轮材料结构与摘要核验通过，视觉审阅另行进行。 |

第二行是条件性文案，不表示当前已获得一次新的成功结果；锁文件由原应用正常释放，不手工删除。

### 16.10 可选：运行材料工具测试

以下两组与工程的 392 项分开计算，上一组完成后再运行下一组：

```powershell
& $Py -B -X utf8 -m unittest discover -s docs/materials_20260911_revision -p test_revision.py -v
$RevisionTestsExit = $LASTEXITCODE
Write-Host "新版材料工具测试退出码：$RevisionTestsExit"
```

```powershell
& $Py -B -X utf8 -m unittest discover -s docs/materials_20260911 -p test_materials.py -v
$OriginalTestsExit = $LASTEXITCODE
Write-Host "原版材料工具测试退出码：$OriginalTestsExit"
```

既有核验为新版 23 项、原版 18 项通过。自己执行时以实际测试数、末尾 `OK`／`FAILED` 和退出码为准。

工具测试通过不代表用户当前改动后的 Office 自动通过，也不等于重新逐页看过渲染。

建议红框框选：两组各自的测试目录、实际 `Ran` 数量、最终 `OK` 与退出码 0。

建议旁边红字说明：

```text
两组材料工具测试通过，与工程回归分开计数。
```

只展示历史 23+18 结果时注明历史日期；本轮未跑不能标为本轮通过。

### 16.11 人工视觉与匿名性检查

| 检查对象 | 逐项动作 |
| --- | --- |
| PPT 每一页 | 放映检查文字大小、边界、表格最后一行、箭头方向、框图节点与页码 |
| PPT 备注 | 检查数据出处、技术边界、Word 节号和演讲内容是否一致 |
| Word 目录 | 点到正文，检查节号、页码、标题对应 |
| Word 图表 | 查看题注、公式、跨页表头、框图清晰度、断页及长行 |
| 两份正文 | 搜索 SDK、待复测、相关工作、创新、分母、P95、独立验收等重点 |
| 匿名性 | 检查姓名、学校、联系方式、仓库地址、文件属性、批注和修订记录 |
| 转换后的 PDF | 再次核对全部页面，不用转换前的截图替代 |

机器文本扫描不做媒体 OCR，图中的个人信息仍须人工看。代理视觉检查不等于负责人的最终审阅批准。

建议红框框选：真正逐页审阅后填写的检查记录、页码与发现的问题；不框选尚未勾选的空白清单冒充完成。

建议旁边红字说明：

```text
已审页面按记录确认，修订问题与匿名性单独复核。
```

未审阅时写“人工逐页与匿名性检查待进行”；只有完成全部页面才能写“全部页面已审阅”。

## 17. 整体本地核验：通过哪些，失败哪些

### 17.1 本章是可选的全流程复验

`verify_release.py` 会重新执行整套检查，**不会替你打包或上传**。

它比单项测试耗时更长，包含工程测试、历史诊断、冻结请求、规模性能、服务完整性、材料和隐私等。

本手册已逐项试跑的范围见[本次核验记录](48_测试操作指南核验.md)。没有重新执行整套入口时，不能把先前的“17 项通过”说成此次全量实测。

建议顺序：

1. 先完成第 9 至 13 章，确认运行功能和数值。
2. 由文档操作者正常关闭 Office，避免锁文件使材料／隐私检查失败。
3. 检查没有把真实案例、数据库或凭据放进公开目录。
4. 停止自己的网页服务及其他本工程性能任务。
5. 新建独立输出目录，运行本章。

### 17.2 选择新目录，日志不要放进去

在窗口 C 执行：

```powershell
$ReleaseDir = Join-Path $Run 'full-local-verification'
if (Test-Path -LiteralPath $ReleaseDir) { throw '请换一个新的完整核验目录。' }
Write-Host "完整核验目录：$ReleaseDir"
```

先不要在 `$ReleaseDir` 内创建日志、截图或说明文件。该入口要求目录不存在或为空；提前写一个日志就会触发拒绝。

已有第 1.10 节 Transcript 在 `$Run` 外层记录即可。不要为重跑删除旧的完整核验目录。

建议红框框选：本轮新的 `full-local-verification` 路径和外层日志位置。

建议旁边红字说明：

```text
本轮核验使用新目录，保留旧报告不覆盖。
```

### 17.3 执行整套检查

```powershell
& $Py -B -X utf8 -S scripts/verify_release.py --artifact-dir $ReleaseDir --sizes 100,1000,5000,10000 --rounds 30
$ReleaseExit = $LASTEXITCODE
Write-Host "本地完整核验退出码：$ReleaseExit"
```

运行期间可能长时间没有新输出，先等待，不要多开一份相同检查。

本入口会显式调用 `compileall`，即使命令带 `-B`，也可能生成被 Git 忽略的 `__pycache__`。这不表示运行源码被修改。

正常完成后应产生：

```text
full-local-verification/
  final_verification.json
  final_verification.md
  requests.json
  evaluation_v3.json
  ablations.json
  service_workload.json
  actions.json
  action-readiness.json
  ...其他诊断和性能报告
```

程序提前报错时不保证有最终 JSON，应保留终端异常。不要手工创建一份“通过”的 JSON 补齐。

建议红框框选：本轮执行命令、原始退出码和实际生成的最终报告文件。

建议旁边红字说明：

```text
整套检查已结束，逐项结论以本轮报告为准。
```

本句不等于 17 项均通过。若提前异常且无最终报告，改为“整套检查中途失败，终端异常已保留”。

### 17.4 展开 17 项门禁

```powershell
$FinalPath = Join-Path $ReleaseDir 'final_verification.json'
if (-not (Test-Path -LiteralPath $FinalPath)) { throw '没有最终报告，先查看终端日志。' }
$Final = Get-Content -Raw -Encoding UTF8 -LiteralPath $FinalPath | ConvertFrom-Json
$Final | Select-Object generated_at_utc,local_release_checks_passed,competition_submission_ready | Format-List
$Final.checks.PSObject.Properties |
    Select-Object Name,Value |
    Format-Table -Wrap
$Final.checks.PSObject.Properties |
    Where-Object { $_.Value -ne $true } |
    Select-Object Name,Value |
    Format-Table -Wrap
```

最后一张表没有行，才表示本报告的 17 项均通过。

| 常见字段 | 含义 |
| --- | --- |
| `compile` | 运行模块、脚本、测试可编译 |
| `unit_tests` | 工程 unittest 成功 |
| `source_syntax_and_privacy` | Python 3.10 语法和公开文件隐私联合检查 |
| `frozen_request_gate` | 冻结五项数值、分母、参数、安全条件联合检查 |
| `frozen_dataset_bytes` | 固定数据原始字节未变 |
| `source_unchanged_during_checks` | 本次执行期间运行文件未变 |
| `request_source_snapshot` | 请求报告与执行源码一致 |
| `evaluation_protocol`／`internal_quality_85` | v3 切分口径和其自身质量门槛 |
| `benchmark_500ms` | 该规模性能入口定义的 500 ms 条件 |
| `service_workload_integrity` | 实际服务目标命中及持久化完整性 |
| `decay_diagnostics`／`action_framework` | 机制诊断与行动框架自检 |
| `local_preflight` | 本地演示预检 |
| `materials`／`editable_materials` | 汇总脚本已有材料清单与相应 Office 检查 |
| `privacy_scan` | 扫描范围内没有意外隐私项 |

其中已有 `editable_materials` 不能替代第 16.9 节对最新 `revised` 材料的严格核验。

建议红框框选：本轮生成时间、全部 17 个检查及其 `True`、本地通过字段与正式就绪 `False`。

建议旁边红字说明：

```text
本轮 17 项本地门禁通过，正式验收仍独立进行。
```

只在本节真正重新执行并取得完整通过报告后使用。没有重跑时，历史报告必须标注“历史本地核验”，不沿用“本轮”。

### 17.5 进一步检查分母和隐私失败

```powershell
$Final.unit_tests | Select-Object passed,tests_run,returncode | Format-List
$Final.request_metrics | Format-List
$Final.request_counts | Format-List
$Final.request_gate | ConvertTo-Json -Depth 8
$Final.privacy_scan.unexpected_findings | Format-Table -Wrap
```

本地合格是 `local_release_checks_passed=true`；正式就绪是另一个字段 `competition_submission_ready`。后者仍要实际环境、正式指标和外部材料，不能因为前者 True 就自动宣称赛事通过。

建议红框框选：实际测试数、指标分母、请求门禁和隐私扫描范围及结果；异常项不公开敏感原值。

建议旁边红字说明：

```text
本地数值、分母与扫描结果逐项核对，不替代正式验收。
```

### 17.6 只做语法与公开隐私检查

不需要整套复验时，可单独执行：

```powershell
& $Py -B -X utf8 -S scripts/check_source.py
$SourceExit = $LASTEXITCODE
Write-Host "语法与隐私检查退出码：$SourceExit"
```

本版会解析 130 个运行 Python 文件，并扫描公开文本、Office 和允许范围内的压缩文件。它**不是只检查语法**。

可能看到：

```text
{'python_310_syntax_files': 130, 'privacy_findings': 2}
```

这是格式示例，意外项数量以当次为准。如果隐私项大于 0，即使 130 份语法全部通过，整体也不能称为通过。

用户打开 Office 时生成的 `~$` 文件会被视为无法扫描的 Office，可能导致非零退出。安全处置：

1. 确认是正在编辑的文档锁，而非未知文件。
2. 让文档操作者正常保存和关闭；不要删除锁文件或强制关闭软件。
3. 重新扫描，使用新的运行记录。
4. 仍有失败时检查具体路径和类型，不添加放宽规则的白名单。

若本次只扫描新增 Markdown，应写“本次新增文档范围内通过”，不能写“整个工作区隐私通过”。

| 实际画面 | 建议红框框选 | 建议旁边红字说明 |
| --- | --- | --- |
| 本节完整入口通过 | 实际解析文件数、扫描范围、意外项 0 和退出码 0 | 本轮公开范围语法与隐私检查通过，不含图片 OCR。 |
| 本节发现隐私项或不可读锁文件 | 实际报错类型、意外项数量和非零退出码；遮挡个人信息 | 本轮扫描未通过，需处理具体问题后复查。 |
| 仅本次文档限定扫描 | 扫描的 Markdown 文件清单与通过状态 | 仅列出的文档扫描通过，不代表全工作区通过。 |

### 17.7 旧脚本提示不替代最新提交规则

历史交接文档和 `verify_release.py` 的静态外部事项仍可能出现旧的“7 分钟”或邮件措辞。本次只编写指南，不修改绑定既有证据的运行脚本。

正式材料应按已核对的最新官方文件执行：

| 项目 | 最新核对口径 |
| --- | --- |
| 项目报告 | PPT 格式 1 份 |
| 技术方案 | 按提交要求提供；本工程目前按负责人要求交付 Word，PDF 自行转换 |
| 演示视频 | 5–10 分钟 |
| 提交压缩包 | ZIP，不超过 200M |
| 截止时间 | 2026 年 9 月 15 日 24:00 |
| 提交方式 | 指定一人扫码提交，以首版为准 |

具体匿名性、文件命名和其余材料仍须完整核对官方原件。规则核对记录及原件摘要见[第 47 号文档](47_精简PPT与评分重点Word修订核验.md)。

这张表不是现在要求打包或提交。当前仍按负责人要求：**先审阅，不打包，不上传，不自动推送**。

### 17.8 怎样判断“本轮测试结束”

不是终端所有文字都变成绿色，而是：

- 每个计划执行的项目有实际输出与退出码。
- 每个失败能定位到文件、请求或前置条件。
- 预期安全拒绝与真正缺陷已经区分。
- 本轮新测、历史引用、可选未执行三类清楚分开。
- 复杂召回、拒答、干扰和延迟没有相互替代。
- SDK、V11、真实 Agent/Judge、真实案例和赛事流程的边界没有被抹去。
- 未执行或待复测项明确记录，交给对应负责人。

## 18. 故障排查：按屏幕现象处理

### 18.1 先做这五件事

1. 暂停后续步骤，记下最后一条命令和完整报错。
2. 看自己处于窗口 A 还是 C，是否误在服务窗口输入了测试命令。
3. 执行 `Get-Location`，确认位于本工程根目录。
4. 确认本轮编号、解释器、端口、数据库路径。
5. 保留已有输出；新试验换新文件，不删除失败结果。

可在窗口 C 执行以下只读检查：

```powershell
Get-Location
Write-Host "Python：$Py"
Write-Host "源码：$env:PYTHONPATH"
Write-Host "本轮：$Run"
Write-Host "数据库：$WebDb"
Write-Host "地址：$Base"
if ($Py) { Test-Path -LiteralPath $Py }
if ($Run) { Test-Path -LiteralPath $Run }
if ($WebDb) { Test-Path -LiteralPath $WebDb }
```

空白变量首先说明该窗口未初始化，不能据此认定工程损坏。

建议红框框选：当前窗口的工程名、解释器、轮次、数据库名、地址及路径检查结果；先遮挡个人目录。

建议旁边红字说明：

```text
先核对当前窗口与本轮参数，再定位故障。
```

### 18.2 环境和命令错误

| 屏幕现象 | 常见原因 | 处理顺序 |
| --- | --- | --- |
| 找不到工程路径 | 路径未加引号、复制错目录、另一个用户名 | 从资源管理器地址栏复制完整路径，重做 1.2 |
| `python` 不是命令 | Python 未安装或 PATH 未生效 | 试 `py -3 --version`；仍失败再安装并重开终端 |
| 跳转 Microsoft Store | 命中了系统应用执行别名 | 使用已安装的 `py -3` 或实际 Python 路径创建 venv |
| `No module named os_agent_memory` | 当前目录或 `PYTHONPATH` 错误 | 重做 1.2、1.6，并显式调用 `$Py` |
| `$Py` 只显示路径 | 忘记调用符 `&` | 使用 `& $Py ...` |
| `Activate.ps1` 被禁止 | PowerShell 执行策略 | 不要求激活，直接使用 `.venv\Scripts\python.exe` |
| pip 联网失败 | 构建工具下载受限 | 核心按 1.6 源码方式离线运行；材料检查单独处理 |
| `No module named docx/pptx/PIL` | 材料依赖没装或用了 `-S` | 按 16.8 在同一解释器安装；材料命令去掉 `-S` |
| `node` 找不到 | 没有 Node.js | 只将第 9.6 节记为未执行，Python/Web 不依赖 Node |
| 中文乱码 | 终端或文件编码不一致 | 重做 1.6；JSON 使用 UTF-8，读取加 `-Encoding UTF8` |
| 一直显示 `>>` | 粘贴漏掉右括号、引号或 here-string 终止行 | 按 `Ctrl+C` 取消当前多行输入，完整重贴该代码块 |
| 报“参数无法绑定” | 把 `PS ...>`、说明文字或 Linux 命令一起粘贴 | 只复制相应 `powershell` 代码块，不复制提示符 |

代码块中的多行数组、函数、`try/catch` 和 JSON 是完整一组，不要只执行中间一行。

### 18.3 网页打不开或按钮没反应

| 现象 | 判断方法 | 处理 |
| --- | --- | --- |
| 浏览器拒绝连接 | 窗口 A 是否显示服务已启动 | 按 4.2 启动，保持窗口不关闭 |
| 用 `https://` 打不开 | 地址协议不符 | 使用 `http://127.0.0.1:18765` |
| 端口被占用 | doctor 或服务提示 bind 失败 | 按 1.8 换空闲端口，同时更新 A、C 和浏览器 |
| 页面打开却接口失败 | C 中 GET `/api/stats` 是否成功 | 核对端口及服务；不要直接双击 `dashboard.html` |
| 旧页面内容未刷新 | 服务正常但前端缓存旧 | 浏览器 `Ctrl+F5`，重新确认作用域 |
| 数字变少或搜不到 | 已执行演示切换或遗忘 | 查看当前作用域和数据状态；不要急于重建库 |
| 按钮呈等待状态 | 请求尚未结束或服务异常 | 先看窗口 A 和浏览器开发者工具 Network，不连点 |
| 点击冲突后规则反了 | 按按钮文案猜版本，未看正文 | 按 5.5 根据 pending 与 existing 的实际内容决策 |

只在自己电脑浏览时，不需要路由器端口映射、外网 IP、TLS 证书或关闭防火墙。

### 18.4 HTTP 400、403、404、500

| 状态／错误 | 是预期还是故障 | 先检查什么 |
| --- | --- | --- |
| 400，缺少租户／用户 | 安全负例中预期 | JSON 是否含正确的 `tenant_id`、`user_id` |
| 400，遗忘计划过期 | 超时测试中预期 | 创建时间、300 秒有效期；正常流程应重新预览 |
| 400，计划不存在 | 不足以证明越权拦截 | ID 是否来自当前服务，是否重启前未确认计划 |
| 403，其他主体确认遗忘 | 第 8.3 节预期 | 核对主体确实不同、计划还有效、数据未被删除 |
| 404，路径不存在 | 常见为手输路径错 | 用 `/api/search` 等实际入口，不套用参考项目 API |
| 500 | 真实异常，需要留证 | 请求 JSON、服务异常、数据库状态及源码版本 |
| 200 和空数组 | 需结合题目判断 | 无答案／越域可正确，正例则可能漏召回 |
| 200 但正文命中错对象 | 检索失败 | 保留问题、期望对象、返回标题与正文，不以非空算成功 |

错误响应正文经常比状态码更具体。使用 `try/catch` 时，查看 `$_.ErrorDetails.Message`，不要把所有异常都吞掉后打印“符合预期”。

故障截图可直接采用以下红字，但必须符合右侧条件：

| 建议红框框选 | 建议旁边红字说明 | 使用条件 |
| --- | --- | --- |
| 缺作用域请求、400 与响应原因 | 缺少作用域被拒绝，符合本例预期。 | 对应第 7.4 节负例，不是任意 400 |
| 错主体、403 与仍存在的目标 | 跨主体确认被拒绝，目标未被删除。 | 计划有效，且拒绝后已查询验证 |
| 404 与实际请求路径 | 接口路径不匹配，先核对请求地址。 | 已确认请求路径错误，不当成安全成功 |
| 500 与服务异常 | 服务出现异常，本轮失败待定位。 | 保留异常与输入，不吞掉错误 |
| 正例问题、空结果或错误对象 | 正例未得到正确证据，本例失败。 | 该题真值有答案，不当成正确拒答 |

### 18.5 接入成功，却检索不到

按这个顺序排查：

1. `accepted_records` 是否真正大于 0；如果是重复事件，检查 `duplicate_records`。
2. `rejected_records` 和 `issues` 是否有字段、类型、时间等错误。
3. 接入报告的 `knowledge` 列表中是否有目标知识，不能把事件接受数当知识数；没有目标时继续查看 `promotion_decisions`。
4. 文本是否符合当前规则抽取条件；手册例子包含足够长度与“流程说明／规则说明”。
5. 是否把信息提成了偏好，而不是知识。
6. 请求租户、用户、场景与入库记录是否一致。
7. 是否被冲突隔离、过期、删除或遗忘。
8. 是否存在显式过滤词、主体限制或最低分数条件。
9. 最后才判断是否属于检索算法漏召回，保留原请求。

不要增加真实个人信息或任意扩大租户来让查询“有结果”。测试仅使用手册合成数据。

### 18.6 PowerShell 数组和 JSON 的常见误判

| 现象 | 原因或处理 |
| --- | --- |
| HTTP 返回 `[]`，却算出数量 1 | Windows PowerShell 可能保留顶层数组对象；使用第 6.3 节辅助函数展开 |
| 只有一个结果时 `.Count` 不稳定 | 用 `@(Post-MemoryJson ...)` 统一成数组，再看 `.Count` |
| `Format-Table` 里出现 `...` | 表格显示截断，不一定数据丢失；换 `Format-List` 或 `ConvertTo-Json -Depth 20` |
| JSON 写成 `System.Object[]` | 不能直接把对象转成普通字符串保存；使用 `Save-GuideJson` |
| 中文请求变问号 | 使用 UTF-8 字节和 `application/json; charset=utf-8`，按辅助函数发送 |
| 变量在另一窗口为空 | A 和 C 不共享变量；按 4.4 重建 C 的环境 |
| 数值 `1` 被看成 1% | 质量字段是 0–1 比例；1 表示 100% |

不要仅凭控制台的缩略显示修改原报告。先用结构化 JSON 核对。

### 18.7 遗忘后数据似乎“回来了”

1. 核对遗忘是否真的确认，是否只有预览。
2. 核对 `knowledge_ids`、主体和场景是否就是当前查询对象。
3. 核对确认返回 `confirmed=true`，而非异常被误当成功。
4. 核对重启使用相同的 `$WebDb`，没有运行 `build-store` 或场景重置。
5. 核对是不是另一个标题相似但 ID 不同的记录。
6. 用相同 `plan_id` 检查持久化回执，比较 `audit_id`。
7. 重发相同事件应判重复；若实际产生新的来源事件，不要混同为同一去重测试。

若以上均正确却发生复活，属于持久化或索引一致性问题，保存数据库和日志，停止对这份库继续写入。不要删除库重建后声称问题消失。

### 18.8 冻结或复杂评测失败

| 提示／现象 | 定位动作 |
| --- | --- |
| 冻结数据摘要不符 | 检查是否编辑、重新生成或行尾转换了固定 JSON，不修改预期摘要 |
| 样本数不足或重复 | 检查原始逐题列表，不复制样本凑分母 |
| `source_unchanged_during_run=false` | 测量期间有人编辑运行文件，保留本轮；稳定版本后新开一轮 |
| Recall 高但完整率没过 | 找出每题缺少的证据 ID，尤其多文档问题 |
| 正例全过但拒答失败 | 查看无答案返回的近似词／错误关系，不能只报正例 |
| 作用域泄漏 | 优先处理安全失败，不能由高平均分抵消 |
| 干扰率仍非零 | 当前已知边界，报告 P@3 和实际干扰；完整率不能替代精度 |
| P95 大于 500 ms | 检查计时边界、负载、规模、全部耗时和首查，另开新轮串行复验 |
| 开发脚本退出 0，旧策略却失败 | 该入口只约束执行异常，需看策略 `summary`，见 11.11 |
| 新 H7/H70 无约束返回 H70 | 本次已复现的额外风险，见 7.7，不改题或静默加约束算通过 |

三策略比较器报错请按 12.6 处理。不要为取得更高速度启用已知损害完整召回的旧实验。

建议红框框选：实际失败字段、请求 ID、期望与返回、配置和耗时，不只框总平均值。

建议旁边红字说明：

```text
失败按请求与配置定位，不删样本、不放宽门槛。
```

### 18.9 文件、权限和 Office 问题

| 现象 | 正确处理 |
| --- | --- |
| `refusing to overwrite` | 输出是不可覆盖证据，换新名字或新轮目录 |
| `PermissionError` 读 Word/PPT | 正常关闭占用文档后再读；不强制关闭他人应用 |
| 严格材料检查说不止一份 Word/PPT | 用 `Get-ChildItem -Force` 查看 `~$` 锁或额外文档；锁由原应用正常释放 |
| Office 输出摘要变化 | 确认是否保存过用户编辑；不要覆盖用户版本或直接改清单 |
| 根目录 `git status` 有 `.sqlite` | 数据库放错公开目录，先停止服务并交由负责人核查隐私 |
| `artifacts/runtime` 不出现在 Git | 预期忽略目录；本地文件仍存在，不代表已归档 |
| 完整核验目录“非空” | 日志／截图提前放入；另选新目录，日志留在外层 |
| 长路径／同步占用 | 保留原目录，优先让负责人确认同步及文件占用；不移动整个工程来试错 |
| 终端被安全策略拦截 | 记录实际拦截，不关闭全部防护，不默认管理员权限 |

建议红框框选：具体文件名、占用或拒绝覆盖的提示；个人路径须遮挡。

建议旁边红字说明：

```text
保留原文件，按占用或覆盖提示处理。
```

这只是处置原则，不能把权限异常或材料检查失败标成测试通过。

### 18.10 提交问题时提供什么

向项目负责人提供以下最小信息：

```text
测试编号：
本轮目录：
系统与Python版本：
源码版本或源摘要：
最后一条完整命令：
Python退出码：
期望结果：
实际结果：
对应JSON或日志：
失败请求ID：
是否已重试，重试输出放在哪里：
是否影响其他已通过项：
```

只发送经过审查的合成数据和脱敏日志。不要贴密钥、隐藏标签、真实聊天记录、报名表或整份私有数据库。

## 19. 测试记录和证据保存

### 19.1 每个输出文件在哪里

默认都在自己创建的 `$Run`，文件只在执行相应章节后出现：

| 文件／目录 | 对应章节 | 用途 |
| --- | --- | --- |
| `window-a.txt`、`window-c.txt` | 1.10，可选 | 终端过程日志 |
| `quick-legacy-v2.json`、`quick-frozen-requests.json`、`quick-demo.sqlite` | 3，可选 | 一键路线，不与后面的手工数据库混用 |
| `web.sqlite` | 4–8 | 本轮网页与接口合成演示库 |
| `http-evidence-example.json` | 7 | 有约束通过与无约束探索结果并列 |
| `http-forget-receipt.json` | 8 | 预览、确认和重复确认回执 |
| `unit-tests.txt` | 9 | 全部工程测试与退出结论 |
| `frozen-requests.json` | 10 | 五项指标、固定分母、逐请求和安全门禁 |
| `complex-default.json`、`constraints-default.json` | 11 | 两套复杂集完整矩阵 |
| `development.json`、`development-challenge.json` | 11.11 | 20+10 可见开发对照 |
| `comparison-original.json`、`comparison-enforce.json`、`comparison-none.json` | 12.2 | 既有同源证据重审，不是新测时延 |
| `policies-*-new.json` 及其 audit | 12.5，可选 | 新测三策略及对应比较器输出 |
| `evaluation-v3.json`、`ablations.json` | 13 | 历史切分和机制诊断 |
| `service-workload.json` | 13 | 命中、并发、HTTP、重启、CPU 与 RSS |
| `action-workspace/`、`actions-fixture.json` | 14 | 合成跨会话文件与后验结果 |
| `action-runtime.json`、`action-readiness.json` | 14 | 只读盘点与缺少的真实运行条件 |
| `native-discovery.json` | 15 | 实际 SDK 发现状态，不是 P95 |
| `full-local-verification/` | 17，可选 | 本轮完整 17 项及子报告 |

本指南作者的辅助核验还保存了 `http-walkthrough.json` 等额外文件；它们不是用户按步骤运行后必须同名产生的文件，区别见[核验记录](48_测试操作指南核验.md)。

### 19.2 列出本轮报告

在窗口 C：

```powershell
Get-ChildItem -LiteralPath $Run -File |
    Sort-Object Name |
    Select-Object Name,Length,LastWriteTime |
    Format-Table -Wrap
```

检查文件不是 0 字节、时间属于本轮。子目录报告另进入对应目录查看；不能把旧时间文件作为新测输出。

查看某一份 JSON：

```powershell
Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $Run 'frozen-requests.json') |
    ConvertFrom-Json |
    Select-Object generated_at_utc,metrics,observation_counts,official_validation_ready |
    Format-List
```

`generated_at_utc` 是 UTC 时间，通常比北京时间少 8 小时，不一定是机器时钟错误。

建议红框框选：本轮报告文件名、非零长度、写入时间和 JSON 内的生成时间，个人目录遮挡。

建议旁边红字说明：

```text
本轮报告逐份留存，文件时间与报告内容对应核查。
```

文件存在只证明已产生输出，是否通过仍看其内容。

### 19.3 为关键报告计算摘要

报告生成并停止写入后：

```powershell
$KeyReportPaths = @(
    (Join-Path $Run 'frozen-requests.json'),
    (Join-Path $Run 'complex-default.json'),
    (Join-Path $Run 'constraints-default.json'),
    (Join-Path $Run 'service-workload.json')
)
foreach ($Path in $KeyReportPaths) {
    if (Test-Path -LiteralPath $Path) {
        Get-FileHash -LiteralPath $Path -Algorithm SHA256 |
            Select-Object Path,Hash
    } else {
        Write-Host "尚未执行或文件缺失：$Path"
    }
}
```

摘要用于确认文件是否改变，不证明独立身份、第三方审核或比赛认可。

原始字节 SHA256 与源码的 CRLF-to-LF 规范化摘要用途不同。不要自行把报告转换换行、重新排版 JSON 后还沿用旧原始摘要。

建议红框框选：实际文件名、`SHA256` 算法和完整摘要；长摘要换行显示，不只圈前几位。

建议旁边红字说明：

```text
SHA256 用于核对文件一致性，不是第三方认证。
```

### 19.4 可直接使用的测试结果模板

在自己的内部测试记录中按以下格式填写；空白模板没有预设“通过”：

```markdown
# OS Agent 本轮测试记录

日期与时区：
操作者内部代号：
工程路径：
本轮编号：
系统／CPU／内存：
Python版本：
源码Git版本：
是否存在尚未提交的运行代码改动：
模型及配置：
本轮报告目录：

| 编号 | 项目 | 期望条件 | 实际结果 | 退出码 | 证据文件 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | doctor与CLI | 核心可运行，外部风险单列 | 待填写 | 待填写 | 待填写 | 未执行 |
| T02 | 网页及接入 | 当前作用域、偏好、冲突、去重正确 | 待填写 | 不适用 | 待填写 | 未执行 |
| T03 | 作用域与拒答 | 错作用域空返回、缺作用域被拒绝 | 待填写 | 待填写 | 待填写 | 未执行 |
| T04 | 两阶段遗忘 | 预览不删、越权拒绝、确认与重启幂等 | 待填写 | 待填写 | 待填写 | 未执行 |
| T05 | 工程测试 | 实际测试数、失败、跳过逐项记录 | 待填写 | 待填写 | 待填写 | 未执行 |
| T06 | 冻结五项 | 固定分母、五项和安全门禁通过 | 待填写 | 待填写 | 待填写 | 未执行 |
| T07 | 复杂原集 | 每格每轮完整、拒答、安全与P95通过 | 待填写 | 待填写 | 待填写 | 未执行 |
| T08 | 复杂约束集 | 开关两种模式均按严格条件检查 | 待填写 | 待填写 | 待填写 | 未执行 |
| T09 | 三策略对照 | 七项门禁，同源、逐请求配对 | 待填写 | 待填写 | 待填写 | 未执行 |
| T10 | 服务负载 | 目标命中、HTTP和重启，资源边界清楚 | 待填写 | 待填写 | 待填写 | 未执行 |
| T11 | 行动fixture | 5会话50轮、12文件；不是模型成绩 | 待填写 | 待填写 | 待填写 | 未执行 |
| T12 | SDK／V11 | 按实际环境与运行证据判断 | 待填写 | 待填写 | 待填写 | 未执行 |
| T13 | 材料与隐私 | 正确版本、严格核验、人工视觉 | 待填写 | 待填写 | 待填写 | 未执行 |
| T14 | 新探索案例 | H7/H70无约束返回对象正确且找齐 | 待填写 | 待填写 | 待填写 | 未执行 |

通过项：
失败项与失败请求ID：
预期拒绝项：
未执行项及原因：
本轮新测与历史引用的区别：
已知风险及后续负责人：
是否修改或覆盖既有证据：否／说明
是否打包、推送或正式提交：否／另附授权与回执
```

建议结论只用“通过”“失败”“预期拒绝”“未执行”“待复测”，不把“命令执行完了”当作统一通过。

建议红框框选：实际填写的结论、退出码与对应证据文件；空白模板不作为完成证明。

建议旁边红字说明：

```text
通过、失败、预期拒绝与未执行分别登记。
```

### 19.5 保存哪些截图最有用

| 编号 | 建议画面 | 应同时保留／红框重点 | 建议旁边红字说明 |
| --- | --- | --- | --- |
| S01 | doctor 和 CLI 结尾 | 命令、版本、退出码、警告边界 | 本地预检与 CLI 流程通过，外部验收另列。 |
| S02 | 网页偏好和版本变化 | 合成场景、当前作用域、新旧偏好与版本 | 本例偏好更新与版本变化可追溯。 |
| S03 | 冲突决策前后 | 原规则、待决规则、选择依据及最终状态 | 待决规则经明确处置后再核对生效结果。 |
| S04 | 查询与拒答 | 完整问题、约束、标题与关键正文、空结果 | 按当前问题与约束核对返回证据。 |
| S05 | 遗忘预览和确认 | 目标数、确认状态、脱敏审计 ID | 先预览范围，确认后软删除并生成回执。 |
| S06 | 重启后再次查询与回执 | 同一路径、本次服务、同一审计 ID | 原库重启后遗忘状态与回执保留。 |
| S07 | 五项指标及门禁 | 数值、分母、Hash、正式就绪 False | 本轮 Hash 冻结指标通过，仍待正式验收。 |
| S08 | 复杂集所有格和轮次 | 规模、干扰、完整率、拒答、P95 | 指定复杂矩阵逐格逐轮通过，干扰仍单列。 |
| S09 | 三策略与风险 | 比较对象、开销、SDK 风险与外部边界 | 新旧策略配对复核，真实 SDK 仍待复测。 |

这是组合画面的总说明。某一张只展示一个步骤时，优先采用该节更具体的红字；S07、S08 等通过句必须有该轮完整通过证据。

截图不能替代逐请求 JSON。录屏时遮挡个人目录，公开材料中不展示 Windows 用户名、学校、姓名、聊天通知或私有仓库凭据。

### 19.6 保存数据库时先停止服务

不要在数据库持续写入时仅复制一个 `.sqlite` 文件，就宣称已得到一致快照。SQLite 可能还有 WAL 或其他关联状态。

简单、稳妥的内部留存方式：

1. 按第 21.1 节停止本轮服务，等待进程退出。
2. 确认没有其他本工程测试正在写同一数据库。
3. 通过文件管理器，将本轮目录作为整体复制到负责人批准的私有留存位置。
4. 不覆盖旧轮次，记录复制时间及文件摘要。
5. 数据库、原始日志不直接加入公开 Git 或匿名赛事包。

重要报告要由负责人单独审核后归档。`artifacts/runtime` 被忽略不等于已备份，也不等于自动允许公开。

建议红框框选：服务已停止的记录、留存轮次目录名和摘要登记，不展示私有目录内容。

建议旁边红字说明：

```text
停写后留存本轮目录，原始报告不覆盖。
```

仅在实际完成停写与留存后使用；仅看到忽略目录仍存在，不等于完成备份。

## 20. 5–10 分钟演示路线与录屏检查

### 20.1 录制前先完整演练一次

先离线完成全部需要的测试并留存报告，再录制，不在视频中等待数分钟自动测试。

准备：

1. 本轮服务正常，地址和窗口 A/C 对齐。
2. 使用合成数据，已关闭个人聊天、通知和真实文档。
3. 浏览器全屏或最大化，检查字体和按钮完整显示。
4. 按 5.1 准备演示场景，确认偏好和冲突的实际内容。
5. 预先准备第 7 章接口输入和自己的报告目录。
6. 方案用最新 20 页 PPT，不需要在视频里逐页读完。
7. 若展示已生成结果，说明它是哪次运行的报告，不伪装成刚刚测得。

演示场景重置会改变合成数据库。只能在专用演示库执行，不能对真实案例库点击重置。

建议红框框选：合成作用域、实际服务地址与所展示报告的轮次，避免把个人桌面一并录入。

建议旁边红字说明：

```text
演示使用合成数据，指标注明实际报告轮次。
```

### 20.2 建议的约 8 分钟流程

| 视频时间 | 操作 | 可以说明的事实 |
| --- | --- | --- |
| 00:00–00:40 | 项目名、应用问题与初版状态 | OS 记忆治理，当前待赛事验收 |
| 00:40–01:25 | PPT 总体架构及检索框图 | 多源接入、两类记忆、证据选择、治理与持久化 |
| 01:25–02:20 | 网页偏好修正和历史 | 当前值、来源证据及版本变化 |
| 02:20–03:10 | 展示隔离冲突，按内容决策 | 待确认规则不直接覆盖有效规则 |
| 03:10–04:10 | 合成事件接入、重复接入、检索及作用域负例 | 接受与去重计数、正确主体能读、错误主体不能读 |
| 04:10–05:10 | 显式 H7 约束下的两份证据、无支持属性拒答 | 条件已声明，不把显式约束隐去 |
| 05:10–06:10 | 遗忘预览、确认、再次检索 | 先看影响范围、确认后删除、返回审计回执 |
| 06:10–07:20 | 本轮五项、复杂矩阵和比较器报告 | 固定分母、干扰、逐轮 P95、质量与代价 |
| 07:20–08:15 | 四个评分重点及待验收项 | 相关工作、创新边界、可信度；SDK、V11、真实模型和新反例风险 |

时间只是建议，不是必须按秒切分。最终成片控制在官方 5–10 分钟范围，且不要超速翻页导致看不清。

### 20.3 可以采用的简短讲解

**展示总体架构时：**

> 本系统把 OS 交互、显式配置和工具反馈等事件，统一为带来源和作用域的记忆。检索以当前用户的有效记录为基础，冲突进入人工确认，遗忘通过预览和确认更新存储及索引。

**展示复杂检索时：**

> 这一例明确传入型号约束，要求同时找齐流程和审核要求。我们同时测试无答案与相似型号干扰，完整召回、拒答和精确率分别统计。

**展示结果时：**

> 这里是指定源码、HashEmbedding 和公开合成回归的结果。P95 来自完整逐请求记录，80 个查询按 nearest-rank 计算；它不代表真实 SDK 或 Agent 最终答案端到端耗时。

**说明风险时：**

> 当前已完成初版，待赛事验收。真实 SDK 时延仍待复测，当前 V11、独立 Agent/Judge 与授权案例需要补证。额外无约束近似型号例仍有失败，我们保留反例，不把已通过回归外推为通用正确。

数值采用自己实际报告，不硬背本文作者的机器耗时。

### 20.4 演示时不要说这些话

| 不应说 | 更准确的说法 |
| --- | --- |
| “所有复杂问题都已解决” | 指定复杂回归通过，探索反例与泛化仍单列 |
| “SDK 检索仅 50 ms” | 本机 Hash 进程内服务 P95；真实 SDK 待复测 |
| “76 项独立官方请求全过” | 单一公开 fixture 的相关检查，不是独立官方请求 |
| “自带登录安全认证” | 当前是仅供本机演示的作用域隔离 |
| “点击遗忘就永久擦除磁盘” | 当前存储与索引删除，备份和磁盘擦除另有边界 |
| “点击系统动作会真的操作电脑” | 本地演示不执行任意系统 Shell |
| “通过了所有正式验收” | 本地核验与赛事验收分开 |
| “图表清晰，负责人已经批准” | 布局核验与负责人实际审阅是两件事 |

### 20.5 导出视频后的检查

1. 从头到尾实际播放一次，不只看首帧。
2. 确认 5–10 分钟、声音清楚、操作顺序可辨。
3. 检查窗口切换是否意外出现个人路径、通知、账号或私有数据。
4. 检查所有引用指标与本轮或明确注明的历史报告一致。
5. 检查字幕没有把 Hash 写成真实 SDK，没有裁掉风险边界。
6. 保留原视频和最终导出版本的文件摘要。
7. 正式命名、匿名性、包大小和提交方式最后对照官方文件，不自动上传。

本手册提供录制流程，不表示已经制作或通过审核的视频存在。

导出后额外检查红框红字：

- 暂停到每个标注画面，确认红框圈的是实际结果，未覆盖命令、正文、失败项或风险字段。
- 确认红字与当前帧一致，没有把前一步的成功字幕留到后一步失败画面。
- 同一框与文字保持就近对应；多框时分别编号，不让观众猜说明指向哪一处。
- 在最终分辨率播放，确认红字可读、不出边界，长句分为两行。
- 展示历史报告时保留日期或轮次说明；不要用编辑过的红字替换程序原始数值。

### 20.6 常用红框与红字速查

下面的短句可以直接放在红框附近。**先核对对应章节的使用条件，只有实际通过时才用通过句；历史报告注明历史轮次。** 这张表不是本次执行清单，也不说明已经制作带标注的截图或视频。

| 步骤／画面 | 红框重点 | 旁边红字短句 |
| --- | --- | --- |
| 2.1 本地预检 | 本地就绪、阻塞项、退出码及外部警告 | 本地演示预检通过，SDK 与麒麟平台另行验收。 |
| 4.3 网页打开 | 本地地址与演示台标题 | 本地演示台已打开，后续逐项验证功能。 |
| 5.3 偏好变化 | 新旧值与版本历史 | 本例偏好已更新，历史版本可查看。 |
| 5.4 冲突待决 | 相反规则正文与待决状态 | 相反规则已进入待决区，等待明确处置。 |
| 5.5 冲突处置 | 实际选择、两条状态与重新检索结果 | 按规则正文完成处置，生效结果已核对。 |
| 5.6 遗忘预览 | 影响范围及预览后仍存在的记录 | 预览只展示影响范围，尚未执行删除。 |
| 5.7 软删除 | 回执、已遗忘状态与空结果 | 本例软删除后不再召回，不代表磁盘安全擦除。 |
| 5.8 用户切换 | 本人、其他用户、切回本人三张结果 | 本人可见、其他用户不可见，切回本人仍可见。 |
| 6.1 首次接入 | 接入计数与可检索正文 | 合成事件已接收，并形成可检索知识。 |
| 6.2 重复接入 | 接收 0、重复 1、知识未增加 | 重复事件已去重，未新增同一份知识。 |
| 6.6 错误事件 | 拒绝计数与缺少正文的原因 | 缺少正文的事件被拒绝，原因已记录。 |
| 7.2 证据归因 | 默认策略名与实际证据字段 | 默认聚焦证据策略生效，返回依据可查看。 |
| 7.4 缺少作用域 | 不完整请求与 HTTP 400 | 缺少作用域的请求被拒绝，符合本例预期。 |
| 7.5 两份 H7 证据 | 显式 H7 约束、两份 H7、无 H70 | 显式型号约束下，两份 H7 证据完整召回。 |
| 7.6 无支持属性 | 保险币种问题与返回 0 | 本例缺少保险币种证据，正确返回为空。 |
| 7.7 无约束反例 | 问题 H7、去掉约束、返回 H70 | 新增反例：无约束时返回 H70，本例失败。 |
| 8.3 跨主体确认 | 错主体、403 与目标仍在 | 跨主体确认被拒绝，原目标未被删除。 |
| 8.5 重复确认 | 两次审计 ID 与相等标志 | 重复确认返回同一回执，不重复执行删除。 |
| 8.6 原库重启 | 遗忘为 0、同回执、重发判重复 | 原库重启后遗忘与回执保留，重发事件不复活知识。 |
| 8.7 到期计划 | 到期原因、400 与知识仍在 | 到期计划被拒绝，原知识仍保留。 |
| 9.2 全量回归 | 实际测试数、最终 OK、退出码与跳过 | 工程回归无失败，平台条件跳过项单列。 |
| 10.3 冻结五项 | 五项、分母、门禁、官方就绪 False | 本轮冻结指标与门禁通过，仍待正式赛事验收。 |
| 10.4 检索 P95 | 80 个服务查询、实际 P95、毫秒单位 | 服务检索 P95 达标，不含 SDK 与 HTTP 往返。 |
| 11.6 复杂矩阵 | 全部配置与轮次的质量、时延、失败数 | 全部配置逐轮核对，完整召回、拒答与时延均达标。 |
| 11.8 干扰结果 | 完整率、P@3 与实际干扰返回率 | 完整召回不等于零干扰，干扰返回率另行披露。 |
| 12.2 历史证据复算 | 三份历史输入、新输出及退出码 | 三份既有同源证据复算通过，本次未重新测时延。 |
| 12.3 七项门禁 | 检查结果、新默认通过、旧控制组失败 | 本组新策略七项门禁通过，旧控制组仍保留失败。 |
| 12.4 性能代价 | 同格旧默认与新默认 P95 | 本格新策略仍达时延门槛，但证据检查增加了耗时。 |
| 13.2 旧 v3 | 正例 11/12、无答案 6/6、原门槛 | 旧 v3 达自身门槛，但仍有 1 个正例未找齐。 |
| 13.4 服务负载 | 完整性与退出码，时延另列 | 服务负载完整性通过，时延条件继续单独核对。 |
| 13.6 资源 | 可用标志、RSS、生命周期峰值与范围 | 资源数值仅覆盖所列进程，高水位不是单配置峰值。 |
| 14.4 行动 fixture | 12/12 文件、记忆终态、Judge 未执行 | 自检 12 份文件与记忆终态通过，未执行真实 Judge。 |
| 14.6 条件缺失 | 缺项、未就绪与退出码 2 | 真实行动评测前置条件不足，缺项逐条保留。 |
| 15.2 SDK 未接通 | 未连接、0 次观察、空 P95 与风险 | 真实 SDK 尚未接通，时延仍为待复测风险项。 |
| 15.7 旧 V11 | 历史记录 7/8 与未通过项 | 旧 V11 记录仅 7/8，当前源码仍待独立复验。 |
| 16.4 相关工作 | 机制对比、适用边界与参考文献 | 相关工作按机制与边界对比，未作外部跑分排名。 |
| 16.5 技术创新 | 问题、框图、实现、证据与限制 | 创新主张对应实现、证据、代价与限制。 |
| 16.6 评测口径 | 分母、干扰、拒答、P95 与计时范围 | 分母、干扰、拒答与计时边界明确，按原始结果复核。 |
| 16.7 性能可信度 | 同条件对照、原始结果与风险 | 性能结论绑定原始证据，不利结果与外部边界单列。 |
| 16.9 材料核验失败 | Office 锁、实际异常与非零退出码 | Office 锁文件使本次严格核验失败，关闭文档后复跑。 |
| 19.3 报告摘要 | 文件名、算法与完整 SHA256 | SHA256 用于核对文件一致性，不是第三方认证。 |
| 21.1 正常停止 | 服务终端退出、端口查询及数据库保留 | 本轮服务已停止，数据库保留。 |

未运行某一步时，统一短句可用“本轮未执行此项，待条件具备后复测”；已失败时用“本轮失败，原始结果已保留”。不要用“已完成初版，待赛事验收”的项目总状态替代单项失败结论。

## 21. 结束测试、下次恢复和最终清单

### 21.1 正常停止自己的服务

在窗口 A：

1. 按 `Ctrl+C`。
2. 等待程序退出、PowerShell 提示符返回。
3. 若仍在退出，先等几秒，不连续粘贴其他命令。

窗口 C 验证端口状态：

```powershell
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

没有监听行通常表示端口已经释放。若当前权限不能查询，不把无输出直接当作已停止；回窗口 A 确认提示符已经返回，并按第 4.5 节检查原服务是否仍能响应。

仍有监听时先确认是否本次服务进程或其他程序。只允许停止已核实属于本次测试的进程；不要全局结束 `python.exe`，不要根据端口号猜测后直接强杀。

Ctrl+C 只停止服务，不删除数据库。无需管理员权限、重启电脑或清理整个工程。

建议红框框选：服务终端提示符返回、有效的端口查询无监听行，以及仍保留的本轮数据库文件名。

建议旁边红字说明：

```text
本轮服务已停止，数据库保留。
```

查询受限或服务仍能响应时，不使用“已停止”；先按上面的检查确认。

### 21.2 结束终端记录

仅在启动过 Transcript 的各个窗口执行：

```powershell
Stop-Transcript
```

没有活动 Transcript 时可能报“尚未启动”，只表示没有日志会话，不影响已生成的 JSON。

然后检查第 19 章报告清单、填写结论。未执行的可选章节保持“未执行”。

建议红框框选：实际 Transcript 停止提示及本轮日志文件名。

建议旁边红字说明：

```text
终端记录已结束，本轮日志留存。
```

没有启动过 Transcript 时不使用此句；JSON 报告是否存在另行核对。

### 21.3 下次继续同一个数据库

下一次打开 PowerShell：

1. 按 1.2 进入工程。
2. 按 1.5 取回 `$Py`，不要删除已有 venv。
3. 按 1.6 设置编码和源码路径。
4. 按 4.4 输入原来的本轮编号，恢复原 `$Run`、`$WebDb`、`$Base`。
5. 检查原数据库存在后，仅执行 4.2 的 `serve`。

不要先执行 `build-store`、`run_demo.ps1` 或演示重置，否则不再是“原数据库重启验证”。

如果要从头开始全新独立测试，则按 1.9 创建新轮次。旧目录继续保留，两种目的不要混淆。

建议红框框选：原轮次名、原数据库名、再次启动的地址，以及原记录的核对结果。

建议旁边红字说明：

```text
继续使用原数据库，未重建或重置演示。
```

### 21.4 最终检查清单

以下是操作者自行填写的空白清单，不预先替任何人宣布通过：

- [ ] 我使用的是本赛题工程，不是参考 SafeOps 工程的命令。
- [ ] 我记录了源码版本、环境、Hash/SDK 配置和本轮目录。
- [ ] 我验证了 CLI、网页、接口、作用域及正确的冲突决策。
- [ ] 我区分事件接受、知识抽取、重复接入和拒绝事件。
- [ ] 我验证了遗忘预览、越权拒绝、确认、幂等和原库重启。
- [ ] 我保留工程测试实际总数、失败数、跳过数和退出码。
- [ ] 我检查冻结五项的数值、分母、配置和附加安全门禁。
- [ ] 我检查两套复杂集全部配置、全部轮次及无约束模式。
- [ ] 我没有把完整召回等同于零干扰或最终答案正确。
- [ ] 我复核三策略七项门禁，并注明复算还是新测。
- [ ] 我记录 v3 和新增探索例中的失败，没有修改冻结标签。
- [ ] 我区分服务、HTTP、初始化、SDK、Agent 等计时边界。
- [ ] 我没有把 fixture 通过写成真实 Agent/Judge 或官方准确率。
- [ ] 我如实记录 SDK、V11 及外部验收的待复测条件。
- [ ] 我审阅最新 20 页 PPT 和详述 Word 的四个评分重点。
- [ ] 我区分历史材料核验、本次严格核验和负责人实际视觉审阅。
- [ ] 我的红框对应真实结果，红字与当轮证据、通过或失败状态一致。
- [ ] 我保留未标注原图，确认红字没有遮挡原始字段或风险说明。
- [ ] 我正常关闭自己的服务，保留日志、数据库和报告。
- [ ] 我没有删除用户文件、Office 锁文件或历史失败证据。
- [ ] 我没有在未获授权时打包、推送或执行正式提交。

### 21.5 进一步阅读

| 需要解决的问题 | 文档 |
| --- | --- |
| 本手册哪些命令实际运行过 | [本次指南核验](48_测试操作指南核验.md) |
| 运行配置与部署 | [部署手册](12_部署手册.md)、[可复现指南](14_可复现指南.md) |
| 具体 HTTP 字段及源码分工 | [API 文档](13_API文档.md)、[模块说明](15_源代码模块说明.md) |
| 冻结五项如何定义 | [逐请求与冻结基线](30_逐请求评测与冻结基线.md)、[评测可信度](39_评测口径与可信度.md) |
| 复杂集和新默认优化 | [复杂检索](40_复杂场景与检索性能复测.md)、[约束补测](41_复杂约束场景补测.md)、[优化验收](45_复杂拒答与完整召回优化验收.md) |
| 旧实验为何不能直接开启 | [正文证据检查与反例](44_正文证据检查与反例.md) |
| 相关工作与创新论证 | [相关工作](38_相关工作与创新边界.md)、[近期对照](43_近期相关工作与评测对照.md) |
| SDK 和 V11 的实际边界 | [SDK 证据](27_真实SDK接入与证据边界.md)、[V11 记录](31_麒麟V11客户机实测.md) |
| 真实 Agent/Judge 怎么交接 | [行动协议](26_官方行动评测协议.md)、[资源与外部交接](36_正式评测资源与外部交接.md) |
| 最新 20 页 PPT 与 Word | [修订核验](47_精简PPT与评分重点Word修订核验.md)、[交付目录](../deliverables/submission-materials-20260911-revised/README.md) |
| 私有案例和匿名发布 | [隐私发布边界](16_原创性与隐私发布边界.md)、[安全说明](../SECURITY.md) |

**最终原则：按真实输入操作，按实际报告判断；该通过的有证据，该失败的留记录，该等待外部验收的保持边界。**
