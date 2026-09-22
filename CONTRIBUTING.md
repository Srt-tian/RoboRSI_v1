# 开发与文档维护

核心默认工作流为离线编译、数值测试和实测反馈可视化。导入、测试、CI、图生成、报告生成不得连接机器人或写 CAN。

## 本地检查

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/verify_evidence.py
```

测试验证运动学、数值轨迹、夹爪事件、流校验和停止保持。归档脚本验证实验原始文件指纹，并复算最后一轮命令频率。不要为了文档调整修改历史记录、指标或轨迹点。

RSI 测试还验证未知任务结果、证据指纹、候选改动范围、不可放宽的上下文/夹爪检查、经验范围选择与离线工作台。新增候选生成器只提交数据给 `rsi.evaluation.evaluate`，不得把生成的代码导入控制进程。规则诊断与审核记录不能替代物理效果评测。

## 修改架构与流程图

源文件生成器为 `scripts/draw_architecture.py`，输出四份可编辑原生 draw.io XML：

```bash
python scripts/draw_architecture.py
# 安装 drawio-skill 时可用其 scripts/validate.py 验证 XML。
drawio -x -f png --width 1800 -o docs/figures/architecture.png docs/figures/architecture.drawio
drawio -x -f png --width 1800 -o docs/figures/execution_flow.png docs/figures/execution_flow.drawio
drawio -x -f png --width 1800 -o docs/figures/rsi_cycle.png docs/figures/rsi_cycle.drawio
drawio -x -f png --width 1800 -o docs/figures/typed_judgment.png docs/figures/typed_judgment.drawio
# 检查 PNG 的文字、连线和分支后导出 SVG。
drawio -x -f svg -e --embed-svg-images -o docs/figures/architecture.svg docs/figures/architecture.drawio
drawio -x -f svg -e --embed-svg-images -o docs/figures/execution_flow.svg docs/figures/execution_flow.drawio
drawio -x -f svg -e --embed-svg-images -o docs/figures/rsi_cycle.svg docs/figures/rsi_cycle.drawio
drawio -x -f svg -e --embed-svg-images -o docs/figures/typed_judgment.svg docs/figures/typed_judgment.drawio
```

Linux 图形环境的启动参数按本机配置补充。四张图共用字体和色板；新增判断图区分离线原型和在线研究目标。人工修订与下一轮反馈使用虚线，不画成已经实现的在线自动学习模块。修改机制时同步检查 README、架构说明和执行流程，防止图比代码“多实现”功能。

## 判断与仿真迭代

provider 测试必须 mock 网络，不在测试中读取真实密钥或加载权重。新增 provider 通过同一分布、时效、上下文检查，不能绕过比较报告。阶段 revision 的语义由观测层负责；哈希并非真实性证明。

仿真逻辑测试检查共同保护、可见性、过时建议、滑落恢复、确定性种子和逐步记录完整性。使用新目录记录每轮实验，媒体导出后运行 `scripts/verify_paper_run.py`，再更新 `scripts/build_paper_index.py`。封存目录不可原位改结果，网页索引可重新生成；仿真源代码变化后保留旧记录并创建新运行。

详细命令见 [SIMULATION.md](docs/SIMULATION.md)。当前 HTML 支持本地浏览器解压 gzip，需要支持 `DecompressionStream` 的现代浏览器；文件必须通过本机 HTTP 服务访问。媒体导出额外依赖 Pillow 与 ffmpeg，核心判断/仿真无需这些依赖。

## 变更边界

- 改控制链路需测试单写者、故障传播、停止与保持，不把离线回归称为真机验收。
- 不能把计划点冒充实测反馈，也不能把程序结束等同于任务成功。
- 当前 URDF 布局、q14 顺序和几何假设不是通用多构型接口；扩展设备必须显式验证。
- 源码、文档、图的嵌入元数据中均不得出现认证信息或私有机器配置。

[GitHub Actions 模板](ci/github-actions-tests.yml) 提供了离线检查。当前模板未启用为 workflow；有相应权限的维护者可放入 `.github/workflows/tests.yml`。不要声称远端 CI 已运行。
