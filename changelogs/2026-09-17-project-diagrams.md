# Project diagrams and freshness checks

Documentation change; this entry does not claim a runtime deployment.

- Adds source-linked Mermaid views of current responsibilities and flows, with planning instructions for as-is/to-be proposals.
- Registers maintained diagram documents and a reviewed-source fingerprint.
- Adds structural/source-drift checks and pinned Mermaid syntax validation in documentation CI; enrolled deployment checks reject stale receipts.
- Nexus maintenance opens reviewed diagram update PRs; merging remains an operator decision.

No application data migration. Diagram validation needs Python3.9+ and Node22; install its pinned dependencies with npm ci --ignore-scripts --prefix scripts/diagrams. After source changes, review the diagrams, stage the intended changes, and run python3 scripts/check-diagrams.py --stamp --index before staging the updated manifest.
