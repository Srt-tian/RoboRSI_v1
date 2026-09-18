<div align="center">

# RoboRSI v1

**让大模型给出粗轨迹，让确定性控制把任务连贯地执行完。**

Scene-grounded coarse plans → smooth trajectories → 200 Hz Piper execution

![Status](https://img.shields.io/badge/status-research_prototype-blue)
![Control](https://img.shields.io/badge/control-200_Hz-13a89e)
![Offline](https://img.shields.io/badge/default-offline_replay-6366f1)

[快速开始](#快速开始) · [系统分工](#系统分工) · [真实实验](#真实实验) · [真机接入](docs/HARDWARE.md) · [实验记录](docs/EXPERIMENTS.md)

</div>

RoboRSI 是一个基于双臂 Piper 的机器人操作研究原型：规划者根据启动前的场景与已有经验，确定物体顺序、抓取姿态和少量任务关键点；IK、轨迹平滑和高频控制负责把这些决定转换成可执行动作。

本仓库整理了实际实验中的运动学、平滑、控制适配和记录流程。**当前版本的 RSI 体现为人机监督的跨轮经验修订，尚未实现自动学习的自改进闭环。** 最后几轮关闭了小 VLM，执行期间不再调用视觉模型。

## 一眼看懂

![RoboRSI 系统流程图](docs/figures/architecture.svg)

[编辑 draw.io 源文件](docs/figures/architecture.drawio) · [PNG 版本](docs/figures/architecture.png)

> **任务层视觉开环，底层关节反馈闭环。** GPT 决定去哪里、怎么夹；它不生成 200 Hz 的每一个控制点，也不直接写 CAN。

## 真实实验

2026-09-17，物理左臂依次将 **青椒、胡萝卜、茄子** 放入篮筐，随后回位。最后一次运行无中途重新规划或保护暂停。

| 结果 | 实测值 |
|---|---:|
| 三物体任务 | **3 / 3 入筐**，结束图像和现场用户确认 |
| 整段执行耗时 | **85.42 s** |
| 主机目标发送频率 | **200.000 Hz** |
| 指令间隔 P99 | **5.116 ms** |
| 指令记录 / 状态反馈 | **17,046 / 4,228** 条 |
| 执行中视觉 / 小 VLM 调用 | **0 / 0** |

| 执行前 | 执行后 |
|:---:|:---:|
| ![三个物体与篮筐](experiments/2026-09-17/before.jpg) | ![三个物体已入筐](experiments/2026-09-17/after.jpg) |

另一次单物体连续运行用时 **31.54 s**，入筐由现场用户确认。此前也发生过空夹、高度保护暂停和 CAN 名称与物理左右臂不一致等问题，均保留在[实验沿革](docs/EXPERIMENTS.md)中。

这些是已记录的单轮结果，**不是长期成功率或严格对照实验**。200 Hz 指主机发送目标的频率，不代表电机内部控制环频率。仓库中的重构代码完成了离线回归验证；上述真机数据来自整理前的实验版本，不能当作重构版本已重新上机验证的证据。

## 快速开始

Python 3.10+。默认流程不需要机器人、相机、模型权重或 inference 内部代码。

```bash
git clone https://github.com/Srt-tian/RoboRSI_v1.git
cd RoboRSI_v1
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/verify_evidence.py
```

**离线编译已记录的粗轨迹：**

```bash
roborsi-compile examples/three_objects.json \
  --speed 2 --tcp-floor 0 --output runs/three_objects.stream.json
```

生成 17,046 个 200 Hz 目标，计划时长约 **85.23 s**。实际记录的 85.42 s 还包含最终状态收敛等待。输出文件必须不存在，以避免覆盖已记录的计划。

未提供 `--urdf` 时只做轨迹和数值检查，输出标记为 `geometry_verified: false`。历史示例始终标为不可执行，不可直接向真机重放。

**在本机查看实测反馈：**

```bash
roborsi-report experiments/2026-09-17/servo20_three_deep.jsonl.feedback.jsonl \
  --output runs/viewer
python -m http.server 8786 --bind 127.0.0.1 --directory runs/viewer
```

打开 **http://127.0.0.1:8786/**，可播放、单步或拖动查看跟踪误差、TCP、夹爪开度和队列状态。显示的是约 50 Hz 的实测反馈，不是把计划插值冒充实测。

## 系统分工

| 模块 | 输入 → 输出 | 实现 / 边界 |
|---|---|---|
| 场景与粗规划 | 图像、任务、历史经验 → 物体顺序、抓取与放置关键点 | 目前由交互式 GPT 会话完成；**不包含独立 GPT API 服务** |
| 像素到基座 | 像素、内外参、高度平面 → 近似目标坐标 | 实验使用名义 URDF 外参与历史偏移；不是通用精确定位器 |
| 运动学 | 末端目标与种子 → 关节配置 | [`ik.py`](src/roborsi/ik.py)，FK、Jacobian、有界 IK |
| 几何检查 | 关节配置 → 接受 / 拒绝 | [`geometry.py`](src/roborsi/geometry.py)，当前装配参数专用，非完整网格碰撞检测 |
| 平滑与时间缩放 | 粗关节路径 → 200 Hz 目标流 | [`smoothing.py`](src/roborsi/smoothing.py)，C1 单调插值、速度与加速度约束 |
| 流编译 | 粗轨迹与夹爪事件 → 带来源信息的执行文件 | [`compiler.py`](src/roborsi/compiler.py)，夹爪开合独立于关节插值 |
| 执行适配 | 目标流 → 原 inference 控制线程 | [`runtime.py`](src/roborsi/runtime.py)，明确 opt-in、源码哈希与硬件映射检查 |
| 停止保持 | 异常 / 用户停止 → 一次实测目标冻结 | [`hold.py`](src/roborsi/hold.py)，取消唯一写线程并清队列，保留支撑与夹持 |
| 实验可视化 | 实测反馈 → 本机 Web | [`reporting.py`](src/roborsi/reporting.py)，不进入控制关键路径 |

### 为什么平滑不等于“让 GPT 多输出一些点”？

关键点表达任务结构，时间参数化决定以什么速度经过这些点。控制线程则以固定 5 ms 节拍更新目标：三者职责不同。

- 同一条路径加速 2 倍，速度约为 2 倍，加速度约为 4 倍，所以必须重新检查动态限值。
- 夹爪开合保留各 0.8 s 的驻留，不能按运动倍速机械缩短。
- 实验曾复用 inference 的 temporal overlap 缓冲；固定计划的重叠片段相同，没有独立预测可集成。整理版直接生成同样的细目标，不引入虚假的 ensemble 收益。
- 平滑和高频控制只能更好地跟随既定轨迹，**不能修正错误的抓取位置**。

## 计划与数据约定

- 单位：米、真实弧度、秒。
- `q14 = [left_j1…left_j6, left_gripper, right_j1…right_j6, right_gripper]`。
- `trajectory.joint_waypoints` 为左臂 Nx6 序列，包含起点；连续阶段的首尾必须一致。
- `gripper` 为独立事件，带目标开度和闭合 / 张开后的检查区间。
- 右臂在此版本保持，不是双臂协作策略。
- SDK 的旧近似弧度转换只在硬件边界处理，不能混进 IK 或分析数据。

完整字段示例见 [`examples/three_objects.json`](examples/three_objects.json)。这份历史计划绑定当时的桌面、物体、相机与初始姿态，不是通用抓取模板。

## 真机接入

见 [硬件接入与停止语义](docs/HARDWARE.md)。必须使用自己的已标定 URDF、实际相机/桌面配置、明确的物理左右臂映射，以及匹配源码哈希的 inference checkout。

**默认命令只离线工作；`--execute` 是显式硬件入口。** 本仓库不分发内部 inference 源码、SDK、模型权重、现场机器配置或供应商网格资产。运行依赖与来源见 [PROVENANCE.md](docs/PROVENANCE.md)。

## RSI 的现状与下一步

目前已具备可追溯的“失败 → 诊断 → 人工审核修改 → 下一轮验证”过程，例如纠正 CAN 映射、修正定位偏差、调整抓取深度和夹爪方向。尚未把这些修改变成自动训练或有统计验证的策略更新。

下一步优先补齐：

1. 相机到基座及桌面高度的独立校验，区分定位误差与控制误差。
2. 固定复位协议下的重复试验，报告任务/物体成功、干预次数和总耗时。
3. 冻结计划与经验修订的对照，再判断局部 VLM 是否有实际增益。

## 自动检查

本地测试与证据校验命令见快速开始。[GitHub Actions 模板](ci/github-actions-tests.yml) 已准备好；当前推送凭据没有 `workflow` 权限，所以未启用远端 CI。具备该权限后，将模板放到 `.github/workflows/tests.yml` 即可。

## 仓库布局

```text
src/roborsi/          # 可复用计算、编译、执行适配和报告
examples/            # 历史粗轨迹，默认不可发到真机
experiments/         # 实测指标、结果图、成功与失败记录
docs/                # 接入、实验、来源和可编辑系统图
scripts/             # 文档图生成等维护工具
tests/               # 离线数值、事件与停止语义测试
```

研究背景：本项目沿用 [Show-Harness](https://showlab.github.io/Show-Harness/) 启发的交互实验方式，但不是其官方实现，也不声称完整复现了其论文结论。
