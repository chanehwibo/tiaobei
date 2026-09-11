# 2026-09-11 材料生成与核验

本目录只生成、核验匿名 Word/PPT，不修改运行算法、评测集或原始测量。
本版交付记录见[第46号文档](../46_项目报告与技术方案交付核验.md)。

## 环境

本次使用 Windows、Python 3.14.3、python-docx 1.2.0、python-pptx 1.0.2、
Pillow 12.2.0；实际渲染使用已安装的 WPS，渲染核验使用 PyMuPDF 1.27.2.3。
生成器需要本机 `C:/Windows/Fonts` 中的微软雅黑、Arial、宋体与 Consolas，
仓库不分发字体或 WPS。页数依赖字体和排版引擎，不承诺不同办公软件逐页完全相同。

在项目根目录、独立虚拟环境中安装可选材料依赖：

```powershell
python -m pip install -e ".[deliverables]"
python -m pip install Pillow
```

只有运行渲染核验时才需要 PyMuPDF；不安装它也能生成文件和执行结构核验：

```powershell
python -m pip install PyMuPDF
```

PyMuPDF 使用 AGPL-3.0 或商业许可，须按安装版本许可使用。它不属于核心运行依赖，
本次不随仓库分发该库、商业字体或 WPS，详见[第三方说明](../../THIRD_PARTY_NOTICES.md)。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `content.py` | 18章67节正文、表格、代码和演讲者备注 |
| `diagrams.py` | 25张框图的节点、连接与边界说明 |
| `evidence.py` | 核对149个运行文件、固定数据和既有原始证据，重新计算比较器 |
| `generate.py` | 生成DOCX、原生可编辑PPTX、证据摘要及内容索引 |
| `qa.py` | 核验内容、匿名信息、摘要、页码、可编辑性及渲染像素 |
| `test_materials.py` | 18项材料工具回归测试 |

## 核验当前交付

```powershell
python -B -X utf8 docs/materials_20260911/qa.py --materials deliverables/submission-materials-20260911
python -B -X utf8 -m unittest discover -s docs/materials_20260911 -p test_materials.py -v
```

严格检查会拒绝：运行源码或冻结数据漂移、证据被改写、输出摘要缺失、工具版本不匹配、
不支持的验收声明、身份信息、外部Office关系，以及交付目录中的PDF/ZIP。
新增18项是材料工具测试，不并入正文引用的392项工程测试或性能样本分母。

## 重新生成

未修改正文、框图和排版程序时，可使用本次实测页码表，输出到不存在的新目录：

```powershell
python -B -X utf8 docs/materials_20260911/generate.py --output-dir artifacts/runtime/materials-review-new --word-layout artifacts/verification/materials-20260911/word_layout.json
```

生成器校验的是LF归一化源码和原始证据摘要，不以当前Git提交号的变化判断算法变化。
Office压缩成员时间等信息可能使重新生成文件的整体摘要不同；新文件仍须重新核验。
不要覆盖已交付文件后继续引用其旧摘要。

修改正文、框图或生成器后，必须先去掉 `--word-layout` 生成初稿，重新取得页码表：

1. 用已安装的办公软件只读打开初稿，不回写源文件；将Word渲染为核验用PDF，
   将PPT渲染为53张1600×900 PNG，全部保存在本机 `~/TiaobeiLab/` 下。
2. 执行下列检查，输出目录必须不存在；工具会产生 `word_layout.json` 和私有联系表。
3. 用新页码表执行第二次生成，再渲染并严格检查最终文件，确认目录页码与实际页码一致。
4. 逐页检查联系表，并放大查看框图、密集表格、命令和参考文献；机器检查不代替视觉检查。

```powershell
$lab = Join-Path $env:USERPROFILE 'TiaobeiLab'
python -B -X utf8 docs/materials_20260911/qa.py --materials artifacts/runtime/materials-review-new --word-render "$lab/materials-word-new/document.pdf" --ppt-render "$lab/materials-ppt-new" --output "$lab/materials-qa-new"
```

如果复用先前的PPT渲染，必须额外提供 `--ppt-render-source` 指向被渲染的PPTX。
核验器要求全部未压缩Office成员集合及字节完全一致，不能只比较页数或可见文字。
最终核验不使用 `--draft`，该选项仅供工具开发期间检查旧初稿，不能放宽正式源绑定。

## 记录与交付边界

生成清单中的 `visual_render_verified=false` 表示“生成时尚未渲染”，不回填覆盖。
后续机器核验记录在 `artifacts/verification/materials-20260911/render_checks.json`，
代理视觉检查另记于同目录的 `visual_review.json`。负责人仍须审阅，两者均不代表赛事验收。
核验用PDF、PNG和联系表只保留在私有实验目录；交付目录仅提供一个Word和一个PPT及说明清单。
本工具不制作赛事压缩包、不上传、不测量新的SDK时延。
