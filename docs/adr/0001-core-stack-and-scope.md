# 0001. Core stack and scope

## Status
Accepted

## Context
At the start of planning this project (a school-management-system backend, whose real purpose is agentic-harness/TDD practice — see the README), several foundational tradeoffs needed settling before any staged roadmap could be written: sync vs. async SQLAlchemy, which dependency manager, when authentication should land in the roadmap, how broad the feature scope should be, and which password-hashing library to use.

## Decision
- **Async SQLAlchemy 2.0** (`asyncpg` driver), over sync — idiomatic for FastAPI, and the pattern most production FastAPI codebases actually use, despite the added async/await overhead throughout the stack.
- **uv** for dependency/environment management, over Poetry or pip+venv.
- **Auth lands early** (Stage 2, immediately after the first domain model), not deferred to the end — every later domain stage builds behind real permission checks from the start rather than retrofitting auth on top of open endpoints.
- **Feature scope**: core academic domain (students, teachers, subjects/classes, enrollment) + grades/assessments + academic terms/years & scheduling. Explicitly excluded for now: attendance, fees/billing.
- **Argon2** (`argon2-cffi`, Argon2id) for password hashing, over bcrypt/passlib.

## Consequences
- Every domain built after Stage 1 assumes an async session/engine end-to-end; introducing a sync code path anywhere would be inconsistent with this decision, not a neutral choice.
- Attendance and fees/billing are deliberately out of scope — adding them later is an intentional roadmap extension, not a course-correction of a mistake.
- The auth-early ordering means Stage 1 (Students) is the only domain stage built without permission checks already in place; every stage from Stage 2 onward is expected to be gated.
