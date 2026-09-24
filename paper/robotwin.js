/* Native expert infrastructure evidence; retain task and process outcomes separately. */
(() => {
  const base='../experiments/robotwin/2026-09-24/qualification_001/';
  const section=document.createElement('section');section.id='robotwin';
  section.innerHTML=`<h2>RoboTwin · 双臂仿真链路验证</h2><p>预先固定种子 0，运行原生专家的交接积木与双臂抬锅。视频来自执行时的 SAPIEN 渲染，物理步频 250 Hz，视频采样 5 Hz。</p><p class="note">两次仿真内部均判定任务成功，但退出阶段存在异常。抬锅子进程收到 SIGSEGV；交接命令退出码为 255，未单独捕获子进程退出码。当前未通过运行稳定性门槛，尚未扩大评测。这两个开发案例不是 JEV / RSI 成功率结果。</p><div id="robotwinExamples" class="grid"></div><details><summary>范围与完整记录</summary><p>原生专家使用特权状态与运动规划，不属于学习策略。没有更换种子重试至成功。全部逐物理步 qpos/qvel、控制目标及规划轨迹保留在执行主机；本页缓存关键结果、实际视频与文件校验清单。控制目标与测量关节状态分别记录。</p><div class="row"><a href="${base}index.json">任务结果与退出码</a><a href="${base}manifest.json">页面缓存校验清单</a><a href="../docs/plans/2026-09-24-robotwin-status.md">环境、异常与后续检验</a></div></details><p id="robotwinStatus" class="small">正在加载仿真记录…</p>`;
  (document.getElementById('libero')||document.getElementById('standard')||document.querySelector('nav')).after(section);
  const link=document.createElement('a');link.href='#robotwin';link.textContent='RoboTwin 仿真';document.querySelector('nav').prepend(link);
  const titles={handover:'交接积木',lift_pot:'双臂抬锅'};
  fetch(base+'index.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(index=>{
    for(const row of index.rows){
      const card=document.createElement('div'),h=document.createElement('h3'),info=document.createElement('p'),video=document.createElement('video'),button=document.createElement('button'),caption=document.createElement('p');
      h.textContent=titles[row.id]+' · 固定种子 '+row.seed;
      info.textContent='仿真任务判定：'+(row.task_success?'成功':'失败')+' · '+row.physics_steps.toLocaleString()+' 物理步 · '+row.simulation_time_s.toFixed(3)+' s';
      video.controls=true;video.muted=true;video.playsInline=true;video.preload='none';video.poster=base+row.final_image;video.style.width='100%';
      button.textContent='加载实际回放';button.onclick=async()=>{button.disabled=true;button.textContent='加载中…';try{const r=await fetch(base+row.video);if(!r.ok)throw Error(r.status);video.src=URL.createObjectURL(await r.blob());video.load();button.textContent='已加载 · 可播放和拖动'}catch(e){button.disabled=false;button.textContent='加载失败：'+e}};
      caption.className='small';caption.textContent='原生专家 · '+row.frames+' 帧 · 退出码 '+row.exit_code+' · 封面为最终渲染帧';
      card.append(h,info,video,button,caption);document.getElementById('robotwinExamples').append(card);
    }
    document.getElementById('robotwinStatus').textContent='已核对 5,310 行物理记录和 107 帧视频索引。任务结果与非零退出码同时保留。';
  }).catch(e=>{document.getElementById('robotwinStatus').textContent='加载失败：'+e});
})();
