# Processing Policy

## 1. Core Execution Rules

### 1.1 Time, Dates, and Deterministic Row Selection

- **Canonical timezone:** `UTC` is the canonical timezone for all timestamps, comparisons, and job execution logic.
- **Date format standard:** All persisted and displayed dates must use ISO format `YYYY-MM-DD`.
- **Deterministic row selection:** When duplicates or multiple eligible rows exist, the worker must always select the **oldest pending row** (ordered by created timestamp ascending, then primary key ascending as a tiebreaker).

## 2. Idempotency Guardrails

- **Atomic status transitions:** Each row must move through a strict, atomic lifecycle:
  1. `blank` -> `In Progress`
  2. `In Progress` -> `Done`

  Status updates must be performed in a single transactional operation with a predicate on the current status to prevent double-processing.

- **Stale recovery rule:** Any row left in `In Progress` longer than the stale threshold (default: **30 minutes**) is eligible for recovery. Recovery resets the row to `blank` and increments a retry counter before it can be selected again.

- **Run traceability:** Each processed row must store a unique `run_id` (UUID recommended) set when transitioning to `In Progress` and retained through `Done` for auditability, replay analysis, and cross-system tracing.
