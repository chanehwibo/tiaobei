# 真实 SDK 接入与证据边界

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

向量数据库的公开示例依赖 gRPC、Protobuf、KylinAiProto、SQLiteCpp、SQLCipher 及实际服务。目前保留本项目 SQLite 后端，真实向量数据库桥接和服务连通测试仍未完成。不要把客户端源码下载、头文件发现或 Embedding 成功算作向量数据库已接入。

原生库、模型及服务只在专用客户机内安装，不安装到 Windows。公开库有各自许可，本仓库不捆绑这些二进制或第三方源码。
