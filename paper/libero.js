/* Training-data evidence only: these videos are not closed-loop policy results. */
(() => {
  const base = '../experiments/datasets/2026-09-24/libero_001/';
  const section = document.createElement('section'); section.id = 'libero';
  section.innerHTML = `<h2>LIBERO · 数据与长程任务接入</h2>
    <p class="note">下方是已有训练演示及其真实记录。新的 JEV / RSI 策略尚未在 LIBERO 完成闭环评测；演示视频不能用作算法成功率。</p>
    <div id="liberoCards" class="cards"></div>
    <p id="liberoAudit" class="small">正在加载远端审计结果…</p>
    <div class="row"><label>固定演示 <select id="liberoTask"></select></label><label>速度 <select id="liberoSpeed"><option value=".5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label><button id="liberoStep">下一帧</button><span id="liberoTime"></span></div>
    <video id="liberoVideo" controls muted playsinline preload="metadata" style="max-width:100%;width:768px;background:#e8eef3;border-radius:12px"></video>
    <p id="liberoCaption" class="small"></p>
    <canvas id="liberoAction" width="1200" height="240"></canvas>
    <p class="small">曲线为数据中的 7 维原始 action；坐标系、旋转和夹爪约定仍需与仿真转换代码核对。10 Hz 是文件标注频率，不据此推定底层控制频率。左右画面分别为 image / image2，未擅自命名固定相机与腕部相机。</p>
    <details><summary>40 个任务的实际演示数量与数据边界</summary><p>各任务 29–50 条，共 1,693 条。不是统一每任务 50 条的完整版本。数据只声明 train 划分；算法选择与成功率评测需要另外冻结仿真初始状态、干预预算和测试种子。</p><div class="scroll"><table id="liberoTasks"></table></div></details>
    <details><summary>可追溯记录</summary><p>全部文件计算 SHA-256；所有动作行、演示边界与视频头经过核验。完整视频解码仅覆盖这里预先指定的三个演示。原始视频保留在远端。</p><div class="row"><a href="${base}audit.json">审计结果</a><a href="${base}source_files.json">原始文件校验清单</a><a href="${base}manifest.json">页面缓存校验清单</a><a href="../docs/plans/2026-09-24-libero-data.md">数据协议与下一步</a></div></details>`;
  const anchor = document.getElementById('standard') || document.querySelector('nav');
  anchor.after(section);
  const link = document.createElement('a'); link.href = '#libero'; link.textContent = 'LIBERO 数据'; document.querySelector('nav').prepend(link);
  const $ = id => document.getElementById(id), video = $('liberoVideo');
  const colors = ['#087f78','#436eb3','#b96b37','#9658ad','#517a53','#b85d60','#172b45'];
  let previews = [], trace = null, generation = 0;
  function draw() {
    const c = $('liberoAction'), ctx = c.getContext('2d'); ctx.clearRect(0,0,c.width,c.height);
    if (!trace) return;
    const n = trace.action.length, step = Math.min(n - 1, Math.max(0,Math.floor(video.currentTime * trace.fps)));
    const x = i => 50 + 1090 * i / Math.max(1,n - 1), y = a => 128 - 76 * a;
    ctx.strokeStyle = '#d8e1ea'; ctx.beginPath(); ctx.moveTo(50,y(0)); ctx.lineTo(1140,y(0)); ctx.stroke();
    for (let d=0;d<7;d++) { ctx.strokeStyle = colors[d]; ctx.lineWidth=1.5; ctx.beginPath(); trace.action.forEach((a,i)=>i?ctx.lineTo(x(i),y(a[d])):ctx.moveTo(x(i),y(a[d])));ctx.stroke();ctx.fillStyle=colors[d];ctx.font='15px system-ui';ctx.fillText('a'+d+' = '+trace.action[step][d].toFixed(3),45+d*163,22); }
    ctx.strokeStyle='#172b45';ctx.beginPath();ctx.moveTo(x(step),40);ctx.lineTo(x(step),214);ctx.stroke();
    ctx.fillStyle='#586b83';ctx.fillText('原始 action · 第 '+step+' 帧 / '+(n-1),50,237);
    $('liberoTime').textContent=video.currentTime.toFixed(1)+' s / '+(n/trace.fps).toFixed(1)+' s';
  }
  async function select() {
    const current = ++generation, p = previews[Number($('liberoTask').value)]; if (!p) return;
    video.pause(); trace=null; video.src=base+p.video; video.playbackRate=Number($('liberoSpeed').value);
    $('liberoCaption').textContent='训练演示 · Episode '+p.episode_id+' · '+p.frames+' 帧 · 按任务固定选择首条，未按观看结果筛选';
    const response=await fetch(base+p.trace);if(!response.ok)throw Error(response.status);
    const data=await response.json();if(current!==generation)return;trace=data;draw();
  }
  $('liberoTask').onchange=()=>select().catch(fail);
  $('liberoSpeed').onchange=()=>{video.playbackRate=Number($('liberoSpeed').value)};
  $('liberoStep').onclick=()=>{if(!trace)return;video.pause();video.currentTime=Math.min((trace.action.length-1)/trace.fps,(Math.floor(video.currentTime*trace.fps+1e-5)+1)/trace.fps)};
  video.addEventListener('timeupdate',draw);video.addEventListener('seeked',draw);
  function animate(){if(!video.paused)draw();requestAnimationFrame(animate)}animate();
  function fail(error){$('liberoAudit').textContent='数据加载失败：'+error}
  Promise.all(['audit.json','previews.json'].map(p=>fetch(base+p).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}))).then(async([audit,items])=>{
    if(!audit.passed)throw Error('审计未通过');previews=items;
    $('liberoCards').replaceChildren(...[[audit.task_count,'任务'],[audit.episodes.toLocaleString(),'已有训练演示'],[audit.frames.toLocaleString(),'动作帧'],[audit.video_files,'已核验视频头']].map(([value,label])=>{const card=document.createElement('div');card.className='card';const v=document.createElement('div');v.className='value';v.textContent=value;card.append(v,label);return card}));
    $('liberoAudit').textContent='审计通过 · '+audit.files+' 个文件 · '+(audit.bytes/1e9).toFixed(2)+' GB · '+audit.action_dim+' 维动作 / '+audit.state_dim+' 维状态 · '+audit.fps+' Hz · 代码 '+audit.source_commit.slice(0,8);
    $('liberoTask').replaceChildren(...items.map((p,i)=>{const o=document.createElement('option');o.value=i;o.textContent=p.task;return o}));
    const rows=[['任务 ID','语言任务','演示数'],...audit.tasks.map(t=>[t.id,t.name,t.episodes])];
    $('liberoTasks').replaceChildren(...rows.map((r,i)=>{const tr=document.createElement('tr');r.forEach(v=>{const td=document.createElement(i?'td':'th');td.textContent=v;tr.append(td)});return tr}));
    await select();
  }).catch(fail);
})();
