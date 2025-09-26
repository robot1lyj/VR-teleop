中文回答



# Repository Guidelines

## Project Structure & Module Organization
- `controller_state.py`: dataclass model tracking left/right grip state, quaternions, and reset helpers consumed by the stream server.
- `controller_stream.py`: asynchronous WebSocket service (`run_vr_controller_stream`) that parses controller payloads into goal dictionaries written to stdout; entrypoint when packaging.
- `__init__.py`: exposes `run_vr_controller_stream` so the package can be imported as `telegrip.vr_new`.
- `web-ui/`: standalone A-Frame client (`index.html`, `interface.js`, `vr_app.js`, `styles.css`) plus `vendor/` assets; serve this directory as static content during local testing.

## Build, Test, and Development Commands
- `python -m telegrip.vr_new.controller_stream --host 0.0.0.0 --port 8442`: launch the debug WebSocket server; set `PYTHONPATH` so that the parent `telegrip/` package is discoverable.
- `python -m http.server 8080 --directory web-ui`: host the browser UI and log console for controller telemetry.
- `python - <<'PY'` ... `PY`: quick way to feed synthetic payloads to the server for unit-style debugging; reuse `_handle_controller` helpers directly.

## Coding Style & Naming Conventions
- Python: keep PEP 8 defaults, 4-space indentation, type hints, and module-level `logger = logging.getLogger(__name__)`; use snake_case for functions and camelCase only when mirroring WebSocket JSON keys.
- JavaScript: 2-space indentation, wrap modules in IIFEs as already done, prefer `const`/`let`, and follow the existing `vrbridge-*` event naming.
- CSS: extend the BEM-like modifier pattern (`status--connected`) when adding UI states.

## Testing Guidelines
- Target `pytest` for future automation; place specs in `tests/` mirroring module names (`tests/test_controller_stream.py`).
- For manual checks: run the stream server, serve `web-ui/`, connect via `ws://localhost:8442`, and confirm printed goal dictionaries and UI status changes.
- Record latency observations (frame interval ≈20 ms) in PR notes when adjusting timing-sensitive code.

## Commit & Pull Request Guidelines
- Follow the existing git history’s short, present-tense summaries (e.g., “获得手柄信息成功”); keep subject ≤50 characters and focus on the observable outcome.
- Squash work-in-progress commits before opening a PR.
- Every PR should list build/test commands run, include relevant terminal output snippets or UI screenshots, and link tracking issues when available.

## Security & Configuration Tips
- The stack ships with plain `ws://`; if deploying beyond trusted networks, generate certificates and configure `websockets.serve()` for `wss://`.
- Never commit VR device credentials or custom certificates; share sensitive configs through deployment secrets instead.
