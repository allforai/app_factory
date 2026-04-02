# Gaming Domain Knowledge

## Why This Exists

This project needs game-specific orchestration knowledge that is materially different from generic app planning. The important difference is that game work is not centered on CRUD features. It is centered on playable loops, content systems, balance, pacing, world coherence, and player motivation.

## Concept Collection Focus

When the project archetype is `gaming`, concept collection should prefer these questions:

- What is the core player fantasy?
- What is the core loop?
- What are the major progression loops?
- What worldbuilding elements are mandatory?
- What content scale is expected for prototype vs later production?
- What monetization model is in scope, if any?
- What platform constraints matter: PC, console, mobile, browser?

The system should not treat game work like a generic SaaS product. It must collect design intent, emotional tone, pacing expectations, and system depth early.

## Domain Work Areas

The most common game-specific domains are:

- worldbuilding
- player archetypes
- core mechanics
- economy
- progression
- level/content design
- narrative
- art direction
- balance testing
- playtest validation

These domains may run in parallel, but their seams must be explicit. For example:

- worldbuilding affects narrative and art direction
- core mechanics affects economy and progression
- progression affects balance and level pacing
- art direction affects UI, assets, and perception of feedback quality

## Planning Guidance

Use domain-specific work packages instead of feature-only tickets. Good game work packages look like:

- define combat loop state model
- draft progression curve for first 30 minutes
- design worldbuilding bible for prototype scope
- define economy source/sink model
- create playtest checklist for core loop

Avoid planning with only generic labels such as "frontend" or "backend" if the real uncertainty is in mechanics or design systems.

## Validation Guidance

Game validation should include more than build success:

- core loop completeness
- pacing sanity
- resource flow sanity
- player feedback clarity
- difficulty ramp sanity
- content teaching order

For prototypes, playability and design coherence matter more than production polish.

