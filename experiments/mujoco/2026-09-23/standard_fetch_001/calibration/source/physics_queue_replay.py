"""Replay fixed pilot indices from archived qpos; never rerun dynamics."""
import argparse
import gzip
import json
import os
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
import gymnasium as gym
import gymnasium_robotics
import imageio.v2 as imageio
import mujoco
import numpy as np
from physics_queue_evidence import ROUTES


def render_branch(env, result, path):
    errors, offsets = [], []
    cache_age = 0.0 if env.unwrapped.block_gripper else float(env.unwrapped.model.opt.timestep)
    assert env.unwrapped.model.opt.integrator == mujoco.mjtIntegrator.mjINT_EULER
    data, model = env.unwrapped.data, env.unwrapped.model
    with imageio.get_writer(path, fps=25) as writer:
        for state in result['trace']:
            data.qpos[:] = state['qpos']
            data.qvel[:] = state['qvel']
            mujoco.mj_forward(model, data)
            obs = env.unwrapped._get_obs()
            offsets.append(max(float(np.max(np.abs(obs['observation'][:3] - state['grip']))),
                               float(np.max(np.abs(obs['achieved_goal'] - state['object'])))))
            if cache_age:
                previous = np.asarray(state['qpos']).copy()
                mujoco.mj_integratePos(model, previous, np.asarray(state['qvel']), -cache_age)
                data.qpos[:] = previous
                mujoco.mj_forward(model, data)
                obs = env.unwrapped._get_obs()
            error = max(float(np.max(np.abs(obs['observation'][:3] - state['grip']))),
                        float(np.max(np.abs(obs['achieved_goal'] - state['object']))))
            assert error < 1e-9, (path.name, error)
            errors.append(error)
            data.qpos[:] = state['qpos']
            mujoco.mj_forward(model, data)
            writer.append_data(env.render())
            np.testing.assert_array_equal(data.qpos, state['qpos'])
    return {'frames': len(errors), 'max_time_aligned_fk_error_m': max(errors),
                'max_raw_api_offset_m': max(offsets), 'observation_cache_age_s': cache_age}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pilot', type=Path, required=True)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    gym.register_envs(gymnasium_robotics)
    report = []
    for index in [0, 1, 4, 5]:
        filename = f'pilot_{index:05d}.json.gz'
        with gzip.open(args.pilot / 'traces' / filename, 'rt') as f:
            record = json.load(f)
        with gzip.open(args.control / 'traces' / filename, 'rt') as f:
            control = json.load(f)
        c = record['context']
        env = gym.make(c['task'], max_episode_steps=300, render_mode='rgb_array', width=640, height=480)
        try:
            env.reset(seed=c['seed'])
            branches = record['variants'][2]['branches'] + [control['variants'][2]['branch']]
            for route, result in zip(ROUTES + ['sensor_delta_control'], branches):
                filename = f'pilot_{index}_proposal_{route}.mp4'
                audit = render_branch(env, result, args.output / filename)
                report.append(dict(file=filename, index=index, task=c['task'], queue='proposal',
                                   route=route, success=result['success'], cost=result['cost'], **audit))
        finally:
            env.close()
    (args.output / 'replays.json').write_text(json.dumps({
        'semantics': 'Archived state playback, not a dynamics rerun. Four fixed development indices.',
        'replays': report}, indent=2))
    print(json.dumps({'videos': len(report), 'max_fk_error': max(x['max_time_aligned_fk_error_m'] for x in report)}))


if __name__ == '__main__':
    main()
