/* Audited full-reset Fetch qualification and a separately labelled sensor pilot. */
(() => {
  const base = '../experiments/mujoco/2026-09-23/standard_fetch_001/';
  const labels = {raw_fast:'原始观测',sensor_delta:'时间差分校正',kalman_smooth:'平稳滤波',kalman_reactive:'快速响应滤波',phase_rule:'阶段规则'};
  const colors = ['#b85d60','#c48b32','#087f78','#436eb3','#9658ad'];
  const methods = Object.keys(labels);
  const section = document.createElement('section'); section.id = 'standard';
  section.innerHTML = `<h2>标准任务 · 完整回合与感知扰动</h2>
    <p>原版 Fetch-v4，正常 reset、默认 50 步（2 秒），以最后一步的成功判定为主指标。没有截取接近成功的起点，也没有延长时间。</p>
    <div class="cards"><div class="card"><div class="value">400</div>技能留出评测回合</div><div class="card"><div class="value">480</div>感知扰动开发回合</div><div class="card"><div class="value">60,000</div>已审计控制步 · 含校准</div><div class="card"><div class="value">38</div>固定索引状态回放</div></div>
    <p class="note">这里评测的是固定底层技能与五种状态估计基线，新增 JEV 判断模型数量为 0。Slide 的低成功率是待解决的基线问题。扰动试验只用于开发，尚未产生算法留出测试结果。</p>
    <div class="scroll"><table id="standardTable"></table></div>
    <p class="small">每个任务 100 个留出种子；95% 区间使用 Wilson 方法。技能参数只从另外 20 个校准种子选择。全过程曾成功和末尾连续 10 步成功均为辅助指标。</p>
    <h3>感知扰动对照 · 相同初始状态配对</h3>
    <div class="row"><select id="standardTask"><option>FetchPush-v4</option><option>FetchPickAndPlace-v4</option></select><select id="standardRegime"><option value="jitter">帧噪声 · 延迟 200 ms</option><option value="drift">偏差漂移 · 延迟 320 ms</option><option value="occlusion">合成丢帧 · 延迟 320 ms</option><option value="clean">零噪声检查</option></select></div>
    <canvas id="standardPlot" width="1200" height="225"></canvas><div class="scroll"><table id="standardRobustTable"></table></div>
    <p class="small">每个任务只有 12 个独立父场景，每个父场景重复四种传感条件、五种方法。不同分支不是额外独立样本。丢帧由传感器掩码模拟，不是图像遮挡；低位置误差不自动等于高任务成功率。</p>
    <details open><summary>完整回合视频与逐步误差 · 页内查看</summary>
      <div class="row"><select id="standardReplaySplit"><option value="evaluation">技能留出回放</option><option value="pilot">感知扰动配对回放</option></select><select id="standardReplayTask"></select><select id="standardReplaySeed"><option value="0">固定种子 0</option><option value="1">固定种子 1</option></select><select id="standardReplayRegime"><option value="jitter">帧噪声</option><option value="drift">偏差漂移</option><option value="occlusion">合成丢帧</option></select></div>
      <div class="row"><button id="standardPlay">播放</button><button id="standardStep">下一步</button><input id="standardTime" type="range" min="0" max="1.96" step=".04" value="0" style="flex:1"><span id="standardTimeLabel">0.00 s</span><select id="standardSpeed"><option value=".5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></div>
      <div id="standardVideos" class="grid"></div><canvas id="standardTrace" width="1200" height="240"></canvas>
      <p class="small">视频来自原始 qpos/qvel 的状态播放，并非重新运行策略。各视频 50 帧；首帧是第 1 步执行后（仿真 0.04 s）。FK 已按 Gym 观测缓存的时间戳对齐核验；最大误差小于 2×10⁻¹⁶ m。案例按固定种子展示，包含失败。</p>
    </details>
    <details><summary>Slide 的 SAC + HER 训练先导 · 保留负结果</summary><p>单个训练种子，25 万环境转移、4 个并行环境。Actor 76,040 参数，双 Critic 合计 150,530 参数。使用完整特权状态，不属于 JEV 判断网络。11 个检查点在同一组 50 个验证场景上均为 0% 最终成功；尚未开启留出测试，不能据此判断该算法充分训练后的能力。</p><img loading="lazy" src="../docs/assets/standard_fetch_readiness.png" alt="固定技能留出结果及 SAC HER 验证曲线"><div class="row"><a href="../docs/assets/standard_fetch_readiness.pdf">可导出 PDF 图</a><a href="../experiments/mujoco/2026-09-23/slide_her_001/curve.json">训练验证曲线</a><a href="../experiments/mujoco/2026-09-23/slide_her_001/manifest.json">SAC 记录校验清单</a></div></details>
    <details><summary>前沿性复核与困难任务接入</summary><p>Q-Planning 已覆盖“冻结策略 + 小 Q 评估器 + 从失败自改进”；RAYA 已研究可恢复性驱动的提前干预。两者均列为最近工作，不将已有组合改名当作创新。候选方向仍需通过强基线、因果输入约束与等预算 RSI 消融。</p><p>LIBERO-Long、RoboTwin 和恢复任务正在接入，当前没有这些困难任务的新方法闭环成绩。</p><a href="../docs/plans/2026-09-23-frontier-gates.md">完整排重记录、候选假设与否决条件</a></details>
    <details><summary>审计与原始记录</summary><div class="row"><a href="${base}audit.json">1,200 回合完整审计</a><a href="${base}evaluation/rows.json">400 回合留出结果</a><a href="${base}pilot/rows.json">480 回合扰动结果</a><a href="${base}manifest.json">导出校验清单</a></div></details><p id="standardStatus" class="small">正在加载已封存结果…</p>`;
  document.querySelector('nav').after(section);
  const link = document.createElement('a'); link.href='#standard'; link.textContent='标准任务'; document.querySelector('nav').prepend(link);
  const $=id=>document.getElementById(id);
  let evaluation, pilot, replays, videos=[], traces=[], generation=0;
  const short = t=>t.replace('Fetch','').replace('-v4','');
  const percent = x=>(100*x).toFixed(1)+'%';
  function table(id, rows) { $(id).replaceChildren(...rows.map((row,i)=>{const tr=document.createElement('tr');row.forEach(value=>{const cell=document.createElement(i?'td':'th');cell.textContent=value;tr.append(cell)});return tr})); }
  function wilson(p,n) {const z=1.96,d=1+z*z/n,m=(p+z*z/(2*n))/d,s=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [m-s,m+s].map(percent).join(' – ')}
  function plotPilot() {
    if(!pilot)return;
    const rows=pilot.summaries.filter(r=>r.task===$('standardTask').value&&r.regime===$('standardRegime').value);
    table('standardRobustTable',[['方法','最终成功 / 12','成功率','位置 RMSE / mm','终点距离 / mm'],...rows.map(r=>[labels[r.method],Math.round(r.success*r.episodes)+' / '+r.episodes,percent(r.success),(1000*r.estimation_rmse_m).toFixed(1),(1000*r.final_distance).toFixed(1)])]);
    const c=$('standardPlot'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);
    rows.forEach((r,i)=>{const y=12+i*40;ctx.fillStyle='#586b83';ctx.font='16px system-ui';ctx.fillText(labels[r.method],14,y+22);ctx.fillStyle='#edf1f5';ctx.fillRect(195,y,860,28);ctx.fillStyle=colors[i];ctx.fillRect(195,y,860*r.success,28);ctx.fillStyle='#172b45';ctx.fillText(percent(r.success),1070,y+22)});
  }
  function pause() {videos.forEach(v=>v.pause());$('standardPlay').textContent='播放'}
  function scrub(t) {videos.forEach(v=>{if(v.readyState>0)v.currentTime=Math.min(t,Math.max(0,v.duration-.04))});$('standardTime').value=t;$('standardTimeLabel').textContent=t.toFixed(2)+' s';drawTrace(t)}
  function drawTrace(t) {
    const c=$('standardTrace'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);
    if(!traces.length)return;
    const ymax=Math.max(.05,...traces.flatMap(r=>r.trace.map(s=>s.distance)));
    ctx.fillStyle='#586b83';ctx.font='15px system-ui';ctx.fillText('目标距离 / mm（不同颜色对应视频；虚线为 50 mm 阈值）',12,22);
    const X=i=>70+i/49*1070,Y=d=>202-d/ymax*150;
    ctx.strokeStyle='#b8c7d5';ctx.setLineDash([5,5]);ctx.beginPath();ctx.moveTo(70,Y(.05));ctx.lineTo(1140,Y(.05));ctx.stroke();ctx.setLineDash([]);
    traces.forEach((r,j)=>{ctx.strokeStyle=colors[methods.indexOf(r.method)]||colors[0];ctx.lineWidth=2;ctx.beginPath();r.trace.forEach((s,i)=>i?ctx.lineTo(X(i),Y(s.distance)):ctx.moveTo(X(i),Y(s.distance)));ctx.stroke()});
    const index=Math.min(49,Math.round(t/.04));ctx.strokeStyle='#172b45';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(X(index),35);ctx.lineTo(X(index),212);ctx.stroke();ctx.fillStyle='#586b83';ctx.fillText((1000*ymax).toFixed(0),12,58);ctx.fillText('0',36,208);ctx.fillText('控制步 '+(index+1)+' / 50',70,233);
  }
  function setupReplay() {
    const isPilot=$('standardReplaySplit').value==='pilot';pause();
    const tasks=isPilot?['FetchPush-v4','FetchPickAndPlace-v4']:['FetchReach-v4','FetchPush-v4','FetchPickAndPlace-v4','FetchSlide-v4'];
    const old=$('standardReplayTask').value;$('standardReplayTask').replaceChildren(...tasks.map(t=>{const o=document.createElement('option');o.value=t;o.textContent=short(t);return o}));
    if(tasks.includes(old))$('standardReplayTask').value=old;
    $('standardReplaySeed').hidden=isPilot;$('standardReplayRegime').hidden=!isPilot;loadReplay();
  }
  async function loadReplay() {
    if(!replays)return;const current=++generation;pause();traces=[];videos=[];$('standardVideos').replaceChildren();
    const split=$('standardReplaySplit').value,task=$('standardReplayTask').value;
    const seed=split==='evaluation'?2200000+Number($('standardReplaySeed').value):(task==='FetchPush-v4'?2300000:2301000);
    const rows=replays.replays.filter(r=>r.split===split&&r.task===task&&r.seed===seed&&(split==='evaluation'||r.regime===$('standardReplayRegime').value));
    rows.forEach(r=>{const card=document.createElement('div'),v=document.createElement('video'),p=document.createElement('p');v.src=base+'replay/'+r.file;v.controls=true;v.preload='metadata';v.muted=true;v.playsInline=true;v.playbackRate=Number($('standardSpeed').value);p.textContent=(labels[r.method]||short(r.task))+' · '+(r.success?'最终成功':'最终失败')+' · 终点 '+(r.final_distance*1000).toFixed(1)+' mm';card.append(v,p);$('standardVideos').append(card);videos.push(v)});
    try {const fetched=await Promise.all(rows.map(async r=>{const response=await fetch(base+split+'/traces/'+r.file.replace('.mp4','.json.gz'));if(!response.ok)throw Error(response.status);return new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json()}));if(current!==generation)return;traces=fetched;scrub(0)}catch(e){$('standardStatus').textContent='回放记录加载失败：'+e}
  }
  $('standardTask').onchange=plotPilot;$('standardRegime').onchange=plotPilot;
  $('standardReplaySplit').onchange=setupReplay;
  ['standardReplayTask','standardReplaySeed','standardReplayRegime'].forEach(id=>$(id).onchange=loadReplay);
  $('standardTime').oninput=()=>{pause();scrub(Number($('standardTime').value))};
  $('standardStep').onclick=()=>{pause();scrub(Math.min(1.96,Number($('standardTime').value)+.04))};
  $('standardSpeed').onchange=()=>videos.forEach(v=>v.playbackRate=Number($('standardSpeed').value));
  $('standardPlay').onclick=async()=>{if(!videos.length)return;if(!videos[0].paused){pause();return}if(videos[0].ended||videos[0].currentTime>=1.96)scrub(0);await Promise.all(videos.map(v=>v.play().catch(()=>{})));$('standardPlay').textContent='暂停'};
  function tick(){if(videos[0]&&!videos[0].paused){const t=videos[0].currentTime;$('standardTime').value=t;$('standardTimeLabel').textContent=t.toFixed(2)+' s';drawTrace(t)}requestAnimationFrame(tick)}tick();
  Promise.all(['evaluation/summary.json','pilot/summary.json','replay/replays.json'].map(p=>fetch(base+p).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}))).then(([e,p,r])=>{evaluation=e;pilot=p;replays=r;
    table('standardTable',[['任务','最终成功 / 100','成功率 · 95% CI','过程中曾成功','末尾 10 步均成功','终点距离 / mm'],...evaluation.summaries.map(r=>[short(r.task),Math.round(r.success*r.episodes)+' / '+r.episodes,percent(r.success)+' · '+wilson(r.success,r.episodes),percent(r.ever_success),percent(r.last10_success),(1000*r.final_distance).toFixed(1)])]);
    plotPilot();setupReplay();$('standardStatus').textContent='完整审计通过：320 校准 + 400 留出 + 480 开发回合。完整轨迹封存在执行主机；本机只保存指标、校验清单和固定案例。';
  }).catch(e=>{$('standardStatus').textContent='加载失败：'+e});
})();
