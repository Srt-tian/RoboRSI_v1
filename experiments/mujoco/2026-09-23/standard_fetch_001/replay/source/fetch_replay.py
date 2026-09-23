"""Fixed-index full-reset Fetch replay, including successful and failed cases."""
import argparse
import gzip
import json
import os
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
import gymnasium as gym
import gymnasium_robotics
from fetch_robustness import METHODS
from fetch_standard import TASKS, write
from physics_queue_replay import render_branch


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evaluation', type=Path, required=True)
    p.add_argument('--pilot', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    gym.register_envs(gymnasium_robotics)
    jobs = []
    # Fixed first two held-out seeds per task, never selected by success.
    for task in TASKS:
        for seed in [2200000, 2200001]:
            matches = list((args.evaluation / 'traces').glob(f'{task}_{seed}_*.json.gz'))
            assert len(matches) == 1
            jobs.append(('evaluation', matches[0]))
    # A fixed pilot parent per task/regime, all five methods side by side.
    for task, seed in [('FetchPush-v4', 2300000), ('FetchPickAndPlace-v4', 2301000)]:
        for regime in ['jitter', 'drift', 'occlusion']:
            for method in METHODS:
                jobs.append(('pilot', args.pilot / 'traces' / f'{task}_{seed}_{regime}_{method}.json.gz'))
    report = []
    for split, path in jobs:
        with gzip.open(path, 'rt') as f:
            result = json.load(f)
        env = gym.make(result['task'], render_mode='rgb_array', width=640, height=480)
        try:
            env.reset(seed=result['seed'])
            name = path.name.removesuffix('.json.gz') + '.mp4'
            audit = render_branch(env, result, args.output / name)
            report.append({'file': name, 'split': split,
                           **{k:v for k,v in result.items() if k not in ['initial', 'trace']}, **audit})
        finally:
            env.close()
    write(args.output / 'replays.json', {
        'semantics': 'Archived integrated-state playback; FK checked at Gym observation cache timestamp. Not a dynamics rerun.',
        'selection': 'First two held-out skill seeds per task; first pilot seed per task, all perturbed regimes and fixed methods.',
        'replays': report})
    print(json.dumps({'videos': len(report), 'frames': sum(r['frames'] for r in report),
                      'max_time_aligned_fk_error_m': max(r['max_time_aligned_fk_error_m'] for r in report)}), flush=True)


if __name__ == '__main__':
    main()
