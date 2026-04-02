# Analysis and Design Knowledge

## Purpose

This phase converts concept into executable planning structure. It should synthesize domains, contracts, architecture boundaries, role bundles, and work packages.

## What This Phase Must Produce

- domain graph
- task graph
- role assignment
- contract candidates
- seam candidates
- work packages with clear acceptance criteria

## Design Rules

- Prefer domain-aligned work packages over arbitrary technical slices.
- Split only when context boundaries are real and seams can be governed.
- Create explicit seam objects when projects split.
- Define acceptance criteria before implementation starts.
- Map work packages to roles before mapping them to executors.

## Role Emphasis

This phase usually activates:

- product_manager
- execution_planner
- interaction_designer
- ui_designer
- technical_architect
- integration_owner

## Output Quality Checks

- every work package must have a goal
- every work package must have an acceptance signal
- every seam must have an owner
- risky parallelism must be gated by frozen seams or contracts

