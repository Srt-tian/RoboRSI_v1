import tempfile, unittest
from pathlib import Path
import numpy as np
from roborsi.ik import URDFIK


class KinematicsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name) / "arm.urdf"
        p.write_text(
            """<robot name="test"><link name="base"/><link name="arm"/><link name="tip"/><joint name="hinge" type="revolute"><parent link="base"/><child link="arm"/><axis xyz="0 0 1"/><limit lower="-2" upper="2"/></joint><joint name="slide" type="prismatic"><parent link="arm"/><child link="tip"/><origin xyz="1 0 0" rpy="0 0 1.5707963267948966"/><axis xyz="1 0 0"/><limit lower="0" upper="1"/></joint></robot>"""
        )
        self.ik = URDFIK(p, "base", "tip")

    def test_prismatic_axis_rotates_with_origin(self):
        np.testing.assert_allclose(self.ik.fk([0, 0.2])[:3, 3], [1, 0.2, 0], atol=1e-10)

    def test_jacobian_matches_finite_difference_and_ik(self):
        q = np.array([0.3, 0.2])
        j = self.ik.jacobian(q)
        for k in range(2):
            delta = np.eye(2)[k] * 1e-6
            measured = (
                self.ik.fk(q + delta)[:3, 3] - self.ik.fk(q - delta)[:3, 3]
            ) / 2e-6
            np.testing.assert_allclose(j[:3, k], measured, atol=1e-8)
        result = self.ik.solve(self.ik.fk(q), q + [0.02, -0.02])
        self.assertTrue(result.success)
