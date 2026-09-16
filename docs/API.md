# Fork HTTP surface

Source: `src/index.ts`. This documents this fork, not Jarvis production. Default port 3000 (`PORT` overrides). Express registers the following routes without general authentication middleware; restrict network access, especially the test adapter.

| Method/path | Contract |
|---|---|
| GET `/health` | `{status: "ok"}` |
| GET `/health/db` | 200 when SELECT 1 succeeds; 500 with database disconnected otherwise |
| GET `/health/concurrency` | Lock-manager statistics and status; 500 on error |
| POST `/test/message` | JSON `conversationId` and `message` required; 400 if missing; returns accepted message while orchestration proceeds asynchronously |
| GET `/test/messages/:conversationId` | Test adapter messages for that conversation |
| DELETE `/test/messages/:conversationId?` | Clears selected/all test adapter output; returns success |
| POST `/webhooks/github` | Conditional on `GITHUB_TOKEN` and `WEBHOOK_SECRET`; raw JSON body and `x-hub-signature-256` header |

Webhook requests missing the signature header return 400. The handler starts `handleWebhook` asynchronously and replies 200 before processing finishes: 200 is receipt, not proof that signature validation or downstream agent work succeeded. Inspect adapter logs/results.

```sh
curl --fail http://localhost:3000/health/db
curl --fail http://localhost:3000/test/message \
  -H 'Content-Type: application/json' \
  --data '{"conversationId":"local-smoke","message":"status"}'
```

The second call can execute agent work; use only a configured disposable local instance. Platform adapters and database schemas are described in the existing architecture/setup documentation.
