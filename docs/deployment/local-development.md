# Local development

Create a new Python 3.12 virtual environment and install `requirements-lock.txt`. Run `python -m pytest -q`. In `frontend`, run `npm ci`, `npm test -- --run`, and `npm run build`.

The Flask service expects cloud configuration when exercising Firestore-backed routes. Pure unit tests and deterministic simulator/benchmark smoke do not require developer ADC. Verified Replay data is compiled from repository-contained sanitized artifacts and has no workstation path dependency.

The production image is built by the root multi-stage `Dockerfile`. It performs a clean `npm ci`, frontend build, pinned Flask deployment install, and copies only the compiled frontend plus required sanitized verification keys.

