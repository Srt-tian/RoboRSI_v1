"""Record immutable benchmark decisions without render-induced state changes."""
import argparse
import gzip
import json
from pathlib import Path
import gymnasium as gym
import gymnasium_robotics
import imageio.v2 as imageio
import mujoco
from physics_judge import rollout


def main():
    p=argparse.ArgumentParser();p.add_argument('--study',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);gym.register_envs(gymnasium_robotics);checks=[]
    for split in ['test','delay']:
        rows=json.loads((a.study/(split+'.json')).read_text());choices=json.loads((a.study/(split+'_decisions.json')).read_text())['choices']
        for idx in [0,1]:
            row=rows[idx];env=gym.make(row['context']['task'],max_episode_steps=150,render_mode='rgb_array',width=640,height=480)
            backup=mujoco.MjData(env.unwrapped.model)
            original=env.render
            def safe_render():
                mujoco.mj_copyData(backup,env.unwrapped.model,env.unwrapped.data)
                try:return original()
                finally:mujoco.mj_copyData(env.unwrapped.data,env.unwrapped.model,backup)
            env.render=safe_render
            for method in ['always_keep','always_accurate','judge_seed11']:
                choice=choices[method][idx];stem=f'{split}_{idx}_{method}'
                with imageio.get_writer(a.output/(stem+'.mp4'),fps=25) as writer:result=rollout(env,row['context'],choice,record=True,writer=writer)
                exact=result['success']==row['success'][choice] and abs(result['duration_s']-row['duration'][choice])<1e-10
                check={'video':stem+'.mp4','success_matches':result['success']==row['success'][choice],'duration_error_s':result['duration_s']-row['duration'][choice],'exact_outcome_and_duration':exact}
                checks.append(check)
                with gzip.open(a.output/(stem+'.json.gz'),'wt') as f:json.dump({'context':row['context'],'method':method,'choice':choice,**result},f)
                print(json.dumps(check),flush=True)
            env.close()
    (a.output/'verification.json').write_text(json.dumps(checks,indent=2))
    assert all(c['exact_outcome_and_duration'] for c in checks), 'render replay mismatch remains'


if __name__=='__main__':main()
