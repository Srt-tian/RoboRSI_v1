# RSI：证据、离线验证与跨轮经验

[返回首页](../README.md) · [四层架构](ARCHITECTURE.md) · [近期工作与研究路线](RESEARCH_2026_09.md) · [历史修订案例](../experiments/2026-09-17/rsi_review.md)

RSI 层现在有可运行的离线工作流：自动整理指标、规则分型、比较候选计划、枚举时间配置、保存审核记录，并按适用范围选取规划上下文。轨迹修订的语义判断与采用仍需人工审核；没有自动模型训练、真机试错或执行中重规划。

![RSI 的证据、候选检查、审核与下一轮验证闭环](figures/rsi_cycle.svg)

[可编辑 draw.io](figures/rsi_cycle.drawio) · [PNG](figures/rsi_cycle.png)

## 快速运行

安装项目后在仓库根目录运行；也可将 `roborsi-rsi` 替换为 `PYTHONPATH=src python -m roborsi.rsi`。

```bash
roborsi-rsi workbench \
  --metrics experiments/2026-09-17/metrics.json \
  --program examples/three_objects.json \
  --tcp-floor 0 --output runs/rsi_demo
python -m http.server 8787 --bind 127.0.0.1 --directory runs/rsi_demo
```

打开 **http://127.0.0.1:8787/**。HTML 也可直接用本机浏览器打开，无 CDN、模型服务或网络请求。工作台有实验筛选、故障详情、原记录、候选对比和来源指纹。

输出目录必须不存在，包含 `evidence.json`、`sweep.json`、`profile_1x.json`、`profile_2x.json` 和 `index.html`。这里 `--tcp-floor 0` 仅复算历史场景；未提供 `--urdf` 时不会验证几何。工作台读取已有指标，不重算原始日志；另运行 `python scripts/verify_evidence.py` 校验原始归档。

## 四份产物与接口

| 产物 | 命令 / 代码 | 内容 |
| --- | --- | --- |
| 证据 D | `analyze` / [evidence.py](../src/roborsi/rsi/evidence.py) | 原指标、逐记录指纹、执行状态、任务结果文字、观测与待验证假设 |
| 候选验证 V | `evaluate`、`sweep` / [evaluation.py](../src/roborsi/rsi/evaluation.py) | 基线/候选计划指纹、验证器代码指纹、约束、改动量、重编译结果 |
| 审核经验 E | `review` / [memory.py](../src/roborsi/rsi/memory.py) | 关联证据、完整比较报告、审核者声明、采用/拒绝、适用范围和经验文字 |
| 规划上下文 C | `context` / [memory.py](../src/roborsi/rsi/memory.py) | 只选范围精确匹配且明确采用的记录；保留来源与验证限制 |

每份产物包含 `schema`、`artifact_sha256` 和 `execution_authorized=false`。指纹检测内容变化，不提供签名认证，也不能阻止有写权限的人重新生成文件。JSON 不执行代码；没有机器人驱动导入、CAN 接口或自动动作提交。

```text
历史指标 → analyze → 证据 D + 规则分型
新候选 JSON + 基线 JSON → evaluate → 候选报告 V
同一计划 → sweep → 1× / 2× 有限枚举与预计时长排序
D + V + 明确审核 + scope → review → 经验 E
E + 精确匹配 scope → context → 规划上下文 C
C + 新场景 → GPT / IK 重新规划 → 编译 → 单独的真机执行流程
```

## 证据不等于归因

`analyze` 支持 `metrics.json` 形式的非空列表，要求唯一 `log`、`execution_status`、非负 `elapsed_s`、整数 `command_rows` / `feedback_rows`。可选 `failure`、`task_result` 等字段原样保留。重复 ID、重复 JSON 键、非有限数值或“完成但同时记录失败原因”的冲突会拒绝。

- `execution_status=complete` 只代表执行完成。
- 有 `task_result` 文字时标记 `reported`，不把自由文本自动转成成功率。
- 缺少任务结果时标记 `unknown`；历史实验沿革中的人工判断需另外关联。
- 夹爪、TCP 下限、执行时序故障按明确错误文本分型。`attribution=unresolved` 保留多种假设，没有自动因果判定。

这些规则借鉴近期工作对归因和验证的重视，但不是 CHIME 或 Zetta 的算法复现。见[论文对照](RESEARCH_2026_09.md)。

## 候选验证边界

```bash
roborsi-rsi evaluate baseline.json candidate.json \
  --baseline-speed 1 --candidate-speed 1 \
  --max-joint-delta 0.12 --urdf local/rig.urdf \
  --output runs/iteration_01/comparison.json
```

目前只接受**同一上下文与阶段结构下的关节关键点数值修订**。默认每个关节值最大变化 0.12 rad；验证器允许配置的范围上限为 0.25 rad。相同初始状态、场景、其他元数据、轨迹点布局、阶段顺序、夹爪开合和检查范围必须保持；结束状态也必须一致。路径重新通过现有编译器与流验证器。

`tcp_floor` 和 URDF 由一次比较共用，候选文件不能自行调低地板或放宽夹爪检查来通过。若任务需要改变物体顺序、夹爪策略或复位状态，需作为新计划单独审核，不属于当前局部修订比较。

`offline_validated` 表示数值重编译通过；`geometry_status=passed` 还要求提供 URDF 并通过现有装配几何检查。该检查不是完整接触仿真或环境网格碰撞证明。`physical_success=not_evaluated` 始终明确。拒绝报告保留错误并让 `evaluate` 返回退出码 2。

`sweep` 仅枚举既有 1×、2× 档位，以预计时长排序，是确定性的小规模搜索。它不生成新的抓取姿态，也不优化真实成功率；选中的报告不会自动升级为经验。所有命令输出报告，不输出可发到机器人的目标流。

## 审核与经验选择

准备一份本地范围文件，例如 `scope.json`：

```json
{"robot": "piper-dual", "setup": "table-calibration-v1", "task": "three-object-pick-place"}
```

阅读证据与候选报告后记录自己的判断：

```bash
roborsi-rsi review --evidence runs/rsi_demo/evidence.json \
  --comparison runs/rsi_demo/profile_2x.json --trial-id servo20_three_deep \
  --scope scope.json --reviewer YOUR_REVIEWER_ID \
  --decision accept_for_planning \
  --lesson '该场景已有 2× 连续执行记录；新场景仍需独立检查。' \
  --output runs/reviews/timing.json
roborsi-rsi context runs/reviews/timing.json --scope scope.json \
  --output runs/planning_context.json
```

`accept_for_planning` 只接受离线比较已通过的记录，也支持保存 `reject`。审核者和经验内容由调用者明确声明，不冒充历史运行时已有审批记录。关联实验与候选的关系也是审核者声明，不构成匹配对照或因果证据。

选择器精确匹配 `robot`、`setup`、`task`，不允许通配范围，去重并说明被排除的原因。输出供规划者阅读；没有自动 GPT 调用或向执行器注入参数。场景、校准或装配变化后应使用新 `setup` 标识。即使数值或几何通过，经验仍标明物理有效性未验证。

## 扩展入口与下一步

新模型可在外部产生候选粗计划 JSON，统一调用 `evaluate()`；不把模型生成的 Python 导入验证器。新的证据来源先适配为指标列表，保留来源，不能悄悄改变结果语义。支持 TCP 级修订时，先增加物体/阶段/位姿到关节路径的显式接口，再复用本层。

当前新增的是**离线迭代工具链**。自动视觉判定、生成式修订、物理仿真、留出场景评测及自主真机循环尚未实现。人工复盘仍可使用[模板](templates/RSI_REVIEW.md)；[三物体案例](../experiments/2026-09-17/rsi_review.md) 是事后整理，不是本次新增实验。
