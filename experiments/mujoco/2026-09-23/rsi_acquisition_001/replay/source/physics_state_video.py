"""Render archived physical states; no dynamics rerun is presented as original."""
import argparse
import gzip
import json
import os
from pathlib import Path
os.environ.setdefault('MUJOCO_GL','egl')
import gymnasium as gym
import gymnasium_robotics
import imageio.v2 as imageio
import mujoco
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    gym.register_envs(gymnasium_robotics)
    report=[]
    for split in ['test','delay']:
        rows=json.loads((args.run/(split+'.json')).read_text())
        for index in [0,1,4,5,9]:
            row=rows[index]
            source=args.run/'traces'/f'{split}_{index:05d}.json.gz'
            with gzip.open(source,'rt') as f:
                record=json.load(f)
            env=gym.make(row['context']['task'],max_episode_steps=300,render_mode='rgb_array',width=640,height=480)
            try:
                env.reset(seed=row['context']['seed'])
                for choice,name in enumerate(['continue','stop_refresh','async_refresh']):
                    branch=record['branches'][choice]
                    stem=f'{split}_{index}_{name}'
                    errors=[]
                    raw_offsets=[]
                    cache_age=0.0 if env.unwrapped.block_gripper else float(env.unwrapped.model.opt.timestep)
                    assert env.unwrapped.model.opt.integrator == mujoco.mjtIntegrator.mjINT_EULER
                    with imageio.get_writer(args.output/(stem+'.mp4'),fps=25) as writer:
                        for state in branch['trace']:
                            env.unwrapped.data.qpos[:]=state['qpos']
                            env.unwrapped.data.qvel[:]=state['qvel']
                            mujoco.mj_forward(env.unwrapped.model,env.unwrapped.data)
                            obs=env.unwrapped._get_obs()
                            raw_offsets.append(max(float(np.max(np.abs(obs['observation'][:3]-state['grip']))),
                                                   float(np.max(np.abs(obs['achieved_goal']-state['object'])))))
                            # Fetch Pick leaves derived site poses cached before the final
                            # 2 ms integration. Push refreshes them in _step_callback.
                            # Validate at the observation timestamp; render original qpos.
                            if cache_age:
                                previous=np.asarray(state['qpos'],dtype=np.float64).copy()
                                mujoco.mj_integratePos(env.unwrapped.model,previous,
                                                      np.asarray(state['qvel'],dtype=np.float64),-cache_age)
                                env.unwrapped.data.qpos[:]=previous
                                mujoco.mj_forward(env.unwrapped.model,env.unwrapped.data)
                                obs=env.unwrapped._get_obs()
                            error=max(float(np.max(np.abs(obs['observation'][:3]-state['grip']))),
                                      float(np.max(np.abs(obs['achieved_goal']-state['object']))))
                            assert error<1e-9,(stem,error)
                            errors.append(error)
                            env.unwrapped.data.qpos[:]=state['qpos']
                            mujoco.mj_forward(env.unwrapped.model,env.unwrapped.data)
                            writer.append_data(env.render())
                            np.testing.assert_array_equal(env.unwrapped.data.qpos,state['qpos'])
                    report.append(dict(stem=stem,frames=len(errors),max_time_aligned_fk_error_m=max(errors),
                                       max_raw_api_offset_m=max(raw_offsets),observation_cache_age_s=cache_age,
                                       source_file=source.name,success=branch['success'],duration_s=branch['duration_s'],
                                       semantics='Archived qpos/qvel playback; no dynamics rerun or image synthesis'))
                (args.output/f'{split}_{index}.json.gz').write_bytes(source.read_bytes())
            finally:
                env.close()
    (args.output/'replays.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(videos=len(report),max_time_aligned_fk_error_m=max(r['max_time_aligned_fk_error_m'] for r in report),semantics='archived state playback; API cache timing explicitly aligned')))


if __name__=='__main__':
    main()
