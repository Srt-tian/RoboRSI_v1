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

源文件生成器为 `scripts/draw_architecture.py`，输出三份可编辑原生 draw.io XML：

```bash
python scripts/draw_architecture.py
# 安装 drawio-skill 时可用其 scripts/validate.py 验证 XML。
drawio -x -f png --width 1800 -o docs/figures/architecture.png docs/figures/architecture.drawio
drawio -x -f png --width 1800 -o docs/figures/execution_flow.png docs/figures/execution_flow.drawio
drawio -x -f png --width 1800 -o docs/figures/rsi_cycle.png docs/figures/rsi_cycle.drawio
# 检查 PNG 的文字、连线和分支后导出 SVG。
drawio -x -f svg -e --embed-svg-images -o docs/figures/architecture.svg docs/figures/architecture.drawio
drawio -x -f svg -e --embed-svg-images -o docs/figures/execution_flow.svg docs/figures/execution_flow.drawio
drawio -x -f svg -e --embed-svg-images -o docs/figures/rsi_cycle.svg docs/figures/rsi_cycle.drawio
```

Linux 图形环境的启动参数按本机配置补充。三张图共用字体和色板；架构图侧重四层职责，RSI 图侧重跨轮改进，执行图侧重本轮条件和顺序。人工修订与下一轮反馈使用虚线，不画成已经实现的在线自动学习模块。修改机制时同步检查 README、架构说明和执行流程，防止图比代码“多实现”功能。

## 变更边界

- 改控制链路需测试单写者、故障传播、停止与保持，不把离线回归称为真机验收。
- 不能把计划点冒充实测反馈，也不能把程序结束等同于任务成功。
- 当前 URDF 布局、q14 顺序和几何假设不是通用多构型接口；扩展设备必须显式验证。
- 源码、文档、图的嵌入元数据中均不得出现认证信息或私有机器配置。

[GitHub Actions 模板](ci/github-actions-tests.yml) 提供了离线检查。当前模板未启用为 workflow；有相应权限的维护者可放入 `.github/workflows/tests.yml`。不要声称远端 CI 已运行。
