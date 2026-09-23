# 中文研究稿：延迟感知与非生成式判断

更新：2026-09-23。内部研究稿，未投稿；论文主张受限于当前实验。作者与单位待团队确认。

使用 CoRL 2026 官方 `corl_2026.sty`、`corlabbrvnat.bst`，原样保留。
`preprint` 选项避免把内部稿误标为已投稿/录用；中文使用 XeLaTeX + ctex/Fandol。
中文排版是内部讨论版本，不等同于满足正式英文投稿要求。

## 近期会议核查

| 会议 / 场合 | 举办时间 | 截稿与格式 | 与当前工作的关系 |
| --- | --- | --- | --- |
| CoRL 2026 主会 | 2026-11-09 至 11-12，Austin | 主会全文 2026-05-28 已截止；初稿正文 8 页 | 采用其官方模板，不视为仍可投主会 |
| Efficient Foundation Models for Real-Time Embodied AI，CoRL workshop | 2026-11-12 | 2026-10-12 23:59 AoE；4 页扩展摘要 + 参考文献，双盲、非归档 | 时延决策方向相关；当前不是基础模型压缩研究，需要明确契合点 |
| Continually Self-Improving Robots，CoRL workshop | 2026-11-12 | 至多 8 页正文，任意学术模板，双盲、非归档；所查页面未列具体截止日期 | RSI 更贴近主题；已完成一轮更新，额外样本效率尚未证实 |
| ICLR 2027 投稿周期 | 摘要 2026-09-18；全文 2026-09-25，均 AoE | 摘要截止已过；正文 9 页 | 未按时注册摘要则不能新投，本轮不为赶截止夸大结果 |

来源：[CoRL 官网](https://www.corl.org/)、[作者指南与官方模板](https://2026.corl.org/contributions/instruction-for-authors)、[实时具身 AI workshop](https://efficient-embodied-ai.github.io/)、[CSIR workshop](https://csircorl.github.io/website/)、[ICLR 官方作者指南](https://iclr.cc/Conferences/2027/AuthorGuidelines)。
会议举办日期、主会截稿、workshop 截稿分别记录；没有将 workshop 视为主会正式论文。

## 模板来源与构建

官方模板入口：上述 CoRL 作者指南中的 submission template。
原始文件：[官方 ZIP](https://drive.google.com/file/d/1R9irIW0ImqeDHh5g8Ukm2XGy91sWxOsQ/view?usp=drive_link)。
仅提取样式和 bibliography 文件，不把官方示例文字作为我们的论文内容。

```bash
python plot_results.py --run /path/to/phase_study_001 \
  --audit /path/to/phase_audit_001/audit.json --output .
xelatex -interaction=nonstopmode -halt-on-error draft_cn.tex
bibtex draft_cn
xelatex -interaction=nonstopmode -halt-on-error draft_cn.tex
xelatex -interaction=nonstopmode -halt-on-error draft_cn.tex
```

Matplotlib 3.10.7 生成矢量统计图和表格。`phase_pipeline.drawio` 为可编辑框架图；PNG 供论文和 Web 使用。
数值对应研究分支提交 `7953b35c5a493876b65d66cf92562d673cc45e75`；审计/回放代码为 `0bfcb808e4c94822606517b282f5dbd01e8718c2`。

## 当前成熟度

- 已完成：两种 MuJoCo 接触任务、1,500 检查点、4,500 分支、12 模型、强规则、消融、配对区间、30 段逐步一致录像。
- 已补充：一轮离线 RSI 更新，9 个交叉拟合模型、12 个更新模型、600 个新测试场景；等预算反例采样优势未证实。
- 尚缺：第三种任务、真实视觉、完整任务的多次判断、多个独立采样种子的确认性复验与持续在线 RSI。
- 研究结论：长延迟抓取局部收益；同分布阶段查表更强；动作历史优势未证实。
- 本稿不将已授权的代码/工具协作视为人类作者审核或投稿授权；当前未进行任何投稿或对外联系。

参考文献已核查一手页面。使用 AI 辅助了研究设计、实现、分析和起草；正式稿应依会议政策由人类作者核对、负责并如实披露。

RSI 执行提交：`a12cc5d8b1adf43c18bb70f098d26445f383cecb`；分支审计与 CPU 移植代码：`91f5f34c90ac238f3ff62a0e0ee1846e0954bf9a`。
