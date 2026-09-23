"""Fixed Fetch skills for the phase study; old study controllers stay unchanged."""
import numpy as np
from physics_pilot import Controller as OriginalController


class Controller(OriginalController):
    def action(self, grip, obj, goal):
        if self.task != 'FetchPush-v4':
            return super().action(grip, obj, goal)
        self.ticks += 1
        delta = goal[:2] - obj[:2]
        distance = np.linalg.norm(delta)
        direction = delta / max(distance, 1e-6)
        behind = obj[:2] - .045 * direction
        # Fetch mocap workspace edge: a farther staging point can be unreachable.
        behind = np.clip(behind, [1.12, .43], [1.54, 1.04])
        relative = obj[:2] - grip[:2]
        along = float(relative @ direction)
        lateral = np.linalg.norm(relative - along * direction)
        if self.stage == 2 and distance > .025 and (lateral > .025 or along < -.012):
            self.stage = 0
            self.ticks = 0
        if self.stage == 0:
            target = np.r_[behind, obj[2] + .085]
        elif self.stage == 1:
            target = np.r_[behind, obj[2]]
        else:
            target = np.r_[obj[:2] + .020 * direction, obj[2]]
            if distance < .025:
                target = grip.copy()
        if self.stage < 2 and np.linalg.norm(grip - target) < .012:
            self.stage += 1
            self.ticks = 0
        speed = .25 if self.stage == 2 else .75
        return np.r_[np.clip((target - grip) * 6, -speed, speed), -1.0]
