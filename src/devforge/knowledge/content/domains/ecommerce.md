# E-Commerce Domain Knowledge

## Why This Exists

Commerce work has different risk centers from games or generic content apps. The dangerous areas are transactional correctness, state-machine consistency, stock behavior, price computation, payment callbacks, and operational workflows.

## Concept Collection Focus

When the project archetype is `ecommerce`, concept collection should prefer these questions:

- Who are the main roles: buyer, seller, admin, customer service?
- What is the critical purchase flow?
- How are pricing, coupons, tax, and shipping calculated?
- What are the order states?
- How should inventory be reserved and deducted?
- What payment methods and callback behaviors are required?
- What return, refund, and cancellation flows are in scope?

## Core Business Flows

The baseline commerce flow is:

- browse
- search
- product detail
- add to cart
- checkout
- payment
- order confirmation

Additional operational flows usually include:

- order tracking
- cancellation
- return/refund
- seller inventory management
- admin operations

## Domain Risks

High-risk areas that should influence planning and testing:

- inventory consistency under concurrent purchase
- payment idempotency
- order state transitions
- price and discount correctness
- async callback handling
- admin and customer-service workflow completeness

## Planning Guidance

Create work packages around business invariants and seams, not just screens:

- define order state machine
- implement cart pricing contract
- validate payment callback idempotency
- implement stock deduction strategy
- verify refund flow and admin handling

## Validation Guidance

Commerce acceptance should emphasize:

- end-to-end checkout usability
- order lifecycle correctness
- callback and retry safety
- price consistency
- stock correctness
- admin recovery paths

