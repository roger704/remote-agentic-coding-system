# Local fork of remote-agentic-coding-system

Reviewed against source `ad60e90631bd73296d22ffbf730cc38096cf2f05` on 2026-09-17. This guide describes tracked implementation and does not assert live deployment state.

## Purpose and architecture

Upstream-style Node/TypeScript agent with Telegram/GitHub adapters, orchestration and PostgreSQL persistence. This fork is distinct from the production `jarvis-agent` repository. Preserve upstream README/license and consult `jarvis-agent` for production behavior.

## Setup and development

Use Node >=20, `npm ci`, and the existing `.env.example`/root setup guide. Development uses `npm run dev`; production compilation uses `npm run build` then `npm start`. Database migrations and platform credentials are required by the selected deployment profile.

## Verification

Run `npm run type-check`, `npm test`, `npm run lint`, and `npm run format:check`. Existing Docker Compose and cloud deployment documentation describe possible local deployment paths, not proof that this fork is deployed.

## Deployment and operations

No deployment workflow exists in this fork. Do not change Jarvis production from this repository. If intentionally deploying this fork, record its own environment, commit, schema migrations and adapter configuration; ensure test endpoints cannot be reached by untrusted clients.

Every actual deployment needs a distinct record under [changelogs](../changelogs/README.md), including exact revision/artifact, environment, outcome and operational notes. A source merge or successful build is not deployment evidence.

## Interfaces and further reading

[Fork HTTP API](API.md), [architecture](architecture.md), [cloud deployment](cloud-deployment.md).
