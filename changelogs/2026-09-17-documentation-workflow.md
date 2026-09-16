# Documentation workflow — 2026-09-17

## Changed

Enrolled project documentation, interface references and operational notes in `.nexus/project.json`. Added the shared Python structural documentation gate, pull-request/default-branch CI check, and a manual deployment wrapper with durable report receipts and replay. Existing enrolled deployment workflows run the gate before build/deployment. The gate reports changed API/runtime/operational paths requiring review; passing does not establish semantic documentation completeness.

## Deployment

Source change only. This entry does not claim an application or infrastructure rollout. Nexus emits separate verified deployment records when the configured workflow or authenticated manual reporter provides evidence.

## Migration and operational notes

No application database migration. Operators must configure the report token securely and use an enrolled manual environment. Receipts remain in Git metadata if reporting fails; replay resends a receipt without rerunning deployment. Read `docs/deployment-documentation.md` before manual releases. CI requires Python 3.9 or newer; the dedicated documentation workflow uses Python 3.12.

Validation: shared contract unit tests and this project's declared-document check. No application E2E result is implied by these structural checks.
