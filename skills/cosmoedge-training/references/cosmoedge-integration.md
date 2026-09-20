# 按交付范围接入 CosmoEdge

只有任务包含 CosmoEdge 接入或端到端验证时读取本页。训练与导出任务不要求提前部署 CosmoEdge。本文按 2026-09-20 核对的仓库内容整理，执行时读取用户所用版本的文档和代码；链接指向官方仓库，分支更新后能力可能变化。

## 先确定目标环境

检查实际实例是否可达、可登录、允许何种操作，以及版本、运行后端、模型管理能力、可用存储和测试数据。已有实例能满足要求时直接利用。缺少实例应提出具体准备方案；继续不依赖它的数据或训练工作，并明确端到端验证正在等待什么。

Mac 上的 Docker 预览是可选开发环境。其可用性、镜像架构、资源和端口要实际检查；Mac/x86 的结果只覆盖该环境。选定设备芯片后，应在相应设备上验证，不能沿用另一后端的运行结论。

可查询官方 [Mac 预览脚本](https://github.com/cosmo-wander-ai/cosmo-edge/blob/main/scripts/macos-docker-preview.sh) 与[模型接入教程](https://github.com/cosmo-wander-ai/cosmo-edge/blob/main/docs/tutorials/05-model-porting/model-porting.md)。先读帮助和版本内容，再选择命令；已有服务不要为套用示例而重建。

## 区分训练导出与产品模型转换

当前 CosmoEdge 正式模型转换执行器从 ONNX 开始；`.pt`、`.pth` 可以作为待评估材料，训练框架导出需要独立检查工程、官方办法和实际输出。一次临时导出成功，不代表 CosmoEdge 已提供通用训练导出服务。

模型格式与目标构建相配：x86 ONNX Runtime 使用 `.onnx`，模型包主文件为 `model.onnx`；Sophon 使用与实际芯片匹配的 `.bmodel`，完整包中的 `model.nn` 还有封装要求，不能通过改扩展名得到。其他后端以当前目标版本的实现为准。

文件格式之外，还要核对输入形状和类型、颜色与归一化、输出布局、类别顺序、是否包含去重处理（NMS）、运行资源和解析器。需要新解析器或代码变更时，评估代价并按主项目贡献流程处理，不能假定任意 ONNX 都能直接运行。

## 使用主项目已有检查入口

读取目标版本的 [AGENTS.md](https://github.com/cosmo-wander-ai/cosmo-edge/blob/main/AGENTS.md) 和[智能体辅助开发说明](https://github.com/cosmo-wander-ai/cosmo-edge/blob/main/docs/development/agent-assisted-development.md)。涉及其任务模型、远程执行、模型传输、转换或测试设备操作时，按适用要求建立私有任务记录并调用主项目工具；本 Skill 不复制另一套互相矛盾的准入规则。

已明确的操作授权可以直接记录，缺少会影响下一步的授权才询问。密码和 Token 只经受支持的安全输入传递，不进入命令参数、任务文件、日志或发布材料。

常用入口是 `scripts/agent/start.sh`、`connect.sh`、`assess.sh`、`doctor.sh`、`convert_model.sh`、`verify.sh`。按所选路线和当前帮助使用；普通 x86 加载不必套用 Sophon 编译步骤。Sophon 路线需要有效的任务评估、执行环境检查和转换验证，其产物与具体目标芯片绑定。

## 按真实用途验证

1. 确认实际添加或导入的是当前候选，配置与输入输出一致；单文件添加与完整模型包导入使用不同入口。
2. 先用固定的正、负、困难图片对照离线结果。存在差异时定位预处理、输出解析或模型问题，保留对照材料。
3. 需要视频应用时，按业务配置检测、区域或时间条件及事件输出；使用[编排教程](https://github.com/cosmo-wander-ai/cosmo-edge/blob/main/docs/tutorials/04-pipeline-orchestration/pipeline-orchestration.md)理解节点用途，实际参数依据当前任务。
4. 检查视频识别、误触发与漏触发，以及任务要求的事件、截图、录像和回放。性能或持续运行要求应在指定负载与时长下测量。

记录模型、应用版本、编排配置、测试材料和实际结果。转换通过只覆盖转换；上传成功只覆盖接收；有画面和事件也不自动表示漏检误报满足要求。报告用普通语言说明各项结果，提供可查看的证据。
