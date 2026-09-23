"""Clean-state SAC + HER lower-level skill baseline, not a JEV result.

Uses registered 50-step Fetch tasks and final-step success for checkpoint
selection. Validation seeds are fixed; no held-out test is consumed here.
"""
import argparse
import importlib.metadata
import json
import os
import subprocess
import time
from pathlib import Path

os.environ.setdefault('MUJOCO_GL', 'egl')
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
import gymnasium as gym
import gymnasium_robotics
import numpy as np
import torch
from stable_baselines3 import SAC, HerReplayBuffer
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import SubprocVecEnv


def write(path, obj):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(obj, indent=2, allow_nan=False))
    temporary.replace(path)


def make_env(task):
    def factory():
        gym.register_envs(gymnasium_robotics)
        env = gym.make(task)
        assert env.spec.max_episode_steps == 50
        return Monitor(env)
    return factory


class Validation(BaseCallback):
    def __init__(self, task, output, interval, episodes):
        super().__init__()
        self.env = gym.make(task)
        assert self.env.spec.max_episode_steps == 50
        self.output, self.interval, self.episodes = output, interval, episodes
        self.next_at, self.started, self.rows, self.best_key = 0, time.perf_counter(), [], None

    def evaluate(self):
        rows = []
        for index in range(self.episodes):
            seed = 2810000 + index
            obs, _ = self.env.reset(seed=seed)
            successes, rewards = [], []
            for step in range(50):
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = self.env.step(action)
                successes.append(bool(info['is_success']))
                rewards.append(float(reward))
                assert not terminated and truncated == (step == 49)
            rows.append({'seed': seed, 'success': successes[-1], 'ever_success': any(successes),
                         'final_distance': float(np.linalg.norm(obs['achieved_goal'] - obs['desired_goal'])),
                         'return': sum(rewards)})
        success = float(np.mean([r['success'] for r in rows]))
        distance = float(np.mean([r['final_distance'] for r in rows]))
        key = (-success, distance)
        record = {'steps': self.num_timesteps, 'wall_s': time.perf_counter() - self.started,
                  'validation_success': success, 'mean_final_distance': distance,
                  'mean_return': float(np.mean([r['return'] for r in rows])),
                  'mean_ever_success': float(np.mean([r['ever_success'] for r in rows]))}
        write(self.output / f'validation_{self.num_timesteps:08d}.json', {'summary': record, 'rows': rows})
        self.rows.append(record)
        if self.best_key is None or key < self.best_key:
            self.best_key = key
            self.model.save(self.output / 'best_model')
            write(self.output / 'best_checkpoint.json', record)
        write(self.output / 'curve.json', self.rows)
        print(json.dumps(record), flush=True)

    def _on_training_start(self):
        self.evaluate()
        self.next_at = self.interval

    def _on_step(self):
        if self.num_timesteps >= self.next_at:
            self.evaluate()
            self.next_at += self.interval
        return True

    def _on_training_end(self):
        if self.rows[-1]['steps'] != self.num_timesteps:
            self.evaluate()
        self.env.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--task', default='FetchSlide-v4', choices=['FetchSlide-v4', 'FetchReach-v4'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, default=250000)
    p.add_argument('--seed', type=int, default=11)
    p.add_argument('--envs', type=int, default=4)
    p.add_argument('--eval-interval', type=int, default=25000)
    p.add_argument('--eval-episodes', type=int, default=50)
    p.add_argument('--learning-starts', type=int, default=10000)
    p.add_argument('--device', default='cuda')
    args = p.parse_args()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
    assert args.steps % args.envs == 0
    assert args.envs > 0 and args.eval_interval > 0 and args.eval_episodes > 0
    args.output.mkdir(parents=True, exist_ok=False)
    gym.register_envs(gymnasium_robotics)
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.set_float32_matmul_precision('highest')
    env = SubprocVecEnv([make_env(args.task) for _ in range(args.envs)], start_method='forkserver')
    model = SAC('MultiInputPolicy', env, replay_buffer_class=HerReplayBuffer,
                replay_buffer_kwargs={'n_sampled_goal': 4, 'goal_selection_strategy': 'future'},
                policy_kwargs={'net_arch': [256, 256]}, buffer_size=250000,
                batch_size=256, gamma=.95, tau=.05, learning_rate=.001,
                learning_starts=args.learning_starts, train_freq=1, gradient_steps=1,
                seed=args.seed, device=args.device, verbose=0)
    config = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'task': args.task, 'training_transitions': args.steps, 'seed': args.seed,
              'num_envs': args.envs, 'validation_episodes': args.eval_episodes,
              'validation_first_seed': 2810000, 'validation_interval': args.eval_interval,
              'selection': 'highest final-step success, then lowest final distance; validation only',
              'held_out_test_generated': False, 'registered_horizon': 50,
              'scope': 'Clean privileged-state lower-level skill baseline; not a learned JEV judgment result',
              'inputs': 'Full standard observation dict, including privileged object pose/velocity, achieved and desired goals',
              'outputs': 'Four continuous Cartesian/gripper action values in [-1, 1]',
              'algorithm': 'Stable Baselines3 SAC + future HER',
              'hyperparameters': {'net_arch': [256, 256], 'buffer_size': 250000, 'batch_size': 256,
                                  'gamma': .95, 'tau': .05, 'learning_rate': .001,
                                  'learning_starts': args.learning_starts, 'train_freq': 1,
                                  'gradient_steps': 1, 'n_sampled_goal': 4, 'entropy': 'auto',
                                  'normalize_observations': False, 'tf32': False},
              'parameters': {'actor': sum(p.numel() for p in model.actor.parameters()),
                             'critics': sum(p.numel() for p in model.critic.parameters())},
              'versions': {n: importlib.metadata.version(n) for n in
                           ['torch', 'numpy', 'mujoco', 'gymnasium', 'gymnasium-robotics', 'stable-baselines3']}}
    write(args.output / 'protocol.json', config)
    print(json.dumps(config), flush=True)
    try:
        model.learn(args.steps, callback=Validation(args.task, args.output, args.eval_interval, args.eval_episodes))
        model.save(args.output / 'final_model')
        model.save_replay_buffer(args.output / 'replay_buffer.pkl')
        write(args.output / 'completion.json', {'status': 'complete', 'transitions': model.num_timesteps,
                                               'scope': 'development training and validation only'})
    finally:
        env.close()


if __name__ == '__main__':
    main()
