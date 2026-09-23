"""Check the information boundary and immutable prefix in actual MuJoCo."""
import copy
import unittest

import gymnasium as gym
import gymnasium_robotics
import numpy as np
from physics_phase import prepare
from physics_queue_evidence import (
    BASE_FEATURES,
    TASKS,
    audit_prefix,
    branch,
    commands,
    context,
    feature_vector,
    streams,
)


class QueueEvidenceTest(unittest.TestCase):
    def test_shared_prefix_and_zero_age_transport_identity(self):
        gym.register_envs(gymnasium_robotics)
        for i, task in enumerate(TASKS):
            env = gym.make(task, max_episode_steps=300)
            try:
                c = context(i + 2, 'pilot')
                c['task'] = task
                snap = prepare(env, c)
                queue = commands(c, snap, 2)
                results = [branch(env, c, snap, queue, r) for r in range(3)]
                audit_prefix(results, queue)
                x1 = feature_vector(c, snap, queue)
                x0 = feature_vector(c, snap, commands(c, snap, 0))
                self.assertEqual(x1[:len(BASE_FEATURES)], x0[:len(BASE_FEATURES)])
                c0 = copy.deepcopy(c)
                c0['delay'] = 0
                candidates, _ = streams(c0, snap['obs'], snap['history'], snap['grips'])
                np.testing.assert_allclose(candidates[1], candidates[2], atol=1e-15, rtol=0)
            finally:
                env.close()


if __name__ == '__main__':
    unittest.main()
