# Testing and Verification Knowledge

## Purpose

Testing should verify both local correctness and cross-project closure. This is where seams, regressions, and acceptance gaps become visible.

## Verification Layers

- work package verification
- seam verification
- integration verification
- acceptance verification

## QA Focus

Testing should emphasize:

- core flow completion
- regression risk
- edge-case and error-path behavior
- seam correctness
- acceptance criteria closure

## Seam-Specific Guidance

When projects are split, verification must explicitly check:

- contract alignment
- payload or schema shape
- state-machine consistency
- version drift

## Output Expectations

Testing should produce:

- pass/fail verdicts
- findings with severity
- evidence summary
- next handoff recommendation

