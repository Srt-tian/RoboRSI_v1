"""Full-reset standard Fetch tasks with separately labelled sensor perturbations.

Five executable estimation baselines share sensor history and fixed skills.
This collector does not claim to evaluate a newly learned judgment policy.
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
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import gymnasium as gym
import gymnasium_robotics
import mujoco
import numpy as np
from fetch_sensors import ESTIMATORS, REGIMES, EstimatorBank, SensorTape
from fetch_standard import FixedSkill, write

TASKS = ['FetchPush-v4', 'FetchPickAndPlace-v4']
METHODS = ESTIMATORS + ['phase_rule']
START_SEEDS = {'pilot': 2300000, 'train': 2400000, 'validation': 2500000,
                   'test': 2600000, 'ood': 2700000}


def choice(method, task, stage):
    if method != 'phase_rule':
        return ESTIMATORS.index(method)
    return 3 if ((task == TASKS[0] and stage == 2) or
                 (task == TASKS[1] and stage >= 3)) else 2


def run(env, task, seed, regime, method, config):
    obs, _ = env.reset(seed=seed)
    ctrl = FixedSkill(task, config)
    tape = SensorTape(seed, regime)
    bank = EstimatorBank(REGIMES[regime])
    initial = {'qpos': env.unwrapped.data.qpos.tolist(), 'qvel': env.unwrapped.data.qvel.tolist(),
                   'obs': {k:v.tolist() for k,v in obs.items()}}
    trace = []
    for step in range(50):
        # Only the simulated sensor sees the true object. The controller sees
        # the selected estimate, current proprioceptive gripper position, goal.
        packet = tape.sample(obs['achieved_goal'])
        estimates = bank.ingest(packet)
        selected = choice(method, task, ctrl.stage)
        error = float(np.linalg.norm(estimates[selected] - obs['achieved_goal']))
        stage_before = ctrl.stage
        action = ctrl.action(obs['observation'][:3], estimates[selected], obs['desired_goal'])
        obs, reward, terminated, truncated, info = env.step(action)
        trace.append({'step': step + 1, 't': (step + 1) * .04, 'stage': ctrl.stage,
                          'decision_stage': stage_before, 'selected': selected,
                          'action': action.tolist(), 'qpos': env.unwrapped.data.qpos.tolist(),
                          'qvel': env.unwrapped.data.qvel.tolist(), 'grip': obs['observation'][:3].tolist(),
                          'object': obs['achieved_goal'].tolist(), 'goal': obs['desired_goal'].tolist(),
                          'estimates': estimates.tolist(), 'estimation_error_m': error,
                          'covariance_diagonal': [np.diag(f.covs[-1]).tolist() for f in bank.filters],
                          'fast': None if packet.fast is None else packet.fast.tolist(),
                          'precise': None if packet.precise is None else packet.precise.tolist(),
                          'precise_step': packet.precise_step, 'ages_s': bank.ages(step),
                          'reward': float(reward), 'success': bool(info['is_success']),
                          'distance': float(np.linalg.norm(obs['achieved_goal'] - obs['desired_goal'])),
                          'terminated': bool(terminated), 'truncated': bool(truncated)})
        if terminated or truncated:
            break
    assert env.spec.max_episode_steps == 50 and len(trace) == 50 and trace[-1]['truncated']
    return {'task': task, 'seed': seed, 'regime': regime, 'method': method, 'config': config,
                'sensor_config': REGIMES[regime], 'initial': initial, 'trace': trace,
                'success': trace[-1]['success'], 'ever_success': any(s['success'] for s in trace),
                'last10_success': all(s['success'] for s in trace[-10:]),
                'final_distance': trace[-1]['distance'],
                'estimation_rmse_m': float(np.sqrt(np.mean([s['estimation_error_m'] ** 2 for s in trace])))}


def worker(items):
    gym.register_envs(gymnasium_robotics)
    envs = {t:gym.make(t) for t in TASKS}
    rows = []
    for task, seed, regime, method, config, output in items:
        result = run(envs[task], task, seed, regime, method, config)
        name = f'{task}_{seed}_{regime}_{method}.json.gz'
        with gzip.open(Path(output) / name, 'wt') as f:
            json.dump(result, f, allow_nan=False)
        rows.append({k:v for k,v in result.items() if k not in ['initial', 'trace']})
    for env in envs.values():
        env.close()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--split', choices=START_SEEDS, default='pilot')
    p.add_argument('--episodes', type=int, default=12)
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
    selection = json.loads(args.selection.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    folder = args.output / 'traces'
    folder.mkdir()
    write(args.output / 'protocol.json', {
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'split': args.split, 'parents_per_task': args.episodes, 'tasks': TASKS,
        'methods': METHODS, 'regimes': REGIMES, 'first_seed': START_SEEDS[args.split],
        'task_seed_stride': 1000, 'primary': 'final is_success at registered TimeLimit step 50',
        'shared': 'same physical seed and exogenous sensor tape across methods; same reset seed across regimes',
        'scope': 'Synthetic sensor robustness extension of standard tasks; fixed estimators, no learned router yet',
        'selection_sha256': hashlib.sha256(args.selection.read_bytes()).hexdigest(),
        'env': {'mujoco': mujoco.__version__, 'gymnasium': gym.__version__, 'robotics': gymnasium_robotics.__version__}})
    items = [(task, START_SEEDS[args.split] + ti * 1000 + i, regime, method, selection[task], str(folder))
             for ti, task in enumerate(TASKS) for i in range(args.episodes)
             for regime in REGIMES for method in METHODS]
    started, rows = time.perf_counter(), []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for batch in pool.map(worker, [items[i:i+5] for i in range(0, len(items), 5)]):
            rows.extend(batch)
    write(args.output / 'rows.json', rows)
    summaries = []
    for task in TASKS:
        for regime in REGIMES:
            for method in METHODS:
                rr = [r for r in rows if r['task'] == task and r['regime'] == regime and r['method'] == method]
                summaries.append(dict(task=task, regime=regime, method=method, episodes=len(rr),
                                      **{k:float(np.mean([r[k] for r in rr])) for k in
                                         ['success', 'ever_success', 'last10_success', 'final_distance', 'estimation_rmse_m']}))
    summary = {'summaries': summaries, 'episodes': len(rows), 'independent_parent_states': 2 * args.episodes,
                   'sensor_conditions_per_parent': 4, 'methods_per_condition': 5,
                   'control_steps': 50 * len(rows), 'wall_s': time.perf_counter() - started}
    write(args.output / 'summary.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k != 'summaries'}), flush=True)


if __name__ == '__main__':
    main()
