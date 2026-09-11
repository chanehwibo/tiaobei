# 20页PPT与评分重点详述Word生成工具

本目录只修订匿名Office材料，不修改运行算法、评测数据、配置或原始成绩。
本版交付与核验见[第47号文档](../47_精简PPT与评分重点Word修订核验.md)。
旧工具与旧材料原样保留，不覆盖其摘要或历史记录。

## 内容组织

| 输出 | 当前规模 | 组织原则 |
| --- | --- | --- |
| 项目报告PPTX | 20页，10张可编辑框图，7张原生表格 | 问题、方案、相关工作、创新、评测、结果、案例及验收 |
| 技术方案DOCX | 实际渲染66页，18章79节，25图49表 | 保留详细实现和用户手册，增加12节评分重点论证 |

PPT表格正文最小18pt，主要图形由原生形状、文字和连接线组成。
Word正文、标题、表格、目录页码域可编辑，方案框图为高清PNG。
四个评分重点在PPT正文中可见，不只藏在备注；每页备注包含论证边界、证据和Word节号。
Word页数来自本机WPS实际渲染，其他字体或排版引擎可能改变分页。

## 环境

沿用[原工具环境说明](../materials_20260911/README.md)：Windows、Python 3.14.3、
python-docx 1.2.0、python-pptx 1.0.2、Pillow 12.2.0；渲染使用本机WPS，
渲染核验使用PyMuPDF 1.27.2.3。生成器使用本机微软雅黑、宋体、Arial与Consolas字体。
核心工程仍要求Python 3.10或更高，不因材料工具升级运行依赖。

在项目根目录、独立虚拟环境中安装材料依赖：

```powershell
python -m pip install -e ".[deliverables]"
python -m pip install Pillow PyMuPDF
```

仅生成和结构核验时不需要PyMuPDF。该库采用AGPL-3.0或商业许可，应遵守所装版本许可；
仓库不分发该库、WPS或商业字体，见[第三方说明](../../THIRD_PARTY_NOTICES.md)。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `word_content.py` | 保留原67节并增加12节，展开相关工作、创新、口径和可信度 |
| `slide_content.py` | 20页独立叙事、简洁正文、备注与有效Word交叉引用 |
| `analysis.py` | 从绑定摘要的原始策略报告复算差值、计分算例及条件性区间说明 |
| `generate.py` | 两份Office、证据摘要、索引和生成清单；拒绝覆盖已存在目录 |
| `render.ps1` | WPS只读渲染，核对源文件未变，生成源与渲染输出摘要 |
| `qa.py` | 严格核验正文、备注、摘要、匿名性、图形、字体、分页及非空像素 |
| `test_revision.py` | 23项材料工具测试，包括删文、篡改摘要、风险只在备注等反例 |

复用原目录的字体、绘图和证据加载器，不改变其源码。生成器绑定两组工具的LF摘要，
以及149个运行文件、固定数据、原始报告和比较器结果。
`analysis.json`是复算，不是新性能测量、外部基准复现或独立盲测。

## 核验当前交付

```powershell
python -B -X utf8 docs/materials_20260911_revision/qa.py --materials deliverables/submission-materials-20260911-revised
python -B -X utf8 -m unittest discover -s docs/materials_20260911_revision -p test_revision.py -v
python -B -X utf8 -m unittest discover -s docs/materials_20260911 -p test_materials.py -v
```

本轮23项新增工具测试和18项原工具测试均通过；不并入正文引用的392项工程测试，
也不增加任何评测样本数。本轮没有重跑完整运行测试或重新测时延，
而是严格核对既有运行证据与当前执行源码一致。

严格核验拒绝输出缺失、正文删除、错误Word交叉引用、不可见SDK风险、小字表格、
源码或工具漂移、不支持的验收声明、身份元数据、交付PDF或ZIP。
最终核验不使用`--draft`。Office打开时产生的`~$`临时文件不属于交付，
不能删除用户正在使用的锁文件以强行获得整工作区扫描通过。

## 两次生成与实际渲染

没有修改正文、框图或排版程序时，可用已归档实测页码表，在新目录生成：

```powershell
python -B -X utf8 docs/materials_20260911_revision/generate.py --output-dir artifacts/runtime/materials-revision-new --word-layout artifacts/verification/materials-20260911-revised/word_layout.json
```

修改内容或排版后，先省略`--word-layout`生成初稿，再按以下步骤完成两次渲染：

1. 生成初稿到不存在的新目录。所有输出先做结构和内容核验。
2. 用`render.ps1`只读渲染Word与PPT，输出必须在私有`~/TiaobeiLab/`且目录不存在。
3. 用`qa.py`读取实际渲染，得到`word_layout.json`、联系表和机器检查报告。
4. 用新页码表第二次生成到另一个新目录，再渲染、严格核验目录页码与实际分页。
5. 逐页查看PPT与Word联系表，放大检查密集表格和框图，再归档机器与代理视觉记录。

以下以第一次生成的`artifacts/runtime/materials-revision-new`为例：

```powershell
$lab = Join-Path $env:USERPROFILE 'TiaobeiLab'
powershell -NoProfile -ExecutionPolicy Bypass -File docs/materials_20260911_revision/render.ps1 -Source artifacts/runtime/materials-revision-new/OS_Agent_技术方案_评分重点详述版_20260911.docx -Output "$lab/revision-word-new" -Kind word
powershell -NoProfile -ExecutionPolicy Bypass -File docs/materials_20260911_revision/render.ps1 -Source artifacts/runtime/materials-revision-new/OS_Agent_项目报告_20页精简版_20260911.pptx -Output "$lab/revision-ppt-new" -Kind ppt
python -B -X utf8 docs/materials_20260911_revision/qa.py --materials artifacts/runtime/materials-revision-new --word-render "$lab/revision-word-new/document.pdf" --ppt-render "$lab/revision-ppt-new" --output "$lab/revision-qa-new"
```

渲染脚本拒绝操作已经打开的同一源文件，只关闭自身打开的文档，不关闭用户的其他窗口。
`render_manifest.json`绑定Office原始摘要及每份渲染输出；不能拿另一版PDF或PNG代替当前版。
本版最终两份Office均重新渲染。若以后复用PPT图像，须提供`--ppt-render-source`，
核验器逐个比较全部未压缩Office成员，不能只比页数、正文或截图。

## 归档与边界

正式机器记录、实测页码与代理视觉记录位于：
`artifacts/verification/materials-20260911-revised/`。
私有PDF、PNG、联系表不进入交付目录或Git。交付目录内只提供一个Word、
一个PPTX和说明/证据清单，不制作PDF、赛事ZIP或上传。

`visual_render_verified=false`保留生成时语义，不回填覆盖原始清单；
后续渲染和代理检查另立记录。`human_visual_review_recorded=false`不改为true，
负责人仍需审阅。SDK、当前V11、真实Agent/Judge和授权案例均不因材料完成而通过，
`competition_ready=false`继续保留。
