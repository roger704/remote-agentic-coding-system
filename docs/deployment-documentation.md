# Documentation checks and deployment records

Nexus reads this repository's `.nexus/project.json` at an immutable source revision. Declared project/API/operational documents must exist and contain meaningful content; `changelogs/README.md` is required separately. A repository without its own API declares an empty API list or an explicit interface-scope document.

## Before a release

```sh
python3 scripts/check-documentation.py
# Compare against the actual previous deployed Git SHA when known:
python3 scripts/check-documentation.py --base <40-character-sha>
```

The shared Python 3.9+ standard-library gate rejects missing/empty declared docs, unsafe paths and symlinks. It reports documentation, API and operational review signals from changed paths. With no known base it flags the whole tracked tree for review. Passing is structural evidence, **not** proof that prose accurately explains every behavior. Review relevant setup, API, migration and rollback details when the signals require it. Update docs in the same change, or record why no documentation update is needed in the PR/release review.

The `Documentation` workflow checks pull requests and default-branch pushes. Enrolled deployment workflows also run the gate before deploying. Nexus observes configured successful workflow jobs and records their verified source revision; deployment failure is not relabeled as success. It writes a separate immutable entry under `changelogs/deployments/`, with the environment/run/attempt identity and operational notes. Source-documentation entries do not claim deployments.

## Manual deployments

Only `manual_environments` listed in `.nexus/project.json` are eligible. Configure `NEXUS_DEPLOYMENT_REPORT_TOKEN` securely in the operator environment; no token belongs in Git. Use a clean checkout of the exact commit and supply a real HTTPS evidence location and operational notes:

```sh
python3 scripts/deploy-with-documentation.py run \
  --environment <enrolled-environment> \
  --evidence-url https://<your-release-evidence> \
  --operational-notes 'Describe migrations, restart requirements and rollback; say none when applicable.' \
  -- <actual-deployment-program> <arguments>
```

The wrapper runs the documentation gate **before** the command, executes argv without a shell, withholds the report token from the child process, and records its real exit outcome afterward. Changing tracked source or HEAD during the command forces a failed receipt requiring reconciliation. The command must deploy this exact checkout/artifact and perform its target health checks before returning success. The wrapper cannot independently inspect arbitrary external deployments or establish that a command really used the declared source. Do not wrap a build-only command and call it a deployment.

Receipts are stored with private permissions under Git metadata (`git rev-parse --git-path nexus-deployment-outbox`). If reporting fails, the wrapper returns a failure and keeps a pending receipt. Retry reporting without rerunning the deployment:

```sh
python3 scripts/deploy-with-documentation.py replay <deployment-uuid>
```

An interrupted `running` receipt cannot be replayed as success: reconcile the actual target outcome manually. `accepted` means Nexus accepted the report, not proof that a GitHub changelog write has already completed. Check the resulting project changelog in Nexus/Friday.

For native-store/extension UI installation or other out-of-band actions, report the actual source/outcome through the enrolled manual endpoint after obtaining evidence. Neither the wrapper nor Nexus can detect every action performed outside configured workflows. The endpoint is `POST https://agent.sicken.work/nexus/api/projects/deployments`, authenticated by `x-nexus-deployment-token`. JSON fields: `repository` (`owner/repo`), `environment`, 40-character `source_sha`, lowercase UUID `deployment_id`, UTC ISO `completed_at`, `outcome` (`success` or `failure`), HTTPS `evidence_url`, and `operational_notes` (at most 4000 characters). Reuse the deployment ID when retrying the same report, never when performing a new deployment.

## Shared implementation

Canonical scripts and tests live in [agent-stack](https://github.com/roger704/agent-stack/tree/main/scripts); copies in active project repositories allow their own deployment checks to run without downloading executable code at deployment time. Update and test the shared copies together.
