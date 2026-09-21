# Offline RSI workbench · 2026-09-21

## Objective

Turn the documented cross-trial workflow into offline tools that summarize evidence,
evaluate bounded coarse-plan revisions, and prepare explicitly reviewed planning
context. Preserve the 200 Hz executor and historical evidence.

## Decisions

- Separate observed guard failures, hypotheses, and task outcomes. Missing task
  labels remain unknown; execution completion never supplies a success label.
- Reuse the deterministic compiler for candidate evaluation. Report numerical
  validity separately from URDF geometry and physical task success.
- Keep baseline context, gripper events/guards, and the return state fixed when
  comparing paths. Bound joint changes. Outputs are reports, never live streams.
- Search the two existing timing profiles as a small, reproducible offline demo.
  Shorter predicted duration is not evidence of improved grasp success.
- Store content fingerprints and explicit scope on review artifacts. Select only
  accepted, matching records for planning; selection does not authorize execution.
- No hardware access, model downloads, generated-code execution, or training.

## Acceptance

- Historical metrics can be processed without editing any original record.
- Tests cover absent outcomes, invalid metrics, altered evidence, excessive path
  edits, relaxed guards, changed scenes/seeds, invalid geometry, and scope mismatch.
- A complete offline demo produces JSON and a local HTML report; unchanged final
  plan at 2x still compiles to 17,046 targets.
- README, RSI documentation, editable diagrams, and a dated primary-source
  research note describe the implemented boundary precisely.

## Completion

- Implemented `roborsi-rsi analyze/evaluate/sweep/review/context/workbench` and
  a self-contained local HTML viewer; package version is 0.2.0.
- 26 offline tests pass, including a subprocess that rejects socket creation and
  hardware-driver imports during the workbench command.
- Historical metrics produce six records, three execution failures and one
  existing task-result text. No task success rate is inferred.
- Same-plan profile comparison yields 33,129 targets / 165.645 s at 1x and
  17,046 targets / 85.230 s at 2x. Geometry was not checked without the rig URDF;
  physical success was not evaluated.
- All 34 original evidence archives pass integrity checks. Core controller,
  compiler, historical plans and raw experiment files are unchanged.
- Updated architecture and RSI diagrams pass structural checks and PNG visual
  inspection. The local workbench was rendered and inspected in a browser.
- Research note records five verified primary-source papers through 2026-09-21;
  implementation, external results and future hypotheses are distinguished.
