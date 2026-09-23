"""Tests for counterfactual identity and observable-only features (needs MuJoCo)."""
import copy
import unittest
import gymnasium as gym
import gymnasium_robotics
import numpy as np
from physics_phase import TASKS, branch, context, feature_vector, prepare, restore, state_vector


class ForkTests(unittest.TestCase):
    def test_restore_replay_and_unobserved_state(self):
        gym.register_envs(gymnasium_robotics)
        for task_index, task in enumerate(TASKS):
            env = gym.make(task, max_episode_steps=300)
            try:
                c = context(4 + task_index, 'pilot')
                c['age'] = 3
                s = prepare(env, c)
                first = branch(env, c, s, 2)
                second = branch(env, c, s, 2)
                self.assertEqual(first, second)
                restore(env, s)
                np.testing.assert_array_equal(state_vector(env), s['integration_state'])
                # Undelivered current object truth must not enter a delayed feature.
                if len(s['history']) > 3:
                    original = feature_vector(c, s)
                    s['history'][-1] += .123
                    s['obs']['observation'][3:6] += .321
                    self.assertEqual(original, feature_vector(c, s))
            finally:
                env.close()

    def test_context_split_disjoint(self):
        splits = ['pilot', 'train', 'validation', 'test', 'delay']
        sets = [{context(i, split)['seed'] for i in range(2000)} for split in splits]
        for i, a in enumerate(sets):
            for b in sets[i + 1:]:
                self.assertFalse(a & b)


if __name__ == '__main__':
    unittest.main()
