# Stage 11 judge interface

IsoPact's judge surface is a React 19, TypeScript, and Vite single-page application compiled into the existing Outcome Gateway container. The dominant surface is the live Outcome Pact Graph; economics, the Case Chronicle, cryptographic receipt, and operational proof are supporting views.

## Trust boundary

The browser applies backend-supplied snapshots only. It does not calculate lifecycle, economics, evidence rank, invariants, operation identity, eligibility, or receipt validity. `GET /v1/demo/stage11` returns a sanitized presentation contract assembled from the configured authoritative pact and captured proof artifacts. `POST /v1/demo/stage11/receipts/verify` reads the configured Firestore receipt, checkpoint, and ordered StateClaim chain, invokes the existing integrity verifier, and returns its result. The tamper option changes an in-memory copy only.

The API does not accept an arbitrary pact identifier. The service account reads the configured pact; consequential action endpoints retain their existing signed-agent authorization. Live mode never silently substitutes replay data.

## Delivery

The multi-stage root Dockerfile compiles the frontend and copies only `dist` into the existing Python image. Cloud Run service `isopact-outcome-gateway`, revision `isopact-outcome-gateway-00022-flq`, serves the UI and API from the same origin. Image digest: `sha256:7f6accaae477e4eb430edf69ed210fc586c75950321bad821c7bdf303a474119`.

