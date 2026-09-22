"""Standalone interactive viewer for the kinematic decision sandbox."""

import json


def render_simulation(result):
    data = (
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    return PAGE.replace("__SIM_DATA__", data)


PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RoboRSI · 决策时序仿真</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#e6edf6;font:16px/1.6 system-ui}
main{max-width:1250px;margin:auto;padding:30px 24px}.eyebrow{color:#59d7c4;letter-spacing:2px;font-size:13px}h1{margin:8px 0;font-size:32px}
p{color:#a5b7cc}.note{border-left:3px solid #ffba78;padding:8px 16px}section{background:#142035;border:1px solid #304159;border-radius:12px;padding:18px;margin:18px 0}
button,select{background:#20344e;color:#e6edf6;border:1px solid #476182;border-radius:6px;padding:8px 12px;cursor:pointer}button:focus-visible,select:focus-visible{outline:2px solid #59d7c4}
.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}canvas{width:100%;height:auto;background:#0d1728;border-radius:8px}
input[type=range]{flex:1;min-width:160px}table{width:100%;border-collapse:collapse}td,th{padding:9px;text-align:left;border-bottom:1px solid #304159}th{color:#a5b7cc;font-weight:500}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,monospace}.scroll{overflow:auto}.teal{color:#59d7c4}.orange{color:#ffba78}
@media(max-width:800px){.grid{grid-template-columns:1fr}main{padding:18px}}
</style><main><div class="eyebrow">ROBORSI / REPRODUCIBLE DECISION SANDBOX</div>
<h1>建议返回时，世界还是原来的世界吗？</h1>
<p>运动学桌面抓取代理 · 相同规则提案、不同等待与复查策略 · 所有控制时间均为虚拟时间</p>
<p class="note">不是 Piper 数字孪生，没有物理接触求解器；没有 GPT / Jev / VLM 调用，也没有训练 RSI。可视化用于观察逻辑、过时建议与等待成本。</p>
<section id="paper-assets" hidden><h2>论文素材与过程归档</h2><p><a href="benchmark.json" download>完整配置、事件与指标 JSON</a> · <a href="process.jsonl.gz" download>全部 episode 的 200 Hz 状态 gzip</a> · <a href="summary.csv" download>结果表 CSV</a> · <a href="manifest.json" download>文件校验清单</a></p><p><a href="summary.svg">可编辑矢量结果表</a> · <a href="README.md">实验说明与复现命令</a></p>
<label>四方法对照视频 <select id="video-scenario"></select></label><video id="video" controls preload="metadata" style="width:100%;max-height:650px;margin-top:16px"></video><p>视频来自本次仿真轨迹，四种方法对齐世界时间，终止后冻结最后状态；没有虚构真机画面。</p></section>
<section><div class="controls"><label>场景 <select id="scenario"></select></label><label>方法 <select id="method"></select></label><span id="seed"></span></div>
<div class="grid"><div><h3>桌面俯视 · m</h3><canvas id="top" width="560" height="340" aria-label="桌面物体与夹爪位置"></canvas></div><div><h3>高度侧视 · m</h3><canvas id="side" width="560" height="340" aria-label="夹爪与物体高度"></canvas></div></div>
<p><span class="teal">● 物体</span>　<span class="orange">＋ 自由 Cartesian 夹爪</span>　蓝色框：篮筐 · 轨迹为当前方法的已播放部分</p>
<div class="controls"><button id="play">播放</button><button id="step">单步</button><input id="time" type="range" min="0" max="8" step="0.005" value="0" aria-label="时间轴"><label>速度 <select id="speed"><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select></label><span id="clock"></span></div>
<p id="state"></p></section>
<div class="grid"><section><h3>此刻的事件</h3><pre id="events"></pre></section><section><h3>当前 episode 结果</h3><pre id="result"></pre></section></div>
<h2>所有种子的配对场景统计</h2><p>每种方法使用相同场景与种子。汇总包含保护停止，不剔除失败；时长均包含成功与失败 episode。</p>
<section class="scroll"><table><thead><tr><th>场景</th><th>方法</th><th>入筐 / 总数</th><th>平均虚拟秒</th><th>过时采纳</th><th>过时丢弃</th></tr></thead><tbody id="summary"></tbody></table></section>
<details><summary>假设、配置与源代码指纹</summary><pre id="metadata"></pre></details></main>
<script type="application/json" id="data">__SIM_DATA__</script><script>
const d=JSON.parse(document.querySelector('#data').textContent),$=s=>document.querySelector(s),names={fixed_plan:'固定粗计划',instant_rules:'即时规则',delayed_unchecked:'延迟建议 / 不复查',delayed_checked:'延迟建议 / 复查版本'},scenes={nominal:'正常',shift:'物体移位',shift_during_wait:'等待期间再移位',occluded_shift:'遮挡与移位',slip:'抬升后滑落',tracking_fault:'跟踪保护'};
function text(tag,value){const n=document.createElement(tag);n.textContent=value;return n}
for(const s of d.config.scenarios){const n=text('option',scenes[s]);n.value=s;$('#scenario').append(n)}
for(const s of d.config.scenarios){const n=text('option',scenes[s]);n.value=s;$('#video-scenario').append(n)}
$('#video-scenario').value='shift_during_wait';function changeVideo(){$('#video').src='videos/'+$('#video-scenario').value+'.mp4'}$('#video-scenario').onchange=changeVideo;if(d.paper_assets){$('#paper-assets').hidden=false;changeVideo()}
for(const m of d.config.methods){const n=text('option',names[m]);n.value=m;$('#method').append(n)}
$('#scenario').value='shift_during_wait';$('#method').value='delayed_checked';let ep,playing=false,previous=0;
function selected(){ep=d.episodes.find(e=>e.scenario===$('#scenario').value&&e.method===$('#method').value&&e.frames.length);$('#time').max=ep.simulated_duration_s;$('#time').value=0;$('#seed').textContent='回放 seed '+ep.seed;const {frames,events,...rest}=ep;$('#result').textContent=JSON.stringify(rest,null,2);draw()}
function draw(){const t=+$('#time').value,points=ep.frames.filter(f=>f.t<=t),frame=points.at(-1)||ep.frames[0];$('#clock').textContent=t.toFixed(3)+' s';$('#state').textContent='阶段：'+frame.phase+' · '+(frame.closed?'夹爪闭合':'夹爪打开');$('#events').textContent=ep.events.filter(e=>e.t<=t).map(e=>JSON.stringify(e)).join('\\n');
for(const kind of ['top','side']){const c=$('#'+kind),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);const xy=p=>[40+(p[0]+.35)/.7*480,kind==='top'?300-(p[1]+.2)/.4*260:300-p[2]/.3*260];ctx.strokeStyle='#223753';ctx.lineWidth=1;for(let i=0;i<7;i++){ctx.beginPath();ctx.moveTo(40+i*80,35);ctx.lineTo(40+i*80,300);ctx.stroke()}ctx.beginPath();ctx.moveTo(40,300);ctx.lineTo(520,300);ctx.stroke();ctx.strokeStyle='#699ce5';const b=xy([.16,.135,.07]),b2=xy([.24,.065,0]);ctx.strokeRect(b[0],b[1],b2[0]-b[0],b2[1]-b[1]);ctx.strokeStyle='#ffba7870';ctx.beginPath();points.forEach((f,i)=>{const p=xy(f.grip);i?ctx.lineTo(...p):ctx.moveTo(...p)});ctx.stroke();const o=xy(frame.object);ctx.fillStyle='#59d7c4';ctx.beginPath();ctx.ellipse(o[0],o[1],10,7,0,0,Math.PI*2);ctx.fill();const g=xy(frame.grip),w=frame.closed?8:17;ctx.strokeStyle='#ffba78';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(g[0]-w,g[1]-12);ctx.lineTo(g[0]-w,g[1]+12);ctx.moveTo(g[0]+w,g[1]-12);ctx.lineTo(g[0]+w,g[1]+12);ctx.moveTo(g[0]-w,g[1]-12);ctx.lineTo(g[0]+w,g[1]-12);ctx.stroke();ctx.fillStyle='#a5b7cc';ctx.font='13px system-ui';ctx.fillText('-0.35',20,325);ctx.fillText('x / m',480,325);ctx.fillText(kind==='top'?'y / m':'z / m',12,20)}}
$('#scenario').onchange=selected;$('#method').onchange=selected;$('#time').oninput=draw;$('#step').onclick=()=>{$('#time').value=Math.min(ep.simulated_duration_s,+$('#time').value+.05);draw()};$('#play').onclick=()=>{playing=!playing;if(playing&&+$('#time').value>=ep.simulated_duration_s)$('#time').value=0;$('#play').textContent=playing?'暂停':'播放'};
function animate(now){if(playing&&previous){$('#time').value=Math.min(ep.simulated_duration_s,+$('#time').value+(now-previous)/1000*+$('#speed').value);draw();if(+$('#time').value>=ep.simulated_duration_s){playing=false;$('#play').textContent='播放'}}previous=now;requestAnimationFrame(animate)}
for(const s of d.summaries){const row=text('tr','');for(const v of [scenes[s.scenario]||'全部',names[s.method],`${s.successes} / ${s.episodes}`,s.mean_simulated_duration_s.toFixed(3),s.stale_adopted,s.stale_discarded])row.append(text('td',v));$('#summary').append(row)}
$('#metadata').textContent=JSON.stringify({limitations:d.limitations,config:d.config,implementation:d.implementation,artifact_sha256:d.artifact_sha256},null,2);selected();requestAnimationFrame(animate);document.body.dataset.loaded='true';
</script></html>"""
