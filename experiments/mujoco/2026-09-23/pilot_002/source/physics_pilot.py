"""MuJoCo Fetch controller qualification. No learned judge in this pilot."""
import argparse
import gzip
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
import gymnasium as gym
import gymnasium_robotics
import imageio.v2 as imageio
import mujoco
import numpy as np


class Controller:
    def __init__(self, task):
        self.task = task
        self.stage = 0
        self.ticks = 0

    def action(self, grip, obj, goal):
        self.ticks += 1
        if self.task == 'FetchReach-v4':
            return np.r_[np.clip((goal-grip)*8, -1, 1), 0.0]
        opening = 1.0
        if self.task == 'FetchPickAndPlace-v4':
            targets = [obj+np.array([0,0,.10]),obj+np.array([0,0,-.022]),obj+np.array([0,0,-.022]),obj+np.array([0,0,.16]),goal]
            target = targets[min(self.stage,4)]
            if self.stage >= 2:
                opening = -1.0
            if self.stage == 3:
                target = np.r_[grip[:2], max(goal[2],.60)]
            if self.stage in (0,1) and np.linalg.norm(grip-target) < .009:
                self.stage += 1; self.ticks = 0
            elif self.stage == 2 and self.ticks >= 12:
                self.stage = 3; self.ticks = 0
            elif self.stage == 3 and grip[2] > max(goal[2],.60)-.015:
                self.stage = 4; self.ticks = 0
        else:
            direction = goal[:2]-obj[:2]
            direction /= max(np.linalg.norm(direction),1e-6)
            behind = obj[:2]-.065*direction
            if self.stage == 0:
                target=np.r_[behind,obj[2]+.10]
            elif self.stage == 1:
                target=np.r_[behind,obj[2]]
            else:
                target=np.r_[goal[:2],obj[2]]
                opening=-1.0
            if self.stage < 2 and np.linalg.norm(grip-target) < .012:
                self.stage += 1
        return np.r_[np.clip((target-grip)*6,-.35 if opening < 0 else -1,.35 if opening < 0 else 1),opening]


def episode(env, task, seed, *, delay=0, refresh=1, writer=None):
    obs, _ = env.reset(seed=seed)
    controller=Controller(task)
    history=[]; trace=[]; successes=[]
    held=None
    started=time.perf_counter()
    for k in range(env.spec.max_episode_steps):
        raw=obs['observation']
        history.append(raw[3:6].copy() if len(raw)>10 else obs['achieved_goal'].copy())
        if held is None or k%refresh == 0:
            held=history[max(0,k-delay)].copy()
        action=controller.action(raw[:3],held,obs['desired_goal'])
        obs,reward,terminated,truncated,info=env.step(action)
        ok=bool(info['is_success']);successes.append(ok)
        trace.append({'step':k+1,'t':float(env.unwrapped.data.time),'action':action.tolist(),
                      'grip':obs['observation'][:3].tolist(),'object':obs['achieved_goal'].tolist(),
                      'perceived_object':held.tolist(),'goal':obs['desired_goal'].tolist(),
                      'qpos':env.unwrapped.data.qpos.tolist(),'qvel':env.unwrapped.data.qvel.tolist(),
                      'contacts':int(env.unwrapped.data.ncon),'stage':controller.stage,'success':ok})
        if writer is not None:
            writer.append_data(env.render())
        if terminated or truncated: break
    return {'task':task,'seed':seed,'delay_steps':delay,'refresh_steps':refresh,
            'ever_success':any(successes),'final_success':successes[-1],
            'sustained_last10':all(successes[-10:]),'steps':len(trace),
            'wall_s':time.perf_counter()-started,'trace':trace}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',type=int,default=10);p.add_argument('--start-seed',type=int,default=0)
    p.add_argument('--horizon',type=int,default=150);p.add_argument('--delay',type=int,default=0)
    p.add_argument('--refresh',type=int,default=1);p.add_argument('--video',action='store_true')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    gym.register_envs(gymnasium_robotics)
    rows=[]
    for task in ('FetchReach-v4','FetchPush-v4','FetchPickAndPlace-v4'):
        env=gym.make(task,render_mode='rgb_array' if args.video else None,width=640,height=480,max_episode_steps=args.horizon)
        for seed in range(args.start_seed,args.start_seed+args.seeds):
            writer=imageio.get_writer(args.output/(task+'.mp4'),fps=25) if args.video and seed==args.start_seed else None
            try:
                result=episode(env,task,seed,delay=args.delay,refresh=args.refresh,writer=writer)
            finally:
                if writer:writer.close()
            with gzip.open(args.output/(task+'_'+str(seed)+'.json.gz'),'wt') as f:json.dump(result,f)
            row={k:v for k,v in result.items() if k!='trace'};rows.append(row)
            print(json.dumps(row),flush=True)
        env.close()
    summary={'scope':'controller qualification; privileged object observations; no learned Jev',
             'mujoco':mujoco.__version__,'gymnasium':gym.__version__,'robotics':gymnasium_robotics.__version__,
             'physics_dt':.002,'control_dt':.04,'horizon':args.horizon,
             'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'episodes':rows,'metrics':{task:{key:sum(r[key] for r in rows if r['task']==task)/args.seeds for key in ['ever_success','final_success','sustained_last10']} for task in sorted(set(r['task'] for r in rows))}}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary['metrics']),flush=True)


if __name__=='__main__':main()
