# Deployment verification

Run:

```powershell
python scripts/collect_stage13_inventory.py
python scripts/verify_deployment.py
python scripts/release_verify.py
```

The verifier checks project/regions, immutable Cloud Run image, four agents, managed identity evidence, Firestore, Pub/Sub, KMS versions, secrets, Model Armor, dashboard, APIs, health, security headers, unauthenticated denial, cross-role denial evidence, sanitized UI data, valid receipt, invalid tampered receipt, and Stage 12 smoke.

