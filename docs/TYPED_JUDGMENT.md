# 结构化判断与阶段契约 · v0.3

本模块将 Jev 式判断用于 **离线 RSI 候选审核**。它不把模型连入实时执行器。默认 provider 为 `disabled`，不联网、不下载模型、不发送 CAN。

## 一条命令看完整示例

安装本仓库后，在仓库根目录运行：

```bash
python scripts/demo_judgment.py --output runs/judgment_demo
python -m http.server 8788 --bind 127.0.0.1 --directory runs/judgment_demo
```

打开 **http://127.0.0.1:8788/**，可以查看历史证据、候选时间配置与判断详情；也可直接打开生成的 HTML。示例 provider 固定输出 `collect_evidence`，模型名明确标为 `synthetic-fixture-not-a-model`。这验证数据流，不测试模型智能。

输出同时包含独立的 `.synthetic.json` 阶段契约/观测与概率评测样例；这些数值均为构造数据，不是历史实验测量。示例候选只做数值复算，几何检查未运行。真实历史记录与合成数据不合并成新的实验成功率。

## 从候选到审核

| 命令 | 输入 → 输出 | 关键规则 |
| --- | --- | --- |
| `checkpoint` | 阶段契约 + 观测快照 → 路由事件 | 区分 `continue / collect_evidence / request_judgment / stop_review / discard_context`；没有运动效果 |
| `prepare-judgment` | evidence + comparison(s) + scope → request | 比较须共享基线、配置和实现版本；最多 32 个候选；默认必须通过现有几何检查 |
| `judge` | request + provider → judgment | 检查完整分布、选项、类型、概率/间隔、证据充分性、时效和请求身份 |
| `review --judgment` | 选定 comparison + judgment + 人工审核 → review | 指纹、trial、scope 必须匹配；模型建议不等于人工采用 |
| `context` | 已审核记录 + 精确 scope → 规划参考 | 保留 judgment 指纹；经验不会成为可执行命令 |
| `calibrate` | 标注概率数据 → 留出评测报告 | validation 选门限，test 仅评分；不自动安装门限 |
| `report-judgment` | evidence + sweep + judgment → 本地 HTML | 检查 evidence 与候选关联，网页不调用模型 |

使用 demo 生成的文件构建一份新的请求：

```bash
roborsi-rsi prepare-judgment \
  --evidence runs/judgment_demo/evidence.json \
  --comparison runs/judgment_demo/profile_1x.json \
  --comparison runs/judgment_demo/profile_2x.json \
  --trial-id servo18_three \
  --scope runs/judgment_demo/scope.json \
  --numerical-only --output runs/request_v2.json
```

`--trial-id` 取自 `evidence.json` 的 `trials[].trial_id`，这里是归档中的一次失败记录。`--numerical-only` 明确开启影子审核；其结果标记 `numerical_shadow`，不是通过几何校验的真机候选。正式离线几何验证从 `evaluate --urdf ...` 开始，但现有几何器仍只覆盖本装配的已检查约束。

```bash
# 不指定 provider 时，保存 provider_disabled 拒判记录。
roborsi-rsi judge --request runs/request_v2.json --output runs/judgment_disabled.json

# 显式合成接口示例；不调用模型。
roborsi-rsi judge --request runs/request_v2.json --provider demo \
  --output runs/judgment_demo_v2.json

# 回放必须绑定完全相同的 request 指纹；原请求默认 600 秒过期。
roborsi-rsi judge --request runs/judgment_demo/request.json \
  --provider replay --response runs/judgment_demo/reply.synthetic.json \
  --output runs/replay_result.json
```

过期请求不通过修改时间来冒充原始在线判断。要做长期历史回放，可直接读取已保存 judgment，或通过 Python API 显式注入历史 clock；这只能用于离线测试。

## 官方 Jev 接口与本地模型扩展

TypeSafe adapter 使用官方 [HTTP API](https://docs.typesafe.ai/api)，调用 `POST https://api.typesafe.ai/v1/systemone`，发送 `model / state / questions`。当前默认请求固定版本 `jev-1.13.0`，同时保存服务返回的模型标识；需自行核验该版本在调用时仍可用。没有自动重试或自动降级成其他模型。

```bash
# 由使用者在进程环境安全注入 TYPESAFE_API_KEY；不要写进 JSON、仓库或日志。
roborsi-rsi judge --request runs/request_v2.json \
  --provider typesafe --allow-network --timeout 5 \
  --output runs/judgment_typesafe.json
```

**状态会发送给 TypeSafe。** 当前 payload 包含声明的范围、筛选后的指标/候选摘要和问题，不包含终局任务结果字段、原始照片或鉴权值。本版只做了 mock HTTP 合约测试，尚未完成真实付费 API 验证。网络 timeout 是 socket 层设置，不能保证函数在严格墙钟时限内返回；因此适配器只能放在控制线程之外，迟到结果会被丢弃。拒绝重定向以避免把鉴权头带到另一地址，响应大小限制为 1 MiB。

`providers.JudgmentProvider` 是最小可替换接口：

```python
class LocalDecisionProvider:
    name = "my_local_model"

    def predict(self, request: dict, *, timeout_s: float) -> dict:
        # 编码 request['state'] 和 request['questions']，一次返回有类型的判断。
        return {
            "request_sha256": request["artifact_sha256"],
            "response": {"model": "pinned-model-version", "answers": answers},
        }
```

Choice 返回 `type / choice / probabilities / confidence`，支持集必须与问题菜单完全一致，概率有限、非负、总和为 1，choice 必须为最大概率选项。Noul 返回 `type / noul`，数值在 `[0,1]`。本版只需要这两种类型。`confidence` 原样单独保存，门控使用最大概率及第一、第二选项差值；三个问题独立预测后仍需代码组合，不能假设天然一致。

## 阶段契约与过时建议

契约样式见 demo 的 `contract.synthetic.json`：`scope / program_sha256 / phase / expected / hard_limits / max_observation_age_s`。观测携带对应计划、阶段、时间和 `revision`。`expected` 是任务预期范围，`hard_limits` 是这个离线检查器的区间限制，不是完备机器人安全模型。

```bash
roborsi-rsi checkpoint --contract my_phase_contract.json \
  --observation fresh_observation.json --output runs/checkpoint.json
```

若事件是 `request_judgment`，可在 `prepare-judgment` 加 `--checkpoint runs/checkpoint.json`。随后 `judge` 必须提供 `--current-checkpoint path/to/current.json`，推理前后分别读取并检查。计划、契约、阶段、语义 revision 与 scope 不一致，事件过期，或当前事件已不需要判断，都拒绝建议。

CLI 的 `current.json` 仍是外部提供的快照；本仓库没有在线 observer。将来更新它需原子替换文件，或通过 `judge(..., context_probe=...)` 提供同步的快照读取器。revision 的增量逻辑必须由观测层实现，不能靠本模块判断物体是否真的移动。哈希检查只能检出内容变化，不能认证来源。

## 评估概率与拒判

```bash
roborsi-rsi calibrate examples/decision_dataset.synthetic.json \
  --min-accepted 2 --output runs/calibration_demo.json
```

这个很小的合成例子故意包含“验证集自信正确、测试集自信错误”的情况，展示验证集门限不保证测试集低风险。没有模型性能含义。正式数据须用独立标注，记录标签来源、问题族、模型版本和 episode group；不能用 `execution_status=complete` 自动生成“抓取成功”标签。

实现检查重复 case 和跨 validation/test 的 group 泄漏。先从固定门限集合选择满足最少样本数与经验错误率的最大覆盖点，再冻结门限报告 test 指标；无可行门限时全部拒判。报告包含多类 Brier、截断 NLL、10-bin ECE、接受数与覆盖率/错误率。它是**拒判工作点评测**，不拟合温度缩放，也不保证有限样本风险。

## 文件与代码边界

`contracts.py` 管阶段快照，`judgment.py` 管候选和门控，`providers.py` 管模型适配，`calibration.py` 管分组留出评测。`evaluation.py` 仍负责确定性重编译，`memory.py` 仍要求显式审核。`runtime.py`、平滑与 200 Hz 下发机制未改变。

终端输出一个合法 `abstain` 是成功保存判断结果，CLI 退出码为 0；候选比较拒绝沿用退出码 2。下游必须读取 `decision / reason`，不能把进程退出成功当成候选被采用。

[方案与消融](RESEARCH_PROPOSAL.md) · [11 项生态调研与相关论文](JEV_RESEARCH_2026_09.md)
