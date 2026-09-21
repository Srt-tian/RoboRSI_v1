<div align="center">

# RoboRSI v1

**用执行证据改进下一轮规划，让粗轨迹成为连贯的机器人操作。**

Plan → Execute → Evaluate → Refine · Offline RSI workbench

[四层架构](#系统架构) · [RSI 闭环](#rsi-跨轮闭环) · [快速开始](#快速开始) · [近期研究](docs/RESEARCH_2026_09.md) · [实验结果](#已记录的实验结果) · [文档导航](docs/README.md)

</div>

RoboRSI 是以“规划—执行—评估—修订”为主线的 Piper 操作研究框架。**本轮**由 GPT 粗规划、确定性轨迹编译和 200 Hz 控制完成操作；**跨轮**由 RSI 层汇集证据、诊断问题、审核修订，再将适用经验用于下一轮规划。

**当前实现：固定计划执行 + 离线 RSI 工具链 + 人工审核。** v0.2 新增自动指标整理、候选重编译比较、1× / 2× 时间配置搜索、按范围选择经验和本机 Web 工作台。规划仍通过交互式 GPT 会话完成；已记录的最终实验中，小 VLM 关闭，执行期间没有新的视觉模型调用。

## 系统架构

![RoboRSI 四层架构：RSI 跨轮改进、任务规划、轨迹编译、执行与反馈](docs/figures/architecture.svg)

[查看架构详解](docs/ARCHITECTURE.md) · [可编辑 draw.io](docs/figures/architecture.drawio) · [PNG](docs/figures/architecture.png)

| 层次 | 负责什么 | 跨层产物 | 当前实现 |
| --- | --- | --- | --- |
| **L1 · RSI 跨轮改进** | 证据分型、候选验证、修订审核、经验选择 | 有指纹、适用范围和验证结果的记录 | `roborsi-rsi` 离线工具 + 人工审核 |
| **L2 · 任务规划** | 选用经验，确定物体顺序、姿态、粗关节关键点 | 审核后的粗计划 JSON | 交互式 GPT + IK 工具 |
| **L3 · 轨迹编译** | 插值、重定时、动态/几何检查、夹爪事件 | 固定 200 Hz 目标流 JSON | 确定性编译代码 |
| **L4 · 执行与反馈** | 下发目标、读反馈、保护保持、保存证据 | 命令、实测状态、执行结果 | 控制适配与本机 Web |

经验向下进入规划，执行证据向上返回 RSI。**RSI 决定下一轮改什么；执行层决定本轮何时发命令与停止。**

**任务层视觉开环，设备层关节反馈与软件保护持续工作。** GPT 不逐点生成 200 Hz 命令；执行保护不会自动调用 GPT 修改剩余轨迹；程序完成不等于物体已经入筐。

## RSI 跨轮闭环

![RSI：实验证据、诊断、候选修订、人工审核、经验与下一轮验证](docs/figures/rsi_cycle.svg)

RSI 的输入是本轮证据，输出是**经过审核、带适用条件的下一轮修订**。工具自动区分故障观测与原因假设，对候选重新编译，并按 robot / setup / task 精确选取已审核的经验。规划者结合新场景使用这些记录。

离线验证分别报告数值约束与几何检查；没有 URDF 就标记几何未检查，程序完成也不会自动变成任务成功。当前的自动搜索仅比较已有时间配置，生成式抓取修订和自主真机迭代仍待实现。

| 已记录实例 | 改进过程 |
| --- | --- |
| 前轮 | 青椒空夹，夹爪检查失败，停止并保留证据 |
| 修订 | 调整抓取深度与方向，审核后用于新计划 |
| 后轮 | 三物体入筐，结果图像与现场确认一致 |

该例展示可追溯的跨轮改进。深度与方向同时改变，不能据此证明某一个改动的独立收益；单次成功也不是长期成功率。

[RSI 命令与接口](docs/RSI.md) · [近期论文与研究路线](docs/RESEARCH_2026_09.md) · [真实修订案例](experiments/2026-09-17/rsi_review.md) · [可编辑闭环图](docs/figures/rsi_cycle.drawio)

## 一轮任务怎么走

审核粗计划 → 离线编译 → 执行前检查 → 连续下发与监督 → 实测保持 → 保存反馈 → 独立确认任务结果。

默认流程止于离线编译或 dry 检查。硬件执行必须显式开启；正常结束和保护停止都会进入保持流程，保护停止不会自动续跑。详见[执行流程与分支说明](docs/EXECUTION_FLOW.md)。

<details>
<summary>展开查看完整执行流程图</summary>

![执行流程：离线与真机分支、执行前检查、连续监督、停止保持及结果确认](docs/figures/execution_flow.svg)

[可编辑 draw.io](docs/figures/execution_flow.drawio) · [PNG](docs/figures/execution_flow.png)

</details>

## 快速开始

Python 3.10+，依赖 NumPy、SciPy 和 PyYAML。默认流程不需要机器人、相机或模型服务；以下命令在仓库根目录执行。

```bash
git clone https://github.com/Srt-tian/RoboRSI_v1.git
cd RoboRSI_v1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

**1. 编译已记录的粗计划，不连接机器人。**

```bash
roborsi-compile examples/three_objects.json \
  --speed 2 --tcp-floor 0 --output runs/three_objects.stream.json
```

生成 **17,046 个目标**，计划时长 **85.23 s**。输出路径必须不存在，以免覆盖计划。示例绑定历史场景，始终不可直接发到真机；未提供 `--urdf` 时，输出的 `geometry_verified` 为 `false`。这里的 `--tcp-floor 0` 是历史复算参数，不能直接套用到新的装配环境。

**2. 在本机查看实测反馈。**

```bash
roborsi-report experiments/2026-09-17/servo20_three_deep.jsonl.feedback.jsonl \
  --output runs/viewer
python -m http.server 8786 --bind 127.0.0.1 --directory runs/viewer
```

打开 **http://127.0.0.1:8786/**，可播放、单步和拖动时间轴，查看跟踪误差、TCP、夹爪开度及队列状态。这里播放的是约 **50 Hz 实测反馈**，不是 200 Hz 计划点。结果照片及任务成败保存在实验记录中，不由查看器自动判断。

**3. 一次生成离线 RSI 工作台。**

```bash
roborsi-rsi workbench \
  --metrics experiments/2026-09-17/metrics.json \
  --program examples/three_objects.json \
  --tcp-floor 0 --output runs/rsi_demo
python -m http.server 8787 --bind 127.0.0.1 --directory runs/rsi_demo
```

打开 **http://127.0.0.1:8787/**，查看历史失败、诊断假设、候选预计耗时与证据指纹；也可直接打开生成的 `index.html`。所有计算都在本机离线完成。该示例复算历史配置，未提供 URDF，不验证新场景的几何或抓取结果。

**4. 验证代码与实验归档。**

```bash
python -m unittest discover -s tests -v
python scripts/verify_evidence.py
```

使用已有环境时，也可通过 `PYTHONPATH=src python -m roborsi.compiler ...` 和 `PYTHONPATH=src python -m roborsi.reporting ...` 运行。硬件接口另见[硬件接入指南](docs/HARDWARE.md)。

## 已记录的实验结果

2026-09-17，物理左臂依次将 **青椒 → 胡萝卜 → 茄子** 放入篮筐并回位。该轮没有中途重新规划或保护暂停。

| 指标 | 记录值 |
| --- | ---: |
| 任务结果 | **3 / 3 入筐**，结束图像与现场确认一致 |
| 实际执行耗时 | **85.42 s** |
| 主机目标发送频率 | **200.000 Hz** |
| 指令间隔 P99 | **5.116 ms** |
| 指令 / 实测反馈记录 | **17,046 / 4,228** 条 |
| 执行中视觉 / 小 VLM 调用 | **0 / 0** |

| 执行前 | 执行后 |
| :---: | :---: |
| ![三个物体与篮筐](experiments/2026-09-17/before.jpg) | ![三个物体已入筐](experiments/2026-09-17/after.jpg) |

这是已记录的单轮结果，**不是长期成功率或严格对照实验**。200 Hz 指主机发送频率，不代表电机内部控制环频率。真机数据来自实验版本；当前仓库代码完成离线回归，尚未以整理后的版本重新完成真机验收。

[成功与失败记录](docs/EXPERIMENTS.md) · [指标数据](experiments/2026-09-17/metrics.json) · [归档校验清单](experiments/2026-09-17/manifest.json)

## 实现与扩展入口

```text
src/roborsi/
├── rsi/            # L1：证据、候选验证、审核经验、范围选择与本机 Web
├── ik.py           # FK / Jacobian / 有界 IK，供规划阶段使用
├── geometry.py     # 当前装配的几何检查
├── smoothing.py    # C1 插值与速度、加速度受限重定时
├── compiler.py     # 粗关节计划 → 目标流与夹爪事件
├── validation.py   # 目标流结构与数值检查
├── runtime.py      # 队列补充、控制后端适配、反馈监督
├── hold.py         # 停止、清队列与新鲜实测保持
└── reporting.py    # 执行后本机反馈查看器
examples/           # 不可直接真机重放的历史计划
experiments/        # 命令、反馈、图片、指标与原始归档
docs/               # 架构、流程、接入与实验说明
scripts/            # 三张图的生成器、实验归档校验
tests/              # 离线测试
```

编译器接收已审核的 **Nx6 左臂关节路径**，不会自动把图像转换为抓取轨迹。右臂在本版本保持，几何检查依赖当前双臂装配，并非通用碰撞规划器。机械臂适配、数据字段与源码映射见[架构详解](docs/ARCHITECTURE.md)。

近期 Zetta、CHIME、RSIAgent 等工作与跨轮改进有明显交集；本仓库的研究方向及尚待验证的差异见[2026-09 论文对照](docs/RESEARCH_2026_09.md)。

[开发与文档维护](CONTRIBUTING.md) · [完整文档导航](docs/README.md) · [依赖与证据边界](docs/PROVENANCE.md)
