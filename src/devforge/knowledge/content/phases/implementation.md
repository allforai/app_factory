# Implementation Knowledge

## Purpose

Implementation should convert design intent and contracts into bounded code changes. This phase should not be treated as one giant free-form coding session.

## Implementation Rules

- choose strategy per work package complexity
- keep work packages bounded and verifiable
- compile or validate incrementally
- preserve architectural abstractions
- never silently skip unmappable items
- leave explicit notes when an item is deferred

## Strategy Selection

Use different implementation styles for different work:

- direct translation for low-complexity UI or syntax-level work
- adapt-and-translate for medium complexity stateful work
- intent rebuild for high-complexity or debt-heavy areas

## Executor Guidance

- `codex` is a strong fit for explicit implementation packages
- `claude_code` is a strong fit for design-heavy implementation and architecture-sensitive work
- executor choice should still respect role and domain context

## Verification Expectation

Implementation is not complete at file write time. It needs:

- compile/build verification
- local contract sanity
- handoff notes for QA or integration

