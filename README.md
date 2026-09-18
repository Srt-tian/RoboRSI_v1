<div align="center">

# RoboRSI v1

**大模型规划粗轨迹，确定性模块生成细动作，200 Hz 控制连续执行。**

Scene-grounded planning · Continuous manipulation · Supervised cross-trial refinement

[系统架构](#系统架构) · [快速开始](#快速开始) · [执行流程](docs/EXECUTION_FLOW.md) · [实验结果](#已记录的实验结果) · [文档导航](docs/README.md)

</div>

RoboRSI 是面向 Piper 操作任务的研究原型。规划者结合场景、任务和历史经验，确定物体顺序、抓取姿态及粗关节路径；轨迹编译器完成插值、时间缩放和检查；控制线程连续下发目标，并通过实测反馈监督执行。

**当前实现：固定计划执行 + 人工监督的跨轮 RSI 修订。** 规划通过交互式 GPT 会话完成，仓库不包含独立的 GPT API 服务。已记录的最终实验中，小 VLM 关闭，执行期间没有新的视觉模型调用。

## 系统架构

![RoboRSI 架构：场景、粗规划、确定性编译、连续执行，以及人工监督的跨轮反馈](docs/figures/architecture.svg)

[查看架构详解](docs/ARCHITECTURE.md) · [可编辑 draw.io](docs/figures/architecture.drawio) · [PNG](docs/figures/architecture.png)

| 层次 | 决定什么 | 实际产物 |
| --- | --- | --- |
| 粗规划 | 先抓哪个、以什么姿态抓、经过哪些关键点 | 已审核的关节路径与夹爪事件 |
| 轨迹编译 | 关键点之间如何连续运动、需要多长时间 | 带检查信息的固定 200 Hz 目标流 |
| 连续执行 | 每个周期下发什么、何时触发保护 | 命令记录、实测反馈、完成或异常状态 |
| 跨轮 RSI | 哪类错误需要修订、下一轮修改什么 | 人工审核的经验与计划修订 |

**任务层视觉开环，设备层关节反馈与软件保护持续工作。** GPT 不逐点生成 200 Hz 命令；执行保护不会自动调用 GPT 修改剩余轨迹；程序完成不等于物体已经入筐。

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

**3. 验证代码与实验归档。**

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

## RSI 在哪里

RSI 体现在**跨轮**的“失败 / 偏差 → 诊断 → 人工审核修订 → 下一轮验证”。已有修订涉及定位偏差、抓取深度、夹爪方向及硬件映射。

当前没有在线自动学习、自动更新的经验库或经验证的小 VLM 残差修正器。下一步是固定复位协议下的重复试验、误差归因，以及冻结计划与经验修订的对照，详见[架构中的 RSI 边界](docs/ARCHITECTURE.md#跨轮-rsi)。

## 实现与扩展入口

```text
src/roborsi/
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
scripts/            # 两张图的生成器、实验归档校验
tests/              # 离线测试
```

编译器接收已审核的 **Nx6 左臂关节路径**，不会自动把图像转换为抓取轨迹。右臂在本版本保持，几何检查依赖当前双臂装配，并非通用碰撞规划器。机械臂适配、数据字段与源码映射见[架构详解](docs/ARCHITECTURE.md)。

[开发与文档维护](CONTRIBUTING.md) · [完整文档导航](docs/README.md) · [依赖与证据边界](docs/PROVENANCE.md)
