# 0025. Test strategy revision — stop testing the same thing twice

## Status
Accepted (revises the uniform application of `docs/adr/0002` / `docs/adr/0007`)

## Context
The user pushed back on test volume — first on Stage 11's 130 tests for one domain, then on the suite as a whole. The numbers supported it:

| | Before |
|---|---|
| Production code | 6,805 lines |
| Test code | **16,654 lines** (2.4:1) |
| Total tests | 702 |
| Fake repository classes | **37**, `FakeClassRepository` reimplemented **6 separate times** |

The sharpest signal was that unit and integration counts were near-identical *per domain* — academic_years 29/32, students 25/30, users 17/19, teachers 39/46, auth 18/20. If unit tests were targeting logic that's awkward to reach through HTTP, those counts would be lopsided. Near-parity meant both layers were exercising the same surface through different plumbing.

**How it got here.** ADR 0002/0007 established the unit(fake-repo)/integration(real-DB) split in Stage 1, when there was one domain and the fakes were nearly free. It was then applied *uniformly* for eleven stages without anyone asking whether it still earned its keep per domain, with each stage's delegated test-writing brief specifying an exhaustive coverage matrix. The cost compounded quietly.

**The fakes are not free**, and this project has direct evidence rather than a hypothetical:
- Stage 11's fakes drifted from the real repository interface (`count_by_section` vs `count_by_section_id`, `get_by_grade_year_name` vs `get_by_name`) and had to be reconciled after a red run.
- Adding one method (`SectionRepository.get_for_update`) to satisfy a security fix immediately broke 11 unit tests, because the fake had to be taught the same method.
- The `list`-shadowing bug (ADR 0018/0019) has now been hit in *fakes* three separate times.

A fake that drifts doesn't just cost maintenance — it can pass against an interface that no longer exists, which is worse than having no test.

## Decision

**Unit tests are for branching logic worth isolating from the DB.** Ownership scoping, capacity races, auth oracle defenses, auto-enrollment fan-out, grade aggregation, the last-super-admin invariant, cross-table validation rules. These are cheap to exercise exhaustively against a fake and awkward to set up over HTTP.

**Everything else gets integration coverage only.** One integration test proves the real constraint, the routing, the serialization *and* the RBAC wiring simultaneously — strictly more than its unit twin proved. Plain CRUD (create/get/list/update/delete, 404s, uniqueness pre-checks, pagination) does not need a unit twin.

**RBAC is asserted once per router tier, not once per route.** Nineteen near-identical `_without_token_returns_401` / `_as_teacher_role_returns_403` tests against a shared `_admin_only` dependency test FastAPI's `Depends`, not this codebase.

**Smell to watch:** if a domain's unit and integration counts are roughly equal, the unit half is probably duplicating rather than adding.

### Applied in this pass

Pruned the clear duplication; left the logic-heavy unit suites intact.

| Domain | Unit before | Unit after | What survived |
|---|---|---|---|
| sections | 63 | 31 | auto-enrollment fan-out, attach/detach, the new attach guards |
| academic_years | 29 | 3 | term-within-year date validation (before/after boundaries, update path) |
| classes | 29 | 2 | FK-existence checks on the *update* path (no integration twin) |
| students | 25 | 8 | student_number generation, PIN issuance, profile-picture cleanup |
| users | 17 | 3 | the last-active-super-admin invariant (ADR 0011's TOCTOU-guarded logic) |
| audit | 5 | 1 | the defaults-to-None detail |
| assessments / enrollments / auth / teachers | 171 | 171 | untouched — ownership scoping, capacity races, oracle defenses |

Result: **702 → 566 tests**, test LOC 16,654 → 15,103. The LOC drop is proportionally smaller than the test-count drop because the fakes are the bulk of the volume and most of them remain — the logic-heavy domains still need them.

## Consequences
- Stage 11 added an entire new domain and the suite still *shrank* (572 before the stage → 566 after).
- Deleting a passing test is only safe when its integration twin genuinely asserts the same thing; every removal here was checked against the integration test list first, not assumed.
- The remaining ~15 fakes are concentrated in the domains where they earn their place. Before adding a new one, check whether an integration test covers it instead.
- This revises how ADR 0002/0007's split is *applied*, not the split itself — the two-tier layout stays, it's just no longer applied uniformly regardless of what a domain actually does.
- Deliberately **not** done: a full sweep of the assessments (73) and enrollments (41) unit suites. Those are logic-heavy enough that the duplication is less clear-cut, and a large test refactor with no functional payoff carries its own risk of cutting the one test that mattered. Revisit only if they become a maintenance problem.
