# Jev、开放判断模型与机器人修订 · 2026-09-22

这是一份面向 RoboRSI 的定向调研：覆盖官方 Jev、独立开放实现、机器人应用和直接相关论文，不声称穷尽所有项目。证据来自官方文档、作者论文、仓库与模型卡；没有下载权重、调用商业 API 或复现外部基准。可变仓库页面的阅读截止日为 **2026-09-22**，实际部署应另行固定 commit、模型版本和许可证。

## 先明确 Jev 指什么

这里的 Jev 是 TypeSafe 于 **2026-09-15** 发布的 System One 判断模型。应用提交状态与带类型的问题，模型返回选项分布或数值判断，代码负责组合结果。它适合候选选择、路由与证据充分性判断；并不是能从相机图像直接输出关节轨迹的机器人策略。[官方发布](https://typesafe.ai/blog/introducing-system-one-models-and-jev) / [接口定义](https://docs.typesafe.ai/introduction)

**开放 SDK 不等于开放模型。** 本次核验到官方 HTTP 服务与 Python SDK，未核验到 TypeSafe 官方开放的 Jev 权重或完整架构、训练论文。独立项目采用的网络不能反推为官方 Jev 架构。官方 `confidence` 与选项概率也不是同一个量，更不是在 Piper 上校准过的任务成功率。[API](https://docs.typesafe.ai/api) / [confidence 定义](https://docs.typesafe.ai/confidence) / [官方 SDK](https://github.com/typesafe-ai/typesafe-sdk-python)

## 开源生态：按可以复用的能力分组

下表的“可用”指作者公开了相应材料，不表示本仓库已运行验证。机器人 demo 与严格对照实验单独看待。

| 类别 / 项目 | 机制与开放材料 | 对 RoboRSI 的价值与边界 |
| --- | --- | --- |
| 官方接口 · [typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python) | 官方 SDK 对接托管模型；Choice / Score / Noul 等类型 | 用作可替换 provider；不把外网时延放进 200 Hz 控制线程。SDK 开源不代表权重开源。 |
| 可训练原型 · [NanoJev](https://github.com/TianyuCodings/NanoJev) | 独立的动态候选判断与训练管线，游戏环境示例 | 可研究如何训练小型候选选择器；环境状态、候选菜单与奖励设计决定问题难度，不能视为官方等价复现。 |
| 可训练原型 · [jevlike](https://github.com/vinnylarouge/jevlike) | 候选 query 读取状态表示，共享评分器对动态菜单归一化；支持 byte / 冻结编码器 | 适合把“候选数量变化”作为接口基础。已查看 [model.py](https://github.com/vinnylarouge/jevlike/blob/main/jevlike/model.py)；未验证机器人迁移效果。 |
| 领域小模型 · [CUA-S1](https://github.com/trycua/cua/tree/main/libs/cua-s1) | 表单领域的 byte 编码与选项注意力；[模型卡](https://huggingface.co/cua-ai/cua-s1-forms)列出 706,048 个可训练参数 | 证明很小的领域判断器也是合理研究对象；表单专用训练和上下文截断不能直接套用机器人状态。代码/权重许可分别核验。 |
| 本地判断模型 · [Laya](https://github.com/NandhaKishorM/laya) | 编码器式模型，提供 typed decisions 与训练/部署路径 | 可作为本地 provider 候选。README 明示未覆盖语言中的自信错误，说明高概率阈值不能代替域外评测。 |
| 开放权重 · [this-that-model](https://github.com/FLock-io/this-that-model) | 指定隐藏状态位置读取标签，一次前向完成多问题；[1.0 模型卡](https://huggingface.co/flock-io/this-that-model-1.0)公开约 2B 模型 | 比直接让 VLM 连续生成动作更适合受约束判断；作者报告的任务族/措辞泛化不等于新的机器人任务零样本泛化。 |
| 机械臂应用 · [RoboJEV](https://github.com/lykycy123/RoboJEV) | MuJoCo 特权状态 → 意图 → 轴向动作 → DLS IK；已查看 [policy.py](https://github.com/lykycy123/RoboJEV/blob/main/src/jev_vla_sim/policy.py) | 直接相关，但等待 API 时仿真暂停。作者的配对实验中 stack 为 8/10 对规则 10/10，gate 为 5/10 对 8/10；不是小模型必然优于规则的证据。 |
| 飞行应用 · [jev-drone](https://github.com/RomanSlack/jev-drone) | 低频战术判断与高频控制分离；代码处理视觉状态、许可动作和约束，已查看 [tactics.py](https://github.com/RomanSlack/jev-drone/blob/main/tactics.py) | 借鉴多速率职责与缓存；仓库自己披露早期匹配种子测试没有证明净收益，不把演示飞行当成消融结论。 |
| 仿真机器人 · [jevduck](https://github.com/amazedsaint/jevduck) | 有界候选、状态复查、动作 receipt 与 outcome 分离 | 借鉴“建议返回后重新检查上下文”；属于仿真展示，未核验真机或胜过规则的受控证据。 |
| 本地机器人研究 · [STEERIX robo-jev](https://github.com/STEERIX-home/robo-jev) | 独立 System One 机器人判断研究，强调状态/指令打乱和延迟对照 | README 包含目标利用不足等负结果，支持将 label shortcut、候选覆盖率和规则基线纳入实验。不是官方 Jev 权重。 |
| 记忆路由 · [Jev-Mem](https://github.com/libingzheren/Jev-Mem) | System One 控制记忆构建、检索预算与停止，System Two 负责推理 | 可启发 RSI 的经验选择与观测预算，但其 LoCoMo 结果不能证明机器人恢复能力；本版未实现其图记忆。 |

**选型建议是我们的判断：**先保持 provider 接口与数据格式稳定，收集有标注的机器人决策样本，再以规则、官方 Jev 和本地开放模型做同输入比较。此时直接选参数量最大的模型、或训练新的 VLM，都缺少依据。仓库当前只实现可选官方 HTTP 适配器；上表其他项目尚未集成。

## 直接相关论文

日期为 arXiv 首次提交日期，以下按预印本介绍，不推断录用状态。性能数字属于作者实验，硬件、任务与延迟口径不能跨论文直接排名。

| 首次提交 / 论文 | 可借鉴的方法 | 必须保留的证据边界 |
| --- | --- | --- |
| **09-19** · Delong Li 等，[*Replacing Large Language Models with Jev Decision Models for Low-Latency Edge Service Orchestration*](https://arxiv.org/abs/2609.22753) | 在相同 validator / scheduler 下替换判断模型，统计整个请求链路的等待 | 两节点 OCR 服务；缓存会明显缩小差异。启发我们同时报告模型、验证、等待和任务总耗时。 |
| **09-20** · Zehua Cheng、Wei Dai、Jiahao Sun，[*this-that-model-1.0: A typed decision model that decides in 30 ms, for a millionth of a cent*](https://arxiv.org/abs/2609.23886) | 非生成式选项读取，多问题一次前向；公开权重与失败案例 | 30.9 ms 是作者特定设备测试，不是本机保证；多步算术与跨任务训练迁移仍存在弱点。 |
| **09-21** · Dongming Jiang、Yi Li、Bingzhe Li，[*Jev-Mem: System-One-Controlled Agentic Memory for Efficient AI Agents*](https://arxiv.org/abs/2609.23986) | 用快判断器决定如何组织、检索和停止访问记忆 | 评测是对话记忆；不能把记忆 benchmark 的收益写成 RSI 真机收益。 |
| **09-21** · Amir Rafe、Subasish Das，[*Calibrated Decisions at Scale: Converting Police Crash Narratives into Probabilistic Crash Variables with a System One Model (Jev)*](https://arxiv.org/abs/2609.24052) | 显式标签、概率质量与校准分析 | 交通事故叙述领域；校准依赖标签与分布，不能沿用阈值。RoboRSI 单独划分 validation / test。 |

## 更大的交集：不把已有组合包装为全新概念

- [**ROBUST TAMP / Plan Along the Way**](https://arxiv.org/abs/2608.28075)，2026-08-28，Puru Ojha 等：已有严格执行接口、可见关系状态及发现/失败触发重规划。因而“事件触发 + 大模型重规划”本身不是我们的差异。
- [**Legato**](https://arxiv.org/abs/2602.12978)，2026-02-13，Yufeng Liu 等：训练期学习 action chunk 的延续，减少模式切换与停顿。它改变 flow policy；本仓库当前的确定性插值和重定时没有训练这种策略，也不能称为 Legato。
- [**FutureRTC**](https://arxiv.org/abs/2607.24008)，2026-07-27，Hai Jiang 等：面向预测时刻与执行时刻的状态错位。它启发我们重视时效，但 RoboRSI 本版只做版本与时限拒绝，没有未来观测预测器。
- **Zetta、CHIME、Show-Harness、RSIAgent** 的主要重叠已见[前一份核验记录](RESEARCH_2026_09.md)。尤其 Zetta 的 critic / 恢复技能演化与我们紧邻，必须用修订对象、数据预算和实验协议建立区别。

## 对本轮方案的结论

Jev 提供的是一种判断接口范式。更值得研究的对象是：**在完整粗计划仍然大部分有效时，能否用少量证据识别“继续、补观测、局部改动、重规划”的边界，并让这个边界通过跨轮数据改善？**

这需要受约束候选、状态时效、拒判、独立结果标签与冻结评测共同成立。它是研究假设，尚无本仓库性能结论。具体原创方案、实现边界和消融设计见 [RESEARCH_PROPOSAL.md](RESEARCH_PROPOSAL.md)，可运行接口见 [TYPED_JUDGMENT.md](TYPED_JUDGMENT.md)。
