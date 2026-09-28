/* Current development evidence, separated from historical learned results. */
(() => {
  const base='../experiments/deployable/2026-09-28/run_001/';
  const section=document.createElement('section'); section.id='deployable';
  section.innerHTML=`<div class="eyebrow">2026-09-28 · 面向真机</div><h2>实测观测 → 可执行候选 → 判断与修正</h2>
  <p>当前迭代先核对输入真实性与候选可执行性。新的视觉判断器、诊断策略和 RSI 采集机制尚未得到算法有效性验证，本轮没有新的真机运动。</p>
  <div class="grid"><div><h3>执行侧 · 已实现离线接口</h3><p>相机帧与时间戳、实测关节和夹爪 → 指令/测量分离 → 有界 IK 与几何筛选 → 200 Hz 平滑轨迹。真机执行仍需当次场景和反馈检查。</p></div><div><h3>判断与 RSI · 待实验支持</h3><p>有限候选评分 → 必要时补观测或小幅诊断 → 执行结果回流。研究重点是“哪条额外证据会改变动作”，并与直接 Q、固定纠错和随机采集比较。</p></div></div>
  <p id="deployStatus" class="note">正在读取本轮封存结果…</p><div id="deployCards" class="cards"></div>
  <h3>双臂仿真 · 指令和实测夹爪同步查看</h3><div class="row"><select id="deployNative"></select><select id="deploySide"><option value="left">左夹爪</option><option value="right">右夹爪</option></select><button id="deployLoad">加载实际回放</button><span id="deployNativeInfo" class="small"></span></div>
  <div class="grid" style="margin-top:16px"><div><video id="deployVideo" controls muted playsinline preload="none" style="width:100%"></video><input id="deployFrame" aria-label="逐帧查看" type="range" min="0" value="0" style="width:100%"><p id="deployFrameInfo" class="small"></p></div><div><canvas id="deployPlot" width="1100" height="390"></canvas><p class="small">青色：第一根夹指实测坐标；橙色虚线：驱动目标，单位 mm。这里是 URDF 关节坐标，不是标定后的夹爪开口。差值可能包含接触和跟踪滞后，不能独立证明抓取成功。</p></div></div>
  <h3>Piper · 历史状态上的小幅动作检查</h3><p id="piperAuditInfo"></p><div class="row"><label>历史反馈帧 <select id="piperFrame"></select></label><span id="piperFrameInfo" class="small"></span></div><div class="scroll"><table id="piperCandidateTable"></table></div><p class="small">保持夹爪和另一臂不变；使用真实 URDF 和历史参数逐点检查平滑输出。相关历史帧不能当作独立试验，几何筛选不是完整场景碰撞检查。</p>
  <h3>固定开发预检 · 抓偏后是否需要不同修正</h3><p id="pilotInfo"></p><div class="scroll"><table id="pilotTable"></table></div><p id="pilotGate" class="note"></p>
  <div class="row"><select id="pilotReplay"></select><button id="pilotLoad">加载分支回放</button><span id="pilotReplayInfo" class="small"></span></div><video id="pilotVideo" controls muted playsinline preload="none" style="max-width:680px;width:100%;margin-top:12px"></video>
  <p class="small">只评首次抓取、抬高和保持，自定义子任务不等于完整 RoboTwin 交接任务。原生专家提供初始提案，纠错候选仅使用固定相对位移。种子固定为 0；3 个偏差条件不构成独立测试集。异常、失败和配对不成立均保留。</p>
  <details><summary>源码、协议与复核资料</summary><div class="row"><a href="${base}summary.json">本轮摘要</a><a href="${base}manifest.json">文件校验清单</a><a href="${base}piper/audit.json">逐候选检查</a><a href="${base}pilot/results.json">分支原始结果</a><a href="../docs/plans/2026-09-28-deployable-recovery.md">研究假设与最近邻工作</a><a href="https://github.com/Srt-tian/RoboRSI_v1/tree/research/deployable-recovery">实验源码</a></div></details>`;
  document.querySelector('nav').after(section);
  const nav=document.createElement('a');nav.href='#deployable';nav.textContent='最新 · 真机准备';document.querySelector('nav').prepend(nav);
  const topNav=document.querySelector('nav');
  new ResizeObserver(()=>{section.style.scrollMarginTop=(topNav.offsetHeight+12)+'px'}).observe(topNav);
  const el=id=>document.getElementById(id);
  const json=async path=>{const r=await fetch(base+path);if(!r.ok)throw Error(path+' HTTP '+r.status);return r.json()};
  let summary,frames=[],audit,videoURL=null,pilotURL=null;
  const titles={lift:'双臂抬锅',handover:'交接积木'};
  const names={probe_up_20mm:'上移 20 mm',shift_x_plus_15mm:'X +15 mm',shift_x_minus_15mm:'X −15 mm',shift_y_plus_15mm:'Y +15 mm',shift_y_minus_15mm:'Y −15 mm'};
  function table(target,rows){el(target).replaceChildren();rows.forEach((row,i)=>{const tr=document.createElement('tr');row.forEach(v=>{const cell=document.createElement(i?'td':'th');cell.textContent=v;tr.append(cell)});el(target).append(tr)})}
  function plot(){
    const c=el('deployPlot'),ctx=c.getContext('2d'),side=el('deploySide').value;
    ctx.clearRect(0,0,c.width,c.height);ctx.font='20px system-ui';ctx.fillStyle='#586b83';
    if(!frames.length||!frames[0].measured){ctx.fillText('该清理回归未启用新版实测分组；请选择交接积木。',35,90);return}
    const values=frames.map(f=>({t:f.simulation_time_s,m:1000*f.measured.arms[side].gripper.joints.position[0],c:1000*f.commands[side].gripper_joint_position[0]}));
    const lo=Math.min(...values.flatMap(v=>[v.m,v.c]))-3,hi=Math.max(...values.flatMap(v=>[v.m,v.c]))+3,maxT=values.at(-1).t||1;
    const X=t=>75+t/maxT*970,Y=v=>330-(v-lo)/(hi-lo)*280;
    ctx.strokeStyle='#dce4ee';ctx.setLineDash([]);
    for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4,y=Y(v);ctx.beginPath();ctx.moveTo(75,y);ctx.lineTo(1045,y);ctx.stroke();ctx.fillText(v.toFixed(0),12,y+6)}
    for(const [key,color,dash] of [['m','#087f78',[]],['c','#cf7b21',[10,6]]]){ctx.strokeStyle=color;ctx.lineWidth=3;ctx.setLineDash(dash);ctx.beginPath();values.forEach((v,i)=>i?ctx.lineTo(X(v.t),Y(v[key])):ctx.moveTo(X(v.t),Y(v[key])));ctx.stroke()}
    const index=Math.min(values.length-1,Math.max(0,+el('deployFrame').value)),v=values[index];ctx.setLineDash([]);ctx.strokeStyle='#496cc7';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(X(v.t),35);ctx.lineTo(X(v.t),340);ctx.stroke();ctx.fillStyle='#586b83';ctx.fillText('物理时间 / s',890,375);ctx.fillText('0',75,365);ctx.fillText(maxT.toFixed(2),980,365);
    el('deployFrameInfo').textContent=`帧 ${index} · 物理步 ${frames[index].physics_step} · ${v.t.toFixed(3)} s · 实测 ${v.m.toFixed(2)} mm / 目标 ${v.c.toFixed(2)} mm`;
  }
  async function selectNative(){
    const row=summary.native.find(r=>r.id===el('deployNative').value);el('deployVideo').pause();el('deployVideo').removeAttribute('src');el('deployVideo').load();
    if(videoURL){URL.revokeObjectURL(videoURL);videoURL=null}el('deployVideo').poster=base+row.directory+'/final.png';el('deployLoad').disabled=false;el('deployLoad').textContent='加载实际回放';
    el('deployNativeInfo').textContent=`任务${row.task_success?'成功':'失败'} · 子进程退出 ${row.exit_code} · ${row.physics_steps.toLocaleString()} 步 / ${row.simulation_time_s.toFixed(3)} s`;
    frames=await json(row.directory+'/frames.json');el('deployFrame').max=frames.length-1;el('deployFrame').value=0;plot();
  }
  async function loadVideo(button,video,path){button.disabled=true;button.textContent='加载中…';try{const r=await fetch(base+path);if(!r.ok)throw Error(r.status);const url=URL.createObjectURL(await r.blob());video.preload='auto';video.src=url;video.load();button.textContent='已加载 · 可播放和拖动';return url}catch(e){button.disabled=false;button.textContent='加载失败：'+e;return null}}
  function piper(){const row=audit.rows[+el('piperFrame').value];el('piperFrameInfo').textContent='TCP: '+row.tcp_xyz.map(v=>(v*1000).toFixed(1)).join(', ')+' mm · 历史状态';table('piperCandidateTable',[['候选','检查结论','时长 / s','200 Hz 点数','说明'],...row.candidates.map(c=>[names[c.id],c.admitted?'通过离线检查':'拒绝',c.admitted?c.timing.duration_s.toFixed(3):'—',c.admitted?c.targets:'—',c.admitted?'保留夹爪；仍无执行授权':c.reason])])}
  el('deploySide').onchange=plot;
  el('deployNative').onchange=()=>selectNative().catch(error=>{el('deployNativeInfo').textContent=String(error)});
  el('deployFrame').oninput=()=>{if(el('deployVideo').src)el('deployVideo').currentTime=+el('deployFrame').value/5;plot()};
  el('deployVideo').ontimeupdate=()=>{el('deployFrame').value=Math.min(frames.length-1,Math.floor(el('deployVideo').currentTime*5));plot()};
  el('deployLoad').onclick=async()=>{const row=summary.native.find(r=>r.id===el('deployNative').value);videoURL=await loadVideo(el('deployLoad'),el('deployVideo'),row.directory+'/head.mp4')};
  el('piperFrame').onchange=piper;
  function replayRow(){const value=el('pilotReplay').value;return value.startsWith('prefix:')?summary.prefix_check.rows.find(r=>r.id===+value.split(':')[1]):summary.pilot.rows.find(r=>r.id===+value)}
  function selectPilot(){const row=replayRow();el('pilotVideo').pause();el('pilotVideo').removeAttribute('src');el('pilotVideo').load();if(pilotURL){URL.revokeObjectURL(pilotURL);pilotURL=null}el('pilotVideo').poster=base+row.directory+'/final.png';el('pilotLoad').disabled=!row.video;el('pilotLoad').textContent=row.video?'加载分支回放':'无可用视频';el('pilotReplayInfo').textContent=`偏差 ${row.error_x_m*1000} mm → 修正 ${row.repair_x_m*1000} mm · ${row.pilot_success===null?'运行异常':row.pilot_success?'子任务成功':'子任务失败'} · 退出 ${row.process_exit}`}
  el('pilotReplay').onchange=selectPilot;
  el('pilotLoad').onclick=async()=>{const row=replayRow();pilotURL=await loadVideo(el('pilotLoad'),el('pilotVideo'),row.directory+'/head.mp4')};
  (async()=>{
    summary=await json('summary.json');audit=await json('piper/audit.json');
    el('deployStatus').textContent=summary.conclusion;
    el('deployCards').innerHTML=[[summary.native.filter(r=>r.exit_code===0).length+'/2','原生任务正常退出'],[audit.admitted_count+'/'+audit.candidate_count,'历史候选通过离线检查'],[(summary.pilot.rows.length+summary.prefix_check.rows.length)+'/12','开发分支记录（9 + 3）'],['0','本轮真机执行']].map(([v,l])=>`<div class="card"><div class="value">${v}</div>${l}</div>`).join('');
    summary.native.forEach(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=titles[row.id];el('deployNative').append(option)});el('deployNative').value='handover';await selectNative();
    el('piperAuditInfo').textContent=`${audit.frame_count} 个固定历史帧，${audit.candidate_count} 个候选：${audit.admitted_count} 个通过，${audit.candidate_count-audit.admitted_count} 个拒绝。每个通过候选的全部输出点均经过几何检查；这是可执行性预检，不是抓取成功率。`;
    audit.rows.forEach((row,i)=>{const o=document.createElement('option');o.value=i;o.textContent=row.source_index;el('piperFrame').append(o)});piper();
    const pilot=summary.pilot;el('pilotInfo').textContent='每条分支上限 2,500 个物理步（250 Hz）；开夹、修正、抬高和保持均计入预算。表格显示子任务结果与实际用步。';
    table('pilotTable',[['初始 X 偏差','继续','重夹 X −20 mm','重夹 X +20 mm'],...[-0.04,0,0.04].map(error=>[error*1000+' mm',...[0,-0.02,0.02].map(repair=>{const r=pilot.rows.find(r=>r.error_x_m===error&&r.repair_x_m===repair);return !r?'未执行':r.pilot_success===null?'异常':`${r.pilot_success?'成功':'失败'} · ${r.physics_steps} 步`})])]);
    el('pilotGate').textContent=pilot.conclusion+(summary.prefix_replay_qualified?' 追加 3 条冻结前缀验证已通过：均为 1,003 步，前缀摘要和分叉物体姿态一致；仍然全部失败。':' 追加的冻结前缀验证尚未通过。');
    pilot.rows.forEach(row=>{const o=document.createElement('option');o.value=row.id;o.textContent=`分支 ${row.id} · 偏差 ${row.error_x_m*1000} / 修正 ${row.repair_x_m*1000} mm`;el('pilotReplay').append(o)});if(pilot.rows.length)selectPilot();
    summary.prefix_check.rows.forEach(row=>{const o=document.createElement('option');o.value='prefix:'+row.id;o.textContent=`冻结前缀验证 ${row.id} · 修正 ${row.repair_x_m*1000} mm`;el('pilotReplay').append(o)});
  })().catch(e=>{el('deployStatus').textContent='本轮数据尚未完整同步：'+e});
})();
