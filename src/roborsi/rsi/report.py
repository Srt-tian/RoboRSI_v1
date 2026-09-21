"""Self-contained, offline HTML for evidence triage and timing comparisons."""

import json


def render(evidence, sweep):
    data = (
        json.dumps(
            {"evidence": evidence, "sweep": sweep}, ensure_ascii=False, allow_nan=False
        )
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    return PAGE.replace("__REPORT_DATA__", data)


PAGE = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RoboRSI · 离线迭代工作台</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0b1220;color:#e6edf6;font:16px/1.65 system-ui;margin:0}
main{max-width:1200px;padding:38px 24px;margin:auto}h1{font-size:34px;margin:8px 0}h2{font-size:22px;margin-top:30px}
.eyebrow{color:#59d7c4;letter-spacing:2px;font-size:13px}.muted,p{color:#a3b4cb}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.card,section{background:#142035;border:1px solid #293b56;border-radius:12px;padding:18px}.number{font-size:30px;color:#59d7c4}
table{width:100%;border-collapse:collapse}th,td{padding:12px 10px;text-align:left;border-bottom:1px solid #293b56}
th{color:#a3b4cb;font-weight:500}button,select{background:#20344e;color:#e6edf6;border:1px solid #405779;border-radius:6px;padding:8px 12px;cursor:pointer}
button:hover,button:focus-visible{border-color:#59d7c4}.tag{color:#ffbc7b}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 ui-monospace,monospace}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.scroll{overflow:auto}.note{border-left:3px solid #ffbc7b;padding:8px 16px}
@media(max-width:760px){.cards,.grid{grid-template-columns:1fr 1fr}main{padding:20px 14px}.grid{grid-template-columns:1fr}}
</style><main><div class="eyebrow">ROBORSI / EVIDENCE → CANDIDATE → VALIDATION → REVIEW</div>
<h1>离线迭代工作台</h1><p>历史证据复盘与候选时间配置对比 · 本页面没有机器人控制接口</p>
<div class="cards" id="cards"></div>
<h2>实验记录 <select id="filter" aria-label="筛选实验"><option value="all">全部</option><option value="failed">执行失败</option><option value="complete">执行完成</option></select></h2>
<section class="scroll"><table><thead><tr><th>实验</th><th>执行状态</th><th>任务结果记录</th><th>观测到的故障</th><th></th></tr></thead><tbody id="trials"></tbody></table></section>
<h2>记录详情</h2><div class="grid"><section><h3>事实与待验证假设</h3><pre id="diagnosis"></pre></section><section><h3>来源与指标</h3><pre id="metrics"></pre></section></div>
<h2>候选离线评估</h2><p>固定同一粗计划，比较已有 1× / 2× 档位。预计耗时来自重编译，不是新真机测量。</p>
<section class="scroll"><table><thead><tr><th>候选</th><th>验证</th><th>目标点</th><th>预计耗时</th><th>几何检查</th><th>物理成功</th></tr></thead><tbody id="candidates"></tbody></table><pre id="errors"></pre></section>
<p class="note">数值通过、几何通过、任务成功是不同证据。规则分类不构成因果诊断；候选排序不自动写入经验，也不授权真机执行。</p>
<details><summary>复现信息与证据指纹</summary><pre id="provenance"></pre></details></main>
<script type="application/json" id="data">__REPORT_DATA__</script><script>
const d=JSON.parse(document.querySelector('#data').textContent),e=d.evidence,s=d.sweep;
function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n}
for(const [label,value] of [['实验记录',e.summary.trials],['执行失败',e.summary.execution_failed],['任务结果有文字记录',e.summary.task_reports],['自动确认任务成功','未实现']]){const c=node('div','');c.className='card';c.append(node('div',label));const n=node('div',value);n.className='number';c.append(n);document.querySelector('#cards').append(c)}
function details(t){document.querySelector('#diagnosis').textContent=JSON.stringify({task_outcome:t.task_outcome,...t.diagnosis},null,2);document.querySelector('#metrics').textContent=JSON.stringify({record_sha256:t.record_sha256,...t.metrics},null,2)}
function draw(){const b=document.querySelector('#trials');b.replaceChildren();const f=document.querySelector('#filter').value;for(const t of e.trials.filter(t=>f==='all'||t.execution_status===f)){const row=node('tr','');for(const v of [t.trial_id,t.execution_status,t.task_outcome.status,t.diagnosis.observation])row.append(node('td',v));const td=node('td',''),button=node('button','查看');button.onclick=()=>details(t);td.append(button);row.append(td);b.append(row)}}
document.querySelector('#filter').onchange=draw;draw();details(e.trials[0]);
for(const r of s.candidates){const row=node('tr','');for(const v of [r.policy.candidate_speed+'×',r.status,r.candidate?.target_count??'—',r.candidate?r.candidate.duration_s.toFixed(3)+' s':'—',r.geometry_status,r.physical_success])row.append(node('td',v));document.querySelector('#candidates').append(row)}
document.querySelector('#errors').textContent=s.candidates.flatMap(r=>r.errors).join('\\n');
document.querySelector('#provenance').textContent=JSON.stringify({source:e.source,evidence_sha256:e.artifact_sha256,sweep_sha256:s.artifact_sha256,selected_comparison_sha256:s.selected_comparison_sha256,selection_scope:s.selection_scope,limitations:e.limitations},null,2);
document.body.dataset.loaded='true';
</script></html>"""
