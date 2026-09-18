"""Fresh feedback and measured-pose hold. Never disable, reset, or auto-release."""

import time
import numpy as np

REFERENCE_HASH = "8727832976b4968d12283c8cb6cdef945f1eace8e472c080c6272c464514a782"


def fresh_state(arms):
    for arm in (arms.left, arms.right):
        msg = arm._piper.GetArmJointMsgs()
        age = time.time() - float(msg.time_stamp)
        if not 0 <= age <= 0.25 or float(msg.Hz) <= 0:
            raise RuntimeError("joint feedback is stale")
        status = arm._piper.GetArmStatus().arm_status
        if status.arm_status != 0 or status.err_code != 0:
            raise RuntimeError("firmware arm status/error is nonzero")
    state, _ = arms.get_state()
    state = np.asarray(state, dtype=float)
    if state.shape != (14,) or not np.isfinite(state).all():
        raise RuntimeError("invalid measured dual-arm state")
    return state


def stop_worker(arms):
    arms._high_follow_running = False
    worker = arms._high_follow_thread
    if worker is not None:
        worker.join(timeout=2)
        if worker.is_alive():
            raise RuntimeError("worker did not stop; refusing concurrent hold writes")
    arms._high_follow_thread = None


def freeze_measured(arms):
    """Stop the only writer, clear queued moves, freeze one fresh measured target.

    Does not disable/reset/release or chase later drift. Leaves the firmware in
    enabled position control. No initialization or automatic resume on exit.
    """
    stop_worker(arms)
    state = fresh_state(arms)
    with arms._high_follow_lock:
        arms._high_follow_queue.clear()
        arms._high_follow_metadata_queue.clear()
        arms._reset_high_follow_segment_locked(reset_anchor=True)
        arms._high_follow_last_ref = state.copy()
    arms.left.apply_high_follow(state[:6], state[6], arms.gripper_effort)
    arms.right.apply_high_follow(state[7:13], state[13], arms.gripper_effort)
    return state
