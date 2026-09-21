# 文档导航

| 我想了解 | 阅读入口 |
| --- | --- |
| 项目能做什么、怎样离线运行 | [项目首页](../README.md) |
| 怎样运行离线 RSI、本机工作台与经验选择 | [RSI 命令与接口](RSI.md) |
| 与近期工作的重叠、下一步研究方向 | [2026-09 论文对照](RESEARCH_2026_09.md) |
| 一份真实的修订记录如何写 | [复盘案例](../experiments/2026-09-17/rsi_review.md) / [模板](templates/RSI_REVIEW.md) |
| GPT、IK、平滑和控制分别负责什么 | [系统架构](ARCHITECTURE.md) |
| 一轮任务怎么启动、监督、停止和确认结果 | [执行流程](EXECUTION_FLOW.md) |
| 如何准备新的真机计划与设备配置 | [硬件接入](HARDWARE.md) |
| 真实成功、失败和人工干预的记录 | [实验记录](EXPERIMENTS.md) |
| 数据与软件依赖的来源、哪些结论有证据 | [证据与依赖边界](PROVENANCE.md) |
| 如何维护代码与重画流程图 | [开发指南](../CONTRIBUTING.md) |

三张图分别回答不同问题：

- [系统架构图](figures/architecture.svg)：模块分工、数据方向、跨轮 RSI；[可编辑源文件](figures/architecture.drawio)。
- [RSI 闭环图](figures/rsi_cycle.svg)：证据、诊断、修订、审核与下一轮验证；[可编辑源文件](figures/rsi_cycle.drawio)。
- [执行流程图](figures/execution_flow.svg)：离线/真机分支、检查、监督、保持与结果确认；[可编辑源文件](figures/execution_flow.drawio)。

图由 [scripts/draw_architecture.py](../scripts/draw_architecture.py) 统一生成，关键机制以对应源码为准。图中规划和人工结果确认是交互实验环节，不是编译器自动提供的模型服务。
