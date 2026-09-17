# Agent instructions

## Architecture diagrams and change planning

Before planning or implementing a change, read [docs/diagrams/README.md](docs/diagrams/README.md), the project guide and the source files linked by the map. For significant changes, document the current as-is behavior and a clearly labeled to-be proposal before implementation, covering affected components, data flow and external boundaries. Keep proposals distinguishable from implemented behavior. Update diagrams and their evidence links in the same PR as the corresponding code/configuration change; if no diagram change is needed, explain why in the review. Reconcile proposals after implementation. Never infer a runtime or deployment from a design-only diagram. Preserve existing repository instructions and upstream attribution.

Before completing a PR, review the staged source against the diagrams and update `.nexus/diagrams.json` with `scripts/check-diagrams.py`; do not stamp without that review. A source change can require a renewed review even when no diagram arrow changes. Nexus maintenance refreshes must use the reviewed PR workflow; do not assume autonomous merges.
