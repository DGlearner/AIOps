---
name: code-simplifier
description: >-
  A subtraction-oriented refactoring skill for daily Code Agent use. Simplify messy,
  duplicated, legacy, or over-engineered code by deleting, merging, and reducing
  complexity while preserving behavior and verifying every change.
---

# Code Simplifier Skill

Use this skill when the user wants a Code Agent to simplify a codebase, clean up messy code, remove duplication, reduce dead code, or make an MVP/prototype easier to maintain.

This is not a general architecture refactor skill.

This is a **deletion-first, complexity-reduction, behavior-preserving** skill.

## Core Goal

Make the codebase:

- smaller
- simpler
- easier to review
- easier to verify
- cheaper to maintain

Optimize for fewer lines, files, branches, wrappers, dependencies, duplicated implementations, and unnecessary concepts.

Do not optimize for making the code look more advanced.

## Decision Order

Always decide in this order:

1. Can it be deleted?
2. Can it be merged?
3. Can it be simplified?
4. Only then consider adding something new.

Refactor means simplify, not decorate.

## Use When

Use this skill for:

- removing unused code
- deleting dead files or helpers
- merging duplicated logic
- reducing unnecessary abstractions
- simplifying long or nested functions
- collapsing useless wrappers
- removing unused dependencies or config
- cleaning historical patches and MVP code

Do not use this skill for:

- adding major features
- framework migration
- behavior redesign
- large rewrites
- performance redesign
- security, auth, payment, permission, audit, or data migration logic unless explicitly approved

## Hard Rules

The agent must:

- prefer deletion over addition
- prefer editing existing code over adding new files
- prefer merging duplication over creating abstractions
- prefer direct control flow over hidden indirection
- keep each round small and reviewable
- preserve existing behavior unless fixing a confirmed bug
- run verification before and after changes when practical
- distinguish pre-existing failures from newly introduced failures
- stop when risk or uncertainty becomes high

The agent must not:

- add frameworks, dependencies, managers, services, factories, or extension points without approval
- move complexity from one file to another
- perform unrelated refactors
- make noisy mass renames
- change public APIs without approval
- delete logic it does not understand
- delete tests to make validation pass
- claim safety without verification
- compress readable code into clever dense code just to reduce LOC

## Risk Boundaries

### Safe Changes

Usually allowed after reference checks:

- unused imports
- unused local variables
- commented-out legacy code
- empty files
- unreferenced helpers
- duplicate helpers with identical behavior
- obsolete demo code not used by docs, tests, scripts, or CI
- unused dependencies confirmed across imports, scripts, configs, and lockfiles

### Medium-Risk Changes

Allowed only when the affected path is understood and verifiable:

- merging similar functions
- simplifying branches
- collapsing wrappers
- consolidating config reads
- simplifying local error handling
- reducing nesting in one function
- removing debug output after confirming it is not required

### Risky Changes

Do not execute without explicit approval:

- API routes
- CLI entry points
- public SDK or library APIs
- database migrations
- auth, permission, payment, security, or audit logic
- user data handling
- deployment, CI, Docker, or environment config
- scheduled jobs
- webhook handlers
- dynamic imports
- plugin-loaded code
- telemetry, logging, metrics, tracing, or monitoring logic
- legacy compatibility logic

When unsure, mark the change as risky instead of deleting it.

## Daily Workflow

### 1. Inspect First

Before editing, inspect the project structure, entry points, main flow, tests, scripts, duplicated logic, dead code, unused imports/dependencies/config, long functions, wrappers, and dynamic loading patterns.

Do not edit before understanding what is safe to touch.

### 2. Establish Baseline

Before changing code, run the strongest practical verification:

- tests
- lint
- typecheck
- build
- startup command
- import check
- syntax check
- key CLI or API check

Record what passed, failed, was skipped, or was already broken.

### 3. Pick One Small Goal

Each round should focus on one theme only.

Good goals:

- remove unused imports
- delete unreferenced helpers
- merge duplicated parsing logic
- simplify one complex function
- collapse useless wrappers
- remove unused dependencies

Bad goals:

- clean the whole project
- redesign architecture
- modernize everything
- refactor all files
- rename all modules

### 4. Check References Before Deletion

Before deleting a file, function, class, dependency, config key, route, or command, search for:

- direct imports
- string references
- config references
- CLI entries
- route registration
- tests and fixtures
- docs and scripts
- CI and Docker usage
- package entry points
- plugin registries
- dynamic imports or auto-discovery

Absence of normal imports is not enough.

### 5. Apply Minimal Changes

Prefer changes that reduce lines, files, functions, branches, nesting, duplicated logic, wrappers, dependencies, config points, call depth, and special cases.

Avoid adding new files, helpers, abstractions, dependencies, config keys, or future-proof extension points.

New code is allowed only if it removes more complexity than it adds and preserves behavior.

### 6. Verify After Editing

Run the same or stronger verification after the change.

Compare against the baseline and report:

- passed checks
- failed checks
- pre-existing failures
- newly introduced failures
- skipped checks
- unverified areas

Never claim the refactor is safe without evidence.

## Stop Conditions

Stop and report instead of continuing when:

- the change requires behavior changes
- the affected path cannot be verified
- the code is dynamically loaded or externally exposed
- reference checks are inconclusive
- the diff grows beyond the small goal
- tests fail in a new way
- business logic is unclear
- the work turns into feature development or architecture redesign

## Output Format

Use this concise report format:

```markdown
## Refactor Goal

## Baseline
- Tests:
- Lint / Typecheck / Build:
- Known pre-existing failures:

## Changes Made
- Deleted:
- Merged:
- Simplified:
- Intentionally not touched:

## Metrics
- Files changed:
- Lines added:
- Lines deleted:
- Net LOC change:
- Functions/classes removed:
- Dependencies removed:
- Duplicate blocks merged:

## Verification
- Post-change checks:
- Comparison with baseline:
- Unverified areas:

## Risks / Next Step
```

Keep the report short, specific, and evidence-based.

## Success Criteria

A good simplification refactor:

- reduces code size or obvious complexity
- avoids increasing file count
- removes duplication or unused code
- preserves behavior
- avoids new dependencies
- keeps the diff easy to review
- provides clear verification results

A bad refactor:

- adds abstractions without need
- creates deeper file structures
- only formats or renames code
- changes behavior silently
- cannot be verified
- makes the project look engineered but harder to maintain

## Final Reminder

This skill is subtraction engineering.

Always ask:

1. Can it be deleted?
2. Can it be merged?
3. Can it be simplified?
4. Only then, should anything be added?
