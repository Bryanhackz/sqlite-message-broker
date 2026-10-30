# sqlite-message-broker

A persistent message broker with **at-least-once** delivery semantics, built
exclusively on SQLite and the Python 3.11+ standard library. No Redis, no
RabbitMQ, no Docker.

## Problem / Solution / Impact

- **Problem.** Reliable producer→consumer coordination usually requires a
  message broker, which in turn usually requires an external service. That
  is a non-starter for air-gapped, on-prem environments.
- **Solution.** A broker built directly on SQLite: persistent queue states
  (`pending` → `processing` → `done` / `dead`), atomic claim under
  `BEGIN IMMEDIATE`, visibility timeout with an opaque lease token,
  exponential backoff on failure, and a dead-letter state after max retries.
- **Impact.** A backend team can integrate reliable messaging into an
  air-gapped deployment without adding a single external dependency.

## Architecture
