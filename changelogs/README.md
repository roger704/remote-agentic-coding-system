# remote-agentic-coding-system changelogs

Keep human-readable source changes and verified deployment records in this directory. Existing upstream/root release histories remain valid historical references.

- Source entries: `YYYY-MM-DD-description.md`; describe changed behavior and documentation.
- Verified deployment entries: `deployments/<environment>-<run-id>-<attempt>.md`; one immutable entry per actual deployment attempt, including redeploys of the same revision.
- Include UTC time, project/environment, exact source SHA and artifact or image digest, previous deployed revision when known, workflow/run or operator evidence, change summary, validation/outcome, migrations, operational actions and rollback notes. State `none` or `unknown` explicitly rather than omitting these fields.
- Never label a build, merge, design proposal or documentation update as a deployment. Failed deployments must retain their actual failed outcome. Do not include tokens, customer data or environment secret values.

Nexus owns automated deployment documentation where its deployment workflow is configured. Manual deployments must provide equivalent evidence; the presence of this directory alone does not mean automation is enabled.
