(async () => {
  const base = '../experiments/mujoco/2026-09-23/rsi_acquisition_001/';
  const section = document.createElement('section');
  section.id = 'rsi';
  section.innerHTML = `<h2>RSI 实验 · 错误记录能带来更有效的补数据吗？</h2>
    <p>旧训练记录 → 交叉拟合找错误 → 等预算采样 → 更新小判断器 → 全新场景测试。</p>
    <p id="rsiStatus" class="note">读取实验进度…</p>
    <p>随机采样、模型分歧、历史反例各新增 180 个场景。另保留冻结模型与只重训旧数据的对照。每次更新都从相同模型开始，使用相同训练步数。</p>
    <div id="rsiResults" hidden><p id="rsiPrimary" class="note"></p>
      <div class="row"><label>分布 <select id="rsiSplit"><option value="test">新 IID 测试</option><option value="delay">新长延迟测试</option></select></label>
      <label>任务 <select id="rsiTask"><option value="all">全部任务</option><option value="FetchPush-v4">Push</option><option value="FetchPickAndPlace-v4">Pick-and-Place</option></select></label></div>
      <div id="rsiMetrics" class="scroll"></div>
      <details open><summary>补数据选中了哪些场景？</summary><div class="row"><label>方法 <select id="rsiSampler"><option value="counterexample">历史反例</option><option value="disagreement">模型分歧</option><option value="random">随机采样</option></select></label><span>浅灰为候选池，蓝色为 Push，橙色为 Pick；实心点为选中场景。</span></div><canvas id="rsiPool" width="1200" height="330"></canvas><p id="rsiPoolInfo" class="small"></p></details>
      <details><summary>全部更新曲线</summary><canvas id="rsiCurves" width="1200" height="300"></canvas><p class="small">验证集平均代价越低越好；每种方法 3 个训练种子。第 0 步为冻结模型，允许保留原模型。</p></details>
      <div id="rsiReplay"></div>
      <p class="small">6,402 参数，结构化数值输入；没有图像编码器或 GPT 调用。只有一轮采样、一次采样随机种子和两类任务。区间按场景计算，不能代表采样种子总体或真机表现。</p>
      <div class="row"><a href="${base}results.json">完整结果</a><a href="${base}selection.json">采样选择与分数</a><a href="${base}oof.json">交叉拟合错误</a><a href="${base}frozen_protocol.json">冻结协议</a><a href="../docs/plans/2026-09-23-rsi-acquisition.md">实验设计</a></div>
    </div>`;
  document.querySelector('main > nav').after(section);
  const link = document.createElement('a'); link.href = '#rsi'; link.textContent = '新：RSI 补数据'; document.querySelector('nav').prepend(link);
  const $ = id => document.getElementById(id);
  const titles = {frozen:'冻结原模型', replay_only:'只重训旧数据', random:'随机补数据', disagreement:'模型分歧补数据', counterexample:'历史反例补数据'};
  const colors = ['#74849a','#598bc3','#c68a25','#008779'];
  const methods = ['replay_only','random','disagreement','counterexample'];
  let result, selection, pool, trials, loaded = false;
  async function get(name) { const r = await fetch(base+name,{cache:'no-store'}); if(!r.ok) throw Error(name+' 尚未同步'); return r.json(); }
  function table() {
    const s = result.summaries.find(v=>v.split===$('rsiSplit').value), task=$('rsiTask').value;
    const rows = [['方法','独立场景数','成功率','综合代价 ↓','剩余用时 / s']];
    for (const method of Object.keys(titles)) {
      const v = [11,22,33].map(seed=>s.methods[method+'_'+seed][task]);
      const mean = k=>v.reduce((a,b)=>a+b[k],0)/v.length;
      rows.push([titles[method],v[0].contexts,(100*mean('success_rate')).toFixed(1)+'%',mean('mean_cost').toFixed(4),mean('duration_s').toFixed(2)]);
    }
    for (const method of ['continue','stop_refresh','async_refresh','task_phase_lookup']) {
      const v=s.methods[method][task]; rows.push([method,v.contexts,(100*v.success_rate).toFixed(1)+'%',v.mean_cost.toFixed(4),v.duration_s.toFixed(2)]);
    }
    const t=document.createElement('table'); rows.forEach((r,i)=>{const tr=document.createElement('tr');r.forEach(value=>{const c=document.createElement(i?'td':'th');c.textContent=value;tr.append(c)});t.append(tr)});$('rsiMetrics').replaceChildren(t);
  }
  function drawPool() {
    const c=$('rsiPool'),ctx=c.getContext('2d'),method=$('rsiSampler').value, chosen=new Set(selection.indices[method]);
    ctx.clearRect(0,0,c.width,c.height);ctx.font='14px system-ui';ctx.fillStyle='#52647b';ctx.fillText('观测噪声标准差 / m',10,22);ctx.fillText('刷新延迟 / s',1050,316);
    for(let k=0;k<5;k++){const y=45+k*50;ctx.strokeStyle='#e0e7ef';ctx.beginPath();ctx.moveTo(80,y);ctx.lineTo(1150,y);ctx.stroke();ctx.fillStyle='#52647b';ctx.fillText((.04-k*.01).toFixed(2),22,y+5)}
    for(let k=0;k<=7;k++){const x=80+k*.2/1.4*1070;ctx.fillText((k*.2).toFixed(1),x,275)}
    const draw=(r,i,selected)=>{const x=80+r.x[3]/1.4*1070,y=45+(1-r.x[1]/.04)*200;ctx.globalAlpha=selected?.85:.25;ctx.fillStyle=selected?(r.x[0]?'#c1751b':'#356bc0'):'#8f9dad';ctx.beginPath();ctx.arc(x,y,selected?4:2,0,Math.PI*2);ctx.fill()};
    pool.forEach((r,i)=>draw(r,i,false));pool.forEach((r,i)=>{if(chosen.has(i))draw(r,i,true)});ctx.globalAlpha=1;
    $('rsiPoolInfo').textContent='1,200 个无结果标签的候选检查点；选中 '+chosen.size+' 个。三种方法按任务和延迟区间保持相同预算；分数使用采样前可见信息。';
  }
  function curves() {
    const c=$('rsiCurves'),ctx=c.getContext('2d'),values=trials.flatMap(t=>t.curve.map(v=>v.validation_cost)),lo=Math.min(...values),hi=Math.max(...values);
    ctx.clearRect(0,0,c.width,c.height);ctx.font='14px system-ui';ctx.fillStyle='#52647b';
    for(let k=0;k<4;k++){const y=30+k*60;ctx.fillText((hi-(hi-lo)*k/3).toFixed(3),5,y+5);ctx.strokeStyle='#e0e7ef';ctx.beginPath();ctx.moveTo(70,y);ctx.lineTo(1160,y);ctx.stroke()}
    trials.forEach((t,i)=>{ctx.strokeStyle=colors[methods.indexOf(t.method)];ctx.setLineDash(i%3===0?[]:i%3===1?[6,3]:[2,3]);ctx.beginPath();t.curve.forEach((v,k)=>{const x=70+v.step/400*1090,y=30+(hi-v.validation_cost)/Math.max(1e-8,hi-lo)*180;k?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()});ctx.setLineDash([]);methods.forEach((m,i)=>{ctx.fillStyle=colors[i];ctx.fillText(titles[m],100+280*i,265)});
  }
  async function refresh() {
    try {
      const status=await get('status.json'); $('rsiStatus').textContent=status.message;
      if(status.status!=='complete'||loaded)return;
      [result,selection,pool,trials]=await Promise.all(['results.json','selection.json','pool.json','update_trials.json'].map(get));
      loaded=true; $('rsiResults').hidden=false;const p=result.primary;
      const verdict=p.ci95[1]<0?'本轮反例采样优于随机；仍需独立重复。':p.ci95[0]>0?'本轮反例采样劣于随机，保留负结果。':'本轮尚未证明反例采样比随机采样更有效。';
      $('rsiPrimary').textContent=verdict+' 主要对照代价差 '+p.mean.toFixed(5)+'，95% 区间 ['+p.ci95.map(x=>x.toFixed(5)).join(', ')+']；600 个独立测试场景，三个固定模型种子取均值。';
      table();drawPool();curves();$('rsiSplit').onchange=table;$('rsiTask').onchange=table;$('rsiSampler').onchange=drawPool;
      if(status.videos?.length){const grid=document.createElement('div');grid.className='grid';for(const file of status.videos){const box=document.createElement('div'),v=document.createElement('video'),p=document.createElement('p');v.controls=true;v.preload='metadata';v.src=base+file;p.textContent=file;box.append(v,p);grid.append(box)}const h=document.createElement('h3');h.textContent='预先固定场景的归档状态回放（不重新仿真）';$('rsiReplay').append(h,grid)}
      if(location.hash==='#rsi')section.scrollIntoView({block:'start'});
    }catch(e){$('rsiStatus').textContent='实验数据同步中：'+e.message}
  }
  await refresh();const timer=setInterval(()=>{if(loaded)clearInterval(timer);else refresh()},30000);
})();
