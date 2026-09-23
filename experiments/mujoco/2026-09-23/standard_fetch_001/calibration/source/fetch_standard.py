"""Full-reset Fetch qualification under the installed registered task protocol.

These are fixed-skill baselines, not a result for a learned JEV-style algorithm.
No max_episode_steps override and no clean checkpoint prefix are used.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
import gymnasium as gym
import gymnasium_robotics
import mujoco
import numpy as np
from physics_skills import Controller

TASKS = ['FetchReach-v4', 'FetchPush-v4', 'FetchPickAndPlace-v4', 'FetchSlide-v4']
CONFIGS = [{'name': 'original', 'gain': 1.0, 'close_ticks': 12, 'closed_speed': .25},
           {'name': 'gain15', 'gain': 1.5, 'close_ticks': 12, 'closed_speed': .25},
           {'name': 'gain20_close8', 'gain': 2.0, 'close_ticks': 8, 'closed_speed': .25},
           {'name': 'gain15_close8_fast', 'gain': 1.5, 'close_ticks': 8, 'closed_speed': .50}]


class FixedSkill:
    def __init__(self, task, config):
        self.task, self.config = task, config
        self.base = Controller(task, closed_speed=config['closed_speed'])

    @property
    def stage(self):
        return self.base.stage

    def action(self, grip, obj, goal):
        if (self.task == 'FetchPickAndPlace-v4' and self.base.stage == 2
                and self.base.ticks >= self.config['close_ticks'] - 1):
            self.base.ticks = 11
        action = self.base.action(grip, obj, goal)
        action[:3] = np.clip(action[:3] * self.config['gain'], -1, 1)
        return action


def write(path, x):
    path.write_text(json.dumps(x, indent=2, allow_nan=False))


def episode(env, task, seed, config):
    obs, _ = env.reset(seed=seed)
    controller = FixedSkill(task, config)
    trace = []
    initial = {'qpos': env.unwrapped.data.qpos.tolist(), 'qvel': env.unwrapped.data.qvel.tolist(),
                   'obs': {k: v.tolist() for k, v in obs.items()}}
    assert env.spec.max_episode_steps == 50
    for k in range(env.spec.max_episode_steps):
        grip = obs['observation'][:3]
        obj = obs['achieved_goal']
        action = controller.action(grip, obj, obs['desired_goal'])
        obs, reward, terminated, truncated, info = env.step(action)
        trace.append({'step': k + 1, 't': (k + 1) * .04, 'action': action.tolist(),
                          'qpos': env.unwrapped.data.qpos.tolist(), 'qvel': env.unwrapped.data.qvel.tolist(),
                          'grip': obs['observation'][:3].tolist(), 'object': obs['achieved_goal'].tolist(),
                          'goal': obs['desired_goal'].tolist(), 'stage': controller.stage,
                          'distance': float(np.linalg.norm(obs['achieved_goal'] - obs['desired_goal'])),
                          'reward': float(reward), 'success': bool(info['is_success']),
                          'terminated': bool(terminated), 'truncated': bool(truncated)})
        if terminated or truncated:
            break
    assert len(trace) == 50 and trace[-1]['truncated'] and not trace[-1]['terminated']
    return {'task': task, 'seed': seed, 'config': config, 'initial': initial, 'trace': trace,
                'success': trace[-1]['success'], 'ever_success': any(s['success'] for s in trace),
                'last10_success': all(s['success'] for s in trace[-10:]),
                'final_distance': trace[-1]['distance']}


def worker(items):
    gym.register_envs(gymnasium_robotics)
    envs = {t: gym.make(t) for t in TASKS}
    rows = []
    for task, seed, config, output in items:
        result = episode(envs[task], task, seed, config)
        filename = f"{task}_{seed}_{config['name']}.json.gz"
        with gzip.open(Path(output) / filename, 'wt') as f:
            json.dump(result, f, allow_nan=False)
        rows.append({k: v for k, v in result.items() if k not in ['initial', 'trace']})
    for env in envs.values():
        env.close()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['calibrate', 'evaluate'], required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--selection', type=Path)
    p.add_argument('--episodes', type=int, required=True)
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
    if args.mode == 'evaluate':
        assert args.selection is not None
        selection = json.loads(args.selection.read_text())
    else:
        assert args.selection is None
        selection = None
    args.output.mkdir(parents=True, exist_ok=False)
    traces = args.output / 'traces'
    traces.mkdir()
    start_seed = 2100000 if args.mode == 'calibrate' else 2200000
    protocol = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    'mode': args.mode, 'tasks': TASKS, 'episodes_per_task': args.episodes, 'first_seed': start_seed,
                    'scope': 'Fixed-skill qualification; not learned JEV algorithm evaluation',
                    'horizon': 'registered default: 50 control steps, no override',
                    'primary_metric': 'is_success at the final time-limit step',
                    'secondary_metrics': ['ever_success', 'last10_success', 'final_distance'],
                    'configuration_selection': 'calibration final-success first, then lower mean final distance, then configuration order',
                    'selection_sha256': None if args.selection is None else hashlib.sha256(args.selection.read_bytes()).hexdigest(),
                    'env': {'mujoco': mujoco.__version__, 'gymnasium': gym.__version__, 'robotics': gymnasium_robotics.__version__}}
    write(args.output / 'protocol.json', protocol)
    items = [(task, start_seed + i, config, str(traces))
             for task in TASKS for i in range(args.episodes)
             for config in (CONFIGS if selection is None else [selection[task]])]
    started = time.perf_counter()
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for batch in pool.map(worker, [items[i:i+10] for i in range(0, len(items), 10)]):
            rows.extend(batch)
    write(args.output / 'rows.json', rows)
    summaries, selected = [], {}
    for task in TASKS:
        configs = CONFIGS if selection is None else [selection[task]]
        candidates = []
        for config in configs:
            rr = [r for r in rows if r['task'] == task and r['config'] == config]
            summary = dict(task=task, config=config, episodes=len(rr),
                           **{k:float(np.mean([r[k] for r in rr])) for k in
                              ['success', 'ever_success', 'last10_success', 'final_distance']})
            candidates.append(summary)
        summaries.extend(candidates)
        selected[task] = min(candidates, key=lambda r:(-r['success'], r['final_distance']))['config']
    write(args.output / 'summary.json', {'summaries': summaries, 'wall_s': time.perf_counter() - started,
                                            'episodes': len(rows), 'control_steps': sum(50 for r in rows)})
    if selection is None:
        write(args.output / 'selection.json', selected)
    print(json.dumps({'summaries': summaries, 'episodes': len(rows), 'wall_s': time.perf_counter() - started}), flush=True)


if __name__ == '__main__':
    main()
