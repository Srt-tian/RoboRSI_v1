(async () => {
  const base = '../experiments/mujoco/2026-09-23/queue_evidence_001/';
  const section = document.createElement('section');
  section.id = 'queue';
  section.innerHTML = `<div class="eyebrow">最新机制检验 · 保留负结果</div>
    <h2>动作队列能决定怎样使用延迟观测吗？</h2>
    <p>同一个物理检查点 → 三个已提交动作队列 → 三种证据使用方式。先检验机制，再决定是否训练。</p>
    <p id="queueVerdict" class="note">正在读取已封存结果…</p>
    <div class="cards" id="queueCards"></div>
    <p id="queueControlNote"></p>
    <div class="row"><label>任务 <select id="queueTask"><option value="all">两个任务</option><option value="FetchPush-v4">Push</option><option value="FetchPickAndPlace-v4">Pick-and-Place</option></select></label><span class="small">每个父场景有 3 个队列；这些分支不是独立样本。</span></div>
    <div id="queueTable" class="scroll"></div>
    <details open><summary>每个父场景的队列信息价值</summary><canvas id="queueGap" width="1200" height="250"></canvas><p class="small">纵轴：知道队列后，理想选择器可减少的代价。理想选择器访问执行结果，仅用于判断学习是否还有空间。原先导门槛使用三个原始路由；补充基线不改写先导判定。</p></details>
    <details open><summary>相同场景下，队列与证据方式如何改变结果？</summary><div class="row"><label>父场景 <select id="queueCase"></select></label><span id="queueCaseInfo" class="small"></span></div><div id="queueMatrix" class="scroll"></div></details>
    <details open><summary>固定场景的归档状态视频</summary><div class="row"><label>场景 <select id="queueVideoCase"><option value="0">0 · Push</option><option value="1">1 · Pick</option><option value="4">4 · Push</option><option value="5">5 · Pick</option></select></label><button id="queuePlay">同步播放</button><button id="queuePause">暂停</button><label>速度 <select id="queueSpeed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label><input id="queueTime" aria-label="同步视频时间" type="range" min="0" max="6" step="0.04" value="0"><span id="queueTimeLabel" class="small">0.00 s</span></div><div id="queueVideos" class="grid"></div><p class="small">四个固定开发场景，均展示原幅提议队列；共 16 段。播放保存的 qpos/qvel，未重跑动力学。短分支结束后停在最后一帧。</p></details>
    <p class="note">范围：两个 Fetch 任务、手写技能、单次路由选择、合成固定偏置。没有新增模型训练。补充基线为事后诊断，99.6% 不能解释为新学习方法或一般视觉任务的成功率。</p>
    <div class="row"><a href="${base}pilot/summary.json">冻结先导结果</a><a href="${base}control/summary.json">事后对照结果</a><a href="${base}control/audit.json">全部分支审计</a><a href="../docs/QUEUE_EVIDENCE_STUDY.md">设计、反证与下一步</a><a href="../docs/manuscript/draft_cn.pdf">中文手稿 PDF</a></div>`;
  document.querySelector('main > nav').after(section);
  const link = document.createElement('a'); link.href = '#queue'; link.textContent = '新：队列机制反证'; document.querySelector('nav').prepend(link);
  const $ = id => document.getElementById(id);
  const routeNames = ['当前粗观测','延迟精确观测','按末端位移校正','传感器差分校正（事后）'];
  const queueNames = {hold:'保持位置',half_proposal:'半幅提议',proposal:'原幅提议'};
  let pilot, control, rows, controls, replays;
  const mean = values => values.reduce((a,b)=>a+b,0)/values.length;
  function createTable(rows) {
    const t = document.createElement('table');
    rows.forEach((row,i)=>{const tr=document.createElement('tr');row.forEach(value=>{const cell=document.createElement(i?'td':'th');cell.textContent=value;tr.append(cell)});t.append(tr)});
    return t;
  }
  function table() {
    const task=$('queueTask').value, rr=rows.filter(r=>task==='all'||r.context.task===task), cc=controls.filter(r=>task==='all'||r.context.task===task);
    const cells=[['证据使用方式','父场景 / 队列分支','成功率','综合代价 ↓']];
    routeNames.forEach((name,i)=>cells.push([name,rr.length/3+' / '+rr.length,(100*mean(i<3?rr.map(r=>Number(r.success[i])):cc.map(r=>Number(r.success)))).toFixed(2)+'%',mean(i<3?rr.map(r=>r.cost[i]):cc.map(r=>r.cost)).toFixed(5)]));
    $('queueTable').replaceChildren(createTable(cells));
  }
  function gapPlot() {
    const canvas=$('queueGap'),ctx=canvas.getContext('2d'),values=pilot.pairs.map(p=>p.queue_blind_oracle_gap),max=Math.max(...values,.01)*1.15;
    ctx.clearRect(0,0,1200,250);ctx.font='14px system-ui';
    for(let i=0;i<=4;i++){const y=25+i*44;ctx.fillStyle='#52647b';ctx.fillText((max*(1-i/4)).toFixed(3),8,y+5);ctx.strokeStyle='#e1e8ef';ctx.beginPath();ctx.moveTo(70,y);ctx.lineTo(1155,y);ctx.stroke()}
    values.forEach((v,i)=>{const x=75+i*1080/(values.length-1),y=201-v/max*176;ctx.fillStyle=pilot.pairs[i].material_flip?'#bb6b25':'#4e8fbc';ctx.beginPath();ctx.arc(x,y,3.5,0,Math.PI*2);ctx.fill()});
    ctx.fillStyle='#52647b';ctx.fillText('父场景编号 0 → 89；橙色为明显最优路由变化',70,233);
  }
  function matrix() {
    const index=+$('queueCase').value, rr=rows.filter(r=>r.context.index===index),cc=controls.filter(r=>r.context.index===index),c=rr[0].context;
    $('queueCaseInfo').textContent=c.task+' · 阶段 '+rr[0].stage+' · 队列 '+(c.queue_steps*.04).toFixed(2)+' s · 精确流延迟 '+(c.delay*.04).toFixed(2)+' s';
    const cells=[['已提交队列',...routeNames]];
    rr.forEach(r=>{const extra=cc.find(x=>x.queue===r.queue),cost=[...r.cost,extra.cost],success=[...r.success,extra.success];cells.push([queueNames[r.queue],...cost.map((x,i)=>x.toFixed(4)+' / '+(success[i]?'成功':'失败'))])});
    $('queueMatrix').replaceChildren(createTable(cells));
  }
  function videos() {
    const index=+$('queueVideoCase').value,box=$('queueVideos'); box.querySelectorAll('video').forEach(v=>v.pause());box.replaceChildren();$('queueTime').value=0;$('queueTimeLabel').textContent='0.00 s';
    replays.replays.filter(r=>r.index===index).forEach((r,i)=>{const div=document.createElement('div'),v=document.createElement('video'),p=document.createElement('p');v.controls=true;v.preload='metadata';v.src=base+'replay/'+r.file;v.playbackRate=+$('queueSpeed').value;p.textContent=routeNames[i]+' · '+(r.success?'成功':'失败')+' · 代价 '+r.cost.toFixed(4);div.append(v,p);box.append(div)});
  }
  try {
    async function get(name){const r=await fetch(base+name);if(!r.ok)throw Error(name);return r.json()}
    [pilot,control,rows,controls,replays]=await Promise.all(['pilot/summary.json','control/summary.json','pilot/rows.json','control/rows.json','replay/replays.json'].map(get));
    $('queueVerdict').textContent='未通过预设训练门槛：队列信息的理想平均收益 '+pilot.queue_blind_oracle_gap.toFixed(5)+' < 0.005；明显变化 '+pilot.material_flip_parents+'/90 < 10。保留负结果，停止本版本的模型训练。';
    $('queueCards').innerHTML=[[90,'独立父场景'],[1080,'已审计物理分支'],[79443,'已审计控制步'],[0,'新增训练模型']].map(([n,l])=>'<div class="card"><div class="value">'+n.toLocaleString()+'</div>'+l+'</div>').join('');
    $('queueControlNote').textContent='补充检查：固定偏置可通过时间差分抵消。无需学习的校正获得 269/270 分支成功；相对直接使用延迟精确观测，代价差 '+control.difference_to_precise_delayed.toFixed(5)+'，父场景 bootstrap 区间 ['+control.difference_parent_bootstrap_95.map(x=>x.toFixed(5)).join(', ')+']。这是开发场景的事后诊断。';
    pilot.pairs.forEach((p,i)=>{const option=document.createElement('option');option.value=i;option.textContent=i+' · '+p.task.replace('Fetch','').replace('-v4','');$('queueCase').append(option)});
    table();gapPlot();matrix();videos();$('queueTask').onchange=table;$('queueCase').onchange=matrix;$('queueVideoCase').onchange=videos;
    $('queuePlay').onclick=()=>{$('queueVideos').querySelectorAll('video').forEach(v=>{v.currentTime=Math.min(+$('queueTime').value,Number.isFinite(v.duration)?Math.max(0,v.duration-.01):0);v.play().catch(()=>{})})};
    $('queuePause').onclick=()=>{$('queueVideos').querySelectorAll('video').forEach(v=>v.pause())};
    $('queueSpeed').onchange=()=>{$('queueVideos').querySelectorAll('video').forEach(v=>{v.playbackRate=+$('queueSpeed').value})};
    $('queueTime').oninput=()=>{$('queueTimeLabel').textContent=(+$('queueTime').value).toFixed(2)+' s';$('queueVideos').querySelectorAll('video').forEach(v=>{if(Number.isFinite(v.duration))v.currentTime=Math.min(+$('queueTime').value,Math.max(0,v.duration-.01))})};
    // Follow decoded media time. Repeated wall-clock seeks can prevent decoding
    // from progressing when a local server is still buffering a video.
    setInterval(()=>{const playing=[...$('queueVideos').querySelectorAll('video')].filter(v=>!v.paused&&!v.ended&&!v.seeking);if(playing.length){const master=playing.reduce((a,b)=>a.duration>=b.duration?a:b);$('queueTime').value=master.currentTime;$('queueTimeLabel').textContent=master.currentTime.toFixed(2)+' s'}},100);
    if(location.hash==='#queue')section.scrollIntoView({block:'start'});
  } catch(e) { $('queueVerdict').textContent='实验数据同步中：'+e.message; }
})();
