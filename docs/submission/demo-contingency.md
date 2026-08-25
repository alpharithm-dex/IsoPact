# Demo contingency

Five minutes before recording or judging, verify Cloud Run `/health`, the four Runtime agents, Firestore, the live pact, receipt verifier, UI, and prepared Google Cloud console tabs. Keep the hosted UI available through judging with scale-to-zero and a maximum of three instances.

If a live agent call fails, restart the recording or explicitly switch to a visibly labeled **VERIFIED REPLAY**. Never present replay as live. Preserve the live Cloud Run revision and timestamp in the recording.

Fallback order: retry fresh page once; verify `/health`; show deployment proof; use verified replay only with the label; explain the failure honestly.
