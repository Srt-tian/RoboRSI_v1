# Standalone System One experiment

Status: three analytic studies completed and sealed; followed by two MuJoCo learning studies. Created 2026-09-22; updated 2026-09-23.

## Question and novelty gate

Can a small non-generative judge learn when acquiring evidence rescues a grasp,
and when acquisition itself spoils a grasp through delay or contact? A positive
result must beat a tuned rule and a capacity-matched outcome predictor, not only
an always-act baseline. This is a hypothesis, not a claim of first invention.

Active perception, value of information, uplift modeling, successor features,
and counterfactual harm are existing ideas. The proposed research focus is the
**deadline-dependent rescue/spoil profile of evidence acquisition**, a typed
interface that can change decisions under new time costs without retraining,
and explicit tests of its dependence on simulator counterfactual coupling.

## Scope

- Offline probabilistic grasp micro-simulator, not Piper dynamics or a vision model.
- Small NumPy neural models trained from simulated branches; no official Jev API.
- Hidden object position, velocity and random outcomes are inaccessible to policy.
- All policies share the same three macros and Bayesian pose estimator.
- Actions: grasp now; obtain a delayed visual measurement then grasp; contact
  probe then grasp. Acquisition costs time and contact may displace/damage objects.
- One macro selection per context; reactive pose estimation inside each macro is
  analytic and shared. This is not general multistep robot policy learning.

## Protocol fixed before testing

1. Implement and audit simulator and gradients on a small pilot. Pilot is not test.
2. Train on context seed 11001, validate on 22002. Compare outcome prediction,
   paired rescue/spoil prediction, and ablations; retain every run and curve.
3. Choose training checkpoints and rule thresholds using validation only.
4. Freeze choices in a hashed protocol before constructing test sets: IID 33003,
   longer delays 44004, changed time costs 55005. Use independent Monte Carlo
   evaluation branches. An extra known-model planner uses an independent branch
   sample rather than the evaluation labels.
5. Record per-context decisions and all potential outcomes, bootstrap by context,
   report paired cost differences, success, sensing, harm and latency separately.
6. Audit menu duplication and counterfactual coupling. Counterfactual harm from
   paired branches depends on a specified structural simulator and is not
   identified by marginal real-world success rates alone.
7. Export replay, training curves, CSV/JSON, checkpoints and hashes to a new local
   Web run. Keep earlier evidence immutable. No CAN or hardware execution.

## Success and stopping criteria

Complete one reproducible study with several validation iterations and an honest
held-out assessment, including negative results. If the proposed paired model
does not improve over outcome prediction, reject that superiority hypothesis and
name the remaining research gap instead of relabeling the baseline as innovation.
Further test-driven changes require new seeds and a new study, never tuning on
the already opened test. Hardware/photorealistic validation remains separate.

## 2026-09-23 progress and next frozen study

- Analytic paired-label superiority rejected; deadline effects remain conditional.
- MuJoCo study 1: 920 contexts, 2,760 branches, 3 trained seeds.
- MuJoCo study 2: 1,500 checkpoints, 4,500 branches, 12 models, 30 exact replay videos.
- Local light single-page Web and six-page Chinese CoRL-template research draft.
- Next: train-side cross-fitted counterexample acquisition versus equal-budget random acquisition; fresh test ranges; add a distinct contact task and visual input.
- IDC CPU resources authorized for collection/confirmation; CLOUD 24 GB GPU available for visual models. This does not authorize EIP training submissions without their required resolved-configuration confirmation.
