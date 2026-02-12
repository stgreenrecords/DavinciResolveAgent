# Refactoring Plan (Progress Tracking)

This document tracks implementation progress against the refactor recommendations from `CODE_REVIEW.md`.

**Legend:**
- ✅ Completed
- 🚧 In progress / partial
- ⬜ Not started

---

## Phase 0 — Stabilize & Quick Wins (Priority 1)
- ✅ Thread safety for stop flag; expose `is_stopped` API.
- ✅ API key storage safety with explicit confirmation and warnings when keyring unavailable.
- ✅ Action validation with target/key whitelists and clamp ranges before execution.
- ✅ Null-safety in UI flow with explicit calibration checks in `main_window.py`.

## Phase 1 — Architecture & Separation (Priority 2)
- ✅ Split `MainWindow` into focused components (MainWindow UI, AgentController, SettingsManager,
  CalibrationManager, IterationRunner, TaskQueue/ThreadPool).
- ✅ Dependency injection in `main.py` and constructors.
- ✅ Move shared models (e.g., `Roi`) into `core/` for layering.

## Phase 2 — Business Logic Hardening (Priority 2–3)
- ✅ Explicit state machine for agent lifecycle (`AgentStateMachine`).
- ✅ Action execution policy with fail-fast and rollback option.
- ✅ Convergence detection (`ConvergenceDetector`) in iteration loop.
- ✅ Metrics normalization (`MetricsNormalizer`).
- ✅ LLM provider abstraction (`LlmProvider`, `LlmClient` implements it).

## Phase 3 — Testing & QA (Priority 2)
- ✅ Unit tests added for core modules (`llm/client.py`, `automation/executor.py`,
  `vision/metrics.py`, `calibration/profile.py`, `storage/settings.py`).
- ✅ E2E controller test gated behind `AGENT_E2E` to keep unit runs non-blocking.
- ✅ Pytest config fixed (`pythonpath = ["."]`) and missing imports added (e.g., `logging`).
- 🚧 Target ≥80% coverage for core modules; add fixtures for LLM responses.

## Phase 4 — Type Safety & Static Analysis (Priority 2)
- 🚧 Use correct PySide6 enums (e.g., `Qt.WindowType.*`).
- 🚧 Add explicit `None` checks where required.
- ✅ Install missing stubs (`types-requests`, `types-Pillow`).
- 🚧 Complete type hints and explicit typed collections (partial fixes applied).

## Phase 5 — Performance & Reliability (Priority 3)
- ✅ Cache calibration config reads in `calibration/profile.py`.
- ✅ Move large image work off UI thread with progress feedback.
- ✅ Add HTTP connection pooling via `requests.Session` with retry adapter.
- ✅ Make debug screenshots configurable via env flag.

## Phase 6 — Best Practices & Maintainability (Priority 3–4)
- ✅ Remove dead/commented code; standardize error messages with codes.
- ✅ Centralize paths/constants in `config/paths.py` and `constants.py`.
- ✅ Add docstrings for public APIs/complex functions.
- ✅ Logging consistency: remove `print` from production/test paths.
- ✅ Consolidate config via `pydantic.BaseSettings` with env overrides.

---

## Milestones & Verification
- ✅ **Milestone A (Stability):** Targeted unit tests for executor/settings executed.
- ⬜ **Milestone B (Architecture):** UI smoke test + existing tests after Phase 1.
- ✅ **Milestone C (Logic/Testing):** Full unit/integration suite after Phase 2–3.
- ✅ **Milestone D (Type/Perf/Best Practices):** mypy + pytest + lint after Phases 4–6.
