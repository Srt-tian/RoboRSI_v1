# Mid-skill counterfactual sensing study

This is a bounded follow-up to the episode-level MuJoCo sensor-mode study. It
does not claim official Jev, image understanding, an optimal controller, or a
state-of-the-art result. No robot hardware is involved.

## Hypothesis and alternatives

The return of sensing depends on the motion executed while evidence is delayed.
A typed candidate-conditioned predictor may exploit phase and action history to
choose between continuing, waiting for a more precise stream, and asynchronously
switching to that stream. Strong alternatives are fixed modes, a validation-tuned
age/noise rule, and a validation-tuned task/phase lookup table. The last one can
disprove an apparent learned benefit caused only by the curriculum mixture.

## Fixed design, before test generation

- FetchPush-v4 and FetchPickAndPlace-v4; 2 ms physics, 40 ms control.
- A fixed privileged skill provides the prefix only. Snapshots are stratified by
  requested skill stage, with an additional 0–5 steps. Unreached stages are kept
  and flagged rather than silently discarded. This is a controlled checkpoint
  curriculum, not a learned full-episode policy evaluation.
- All three continuations start from an exact MjData copy, including solver
  state, plus the same controller memory and sensor history. Every restored
  integration state is checked. All continuations have the same 150-step budget.
- Current proprioception and task goal are observed. Object pose comes from a
  biased delayed tracker. True object state is reserved for sensor simulation,
  training branch labels, and evaluation, not supplied as an extra policy input.
- A precise stream is acquired at request time, delivered after D steps, and
  remains D steps old. Pausing advances physics and retains the gripper command.
  An asynchronous request continues the same skill before consuming the stream.
- Three candidate actions; one decision per checkpoint. No recurrent learned
  replanning, object-vision encoder, pretrained world model, or GPT call.
- 600 train, 180 validation, 360 IID test, 360 longer-delay test contexts by
  default. Independent seed ranges. Four feature variants, three training seeds.
- Shared candidate network, 64/64 hidden units, success BCE plus duration MSE.
  Checkpoint selected only using validation cost. Zeroed standardized-feature
  ablations retain parameter count; other correlated features can still reveal
  phase/age, so these are information-removal tests, not pure causal effects.
- Cost = failure + time_price * remaining duration. Success requires 10
  consecutive standard-success ticks. Prefix duration is excluded and logged.
- Freeze checkpoint hashes and all baseline rules before generating test data.
- Paired uncertainty must resample contexts, not count three network seeds as
  independent environments. Report both tasks, all seeds, negative results.

## Reproducibility and evidence

The execution commit must be canonical-remote recoverable before a remote run.
Run directly on the authorized development GPU; this is not an EIP submission.
Save every branch's actions, joint states, contacts, sensor age, observation and
success sequence, plus the integration state and controller at the fork. Record
videos using MjData-preserving rendering and compare replay against original
outcomes. Seal exported artifacts with content hashes; keep failed pilots.

First qualify the revised pushing skill, then inspect only pilot/train/validation
diagnostics. After opening held-out results, protocol changes require a new run
with new seed ranges. A null result is a valid falsification and must be visible.

## Relation to research

AAWR (arXiv:2512.01188) already learns active perception using training-time
privileged sensors. REMAC (arXiv:2601.20130) corrects action/perception mismatch,
and FutureRTC (arXiv:2607.24008) anticipates execution-time observations. None of
typed output, phase conditioning, or counterfactual labels alone establishes
novelty. The candidate hypothesis is an action-dependent evidence-consumption
decision tested under matched skill, information and compute constraints.
