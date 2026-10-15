# Backend Layering Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize the backend into clearer application, domain, and infrastructure layers without changing runtime behavior.

**Architecture:** Keep FastAPI routes and workers as entrypoints. Move domain schemas/models, persistence adapters, and LangGraph agent orchestration into clearer package namespaces, while leaving compatibility wrappers at old import paths.

**Tech Stack:** Python, FastAPI, LangGraph, SQLAlchemy, Kafka, Redis, PostgreSQL, pytest.

---

### Task 1: Create Target Packages

**Files:**
- Create: `backend/src/crossst/domain/`
- Create: `backend/src/crossst/infrastructure/`
- Create: `backend/src/crossst/application/`

**Steps:**
1. Add package directories with `__init__.py`.
2. Keep the old package names available during the first refactor pass.

### Task 2: Move Domain Types

**Files:**
- Move implementation from `crossst.models` to `crossst.domain.models`.
- Move implementation from `crossst.schemas` to `crossst.domain.schemas`.
- Leave wrappers in `crossst.models` and `crossst.schemas`.

**Steps:**
1. Move files.
2. Update imports inside moved files.
3. Add wrapper modules that re-export the moved objects.
4. Run model/schema focused tests.

### Task 3: Move Infrastructure Adapters

**Files:**
- Move implementation from `crossst.storage` to `crossst.infrastructure.storage`.
- Leave wrappers in `crossst.storage`.

**Steps:**
1. Move files.
2. Update imports inside moved files.
3. Add wrapper modules.
4. Run storage focused tests.

### Task 4: Move Agent Application Layer

**Files:**
- Move implementation from `crossst.agents` to `crossst.application.agents`.
- Leave wrappers in `crossst.agents`.

**Steps:**
1. Move files.
2. Update imports inside moved files.
3. Add wrapper modules.
4. Run LangGraph and chat agent tests.

### Task 5: Verify Entry Points

**Files:**
- Check `crossst.api`, `crossst.workers`, `scripts`, and tests.

**Steps:**
1. Keep public imports working.
2. Run full backend test suite.
3. Fix broken imports or monkeypatch paths.

### Task 6: Clean Project Surface

**Files:**
- Modify: `.gitignore`

**Steps:**
1. Ensure generated frontend/backend artifacts are ignored.
2. Do not delete user data or generated files unless explicitly requested.
