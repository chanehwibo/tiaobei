# 真实 SDK 接入与证据边界

状态：**已完成初版，待赛事验收**。真实SDK时延为**待复测风险项**，
不是“达标但缺图”。现有证据不支持原生检索P95<=500ms。

## 当前风险结论

| 测量对象 | 实际数据 | 能说明什么 | 风险状态 |
| --- | --- | --- | --- |
| 旧ABI真实调用 | 1次，768维，13,390.615ms | 进程、会话、模型初始化及向量调用合计；未拆分各项 | **待复测风险项**，单次也高于500ms |
| 原生完整服务检索 | 没有至少50个不同请求的P95 | 无法评定原生端到端时延 | **待复测风险项** |
| 新ABI及实际模型 | 缺符号；实际模型身份/版本未核验 | 已安装模型文件不等于该调用使用该模型 | **待复测风险项** |
| 向量数据库往返 | 服务存在但未验证建库/写/查/删 | 服务active不等于业务链路接通 | **待复测风险项** |
| HashEmbedding回归 | 单独的五项和复杂干扰报告 | 仅证明该轻量provider的公开合成结果 | 不计为原生SDK成绩 |

机器可读风险摘要由 `scripts/summarize_sdk_risk.py` 从原始探针读取，
固定保留`native_p95_ms=null`、`native_latency_passed=false`及原始文件SHA256。
它只生成风险披露，不执行SDK，也不能被当作新一轮测试通过。

## 解除风险标记的条件

1. 固定并记录V11、CPU/内存、SDK/runtime/模型版本、二进制及配置摘要，
   实际核验模型身份、维度，不允许失败后静默退回HashEmbedding。
2. 先冻结至少50个不同请求、文档集、干扰分布、top_k、阈值与计时方案。
   原有80条查询可作为固定回归，新复杂集另外报告，不能复制查询凑独立样本。
3. 分别记录运行时启动、模型初始化、首次查询和完整`MemoryService.search`时延。
   当前每次调用新建子进程和会话，不能把13.39秒假定为以后只付一次的冷启动成本；
   若改为持久worker，需先验证超时隔离、重启恢复和资源释放，再重新测量。
4. 至少重复3轮，保留每个请求的结果、错误/超时、延迟及每轮P50/P95/P99。
   使用nearest-rank，不剔除慢请求；超时/异常计失败，报告其耗时下界，
   存在丢失请求时不判定通过。预热数量和是否计入必须预先写明。
5. 在声明的资源配置下原生服务检索P95<=500ms，同时质量、无答案、跨域、
   冲突与敏感泄漏门槛通过，方可为该配置解除时延风险。HTTP/Agent端到端另报。
6. 声称向量数据库集成时，另提供建库、写入、检索、删除后的真实往返结果，
   不用Embedding连通替代。正式评分仍需出题方验收。

主办方对虚拟机部署、运行资源及评分口径的认可已按参赛者确认处理，
原始凭证待归档；认可不等于真实SDK性能通过。以下保留历史诊断的准确范围。

## 接口来源

本轮核对的公开源码仅保存在隔离实验目录，没有把第三方实现或官方原始资料加入本仓库。

| 接口 | 核对的来源 | 版本及接入方式 |
| --- | --- | --- |
| Embedding | [公开头文件](https://gitee.com/openkylin/kylin-coreai-embedding/blob/openkylin/nile-sp2/include/kylin-ai/coreai/embedding/embedding.h) | 本地检出 63aed6f3e947926f5def476997ee1baa6735dd8f；C ABI，库名 kysdk-coreai-embedding |
| 向量数据库 | [官方示例目录](https://gitee.com/openkylin/libkysdk-vector-engine-client/tree/openkylin/nile-sp2/demo/client) | 本地检出 bed675f418d32c052a6ab4c5c49bae148d90f678；C++17 客户端，库名 kysdk-vector-engine-client |

原有 `provider=kylin` 是可配置 Python 模块的通用适配支架，不能据此推断官方提供同名 Python 包。新增 `provider=kylin-native` 依据公开 C ABI 创建会话、初始化指定模型、同步取向量、校验错误码和维度，再释放结果及会话。它不会回退为 HashEmbedding。

每次向量调用放入独立子进程，超时终止并等待回收，避免原生库崩溃或阻塞拖住主服务。输入仅走标准输入；原生库日志丢弃，错误报告不回显用户正文。代价是每次重新初始化会话和模型，因此这是优先验证接口的实现，实际延迟必须另测，不能沿用 HashEmbedding 的成绩。

## 客户机内验证

先运行 `python3 -S scripts/check_kylin_native.py --output /home/tiaobei/native-sdk.json`。没有执行向量调用时返回 2，库文件存在也不会标成连接成功。

将 `config/embedding.kylin-native.example.json` 复制到客户机私有运行目录，按实际安装内容填写库的绝对路径、模型名、模型版本和维度。示例路径和768维均需核对，不承诺公开镜像自带该版本。然后执行：

```bash
python3 -S scripts/check_kylin_native.py --embedding-config /home/tiaobei/native-config.json --output /home/tiaobei/native-sdk.json
```

只有真实库返回合规向量才报告 `real_embedding_executed=true`。单次自检也不等于官方性能验收、模型质量达标或向量数据库连接成功。服务部署继续通过统一 `create_provider` 配置入口注入。

### R06：V11 2603 实际调用

2026-09-07，在 R05 的离线、磁盘安装客户机内核查。原始公开诊断位于 `artifacts/verification/round5/native/`，包括失败记录，不覆盖此前的 `not_connected`。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Embedding 库 | 1.2.0.0-0k0.3；缺少 `text_embedding_init_model` 和新模型列表 ABI | `packages.log`、`symbols.log` |
| 新 ABI 枚举 | 失败，`library_symbols`；未枚举模型、未调用向量 | `models_recheck.json` |
| Runtime 未启动时的旧 ABI 调用 | 会话初始化失败，错误码 3；公开头文件定义为连接错误 | `legacy_probe.json` |
| Runtime 启动后的旧 ABI 调用 | 真实返回 768 维有限非零向量，单次 13390.615ms | `legacy_runtime_started.json` |
| 模型文件 | `kylin-gte-base-model` 已安装；ONNX 普通文件 339629744 字节 | `model_package_files.log`、`model_file.log` |
| 向量服务 | 用户服务 active/running，客户端 1.2.0.0-0k0.7 | `vector_service.log`、`packages.log` |
| 向量开发环境 | 查询的客户端/gRPC/Protobuf/SQLiteCpp/SQLCipher 开发包未安装，pkg-config 无客户端条目 | `vector_development_recheck.log`、`vector_pkgconfig.log` |
| Agent、容器、Judge | 未发现 Docker、Podman、KylinBot 命令；未执行真实行动评分 | `legacy_runtime_started.json` |

模型的实际路径为 `/usr/share/kylin-ai/model-repository/embd_gte-base_uint8-text/1/gte-base-multilingual-model_QUInt8.onnx`。另一个名字相近的模型包未安装，不代表该 ONNX 文件不存在。文件存在也不能证明某次调用使用了该模型，故报告保持 `model_identity_verified=false`、`model_version_verified=false`。

镜像通过 `/etc/xdg/autostart/kylin-ai-runtime.desktop` 启动 AI Runtime，不是同名 systemd 用户单元。诊断在专用客户机中按其依赖路径启动，120 秒后自动结束；没有更改宿主配置、联网下载或设置永久自启动：

```bash
timeout -k 5s 120s env LD_LIBRARY_PATH=/usr/lib/kylin-ai/depends QT_QPA_PLATFORM=offscreen /usr/bin/kylin-ai-runtime
```

在同一用户会话的另一终端执行：

```bash
env TMPDIR=/var/tmp python3 -S scripts/check_kylin_native.py \
  --library-path /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 \
  --probe-legacy-default --timeout-seconds 40 --output /home/tiaobei/native-probe.json
```

`--probe-legacy-default` 是显式选择的兼容性诊断，不是业务 provider 的自动降级。旧接口不能明确指定、枚举并核验模型，业务 `kylin-native` 仍要求指定模型的新 ABI；不得把旧接口返回的硬编码模型元数据当作已安装模型列表。

本次单探针含会话、进程和初始化成本，**不是 50 请求 P95，也没有通过 500ms 性能门槛**。现有五项达标结果使用 HashEmbedding，不能沿用为原生模型成绩。

向量数据库的公开示例依赖 gRPC、Protobuf、KylinAiProto、SQLiteCpp、SQLCipher 及实际服务。目前保留本项目 SQLite 后端；缺少匹配的开发依赖，真实向量数据库桥接、建库/写入/检索/删除往返尚未验证。不要把服务 active、客户端源码下载或 Embedding 成功算作向量数据库已接入。正式 Agent/单样本容器/独立 Judge 仍需提供匹配运行资源。

### 证据传输

- 被测代码 TAR SHA256：`3efb41164b8c22a931ffadee35706331efa7887394fbd6cacbb880d4518cce8c`。
- 只读 ISO SHA256：`ebcfcee7ea69107e5e2b405433ad3dc47871920ddf9d0099e6277d36a9113905`。
- 本次串口导出 TAR SHA256：`292a9957d18ab57f1621ea49e5bb8df551491f8b6cef67b951bb420a65a58b43`。
- 仅复制已核查的诊断 JSON、依赖/符号/包状态日志，保持原始字节。包含原生运行时详细输出的日志、客户机访问凭据、私人路径截图仅留在隔离实验目录，不进入公开仓库。

原生库、模型及服务只在专用客户机内安装，不安装到 Windows。公开库有各自许可，本仓库不捆绑这些二进制或第三方源码。
