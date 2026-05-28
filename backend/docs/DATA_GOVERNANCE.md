# Data Governance

## Data Categories

- User identity: `openid`, nickname, avatar URL.
- Product data: product name, category, image key or mock URL, AI summary.
- Survey data: generated questions and original answer content.
- AI data: persona answers, report content, chat messages, token usage, cost estimate.
- Credit data: balance, transactions, recharge orders, provider transaction ids.
- Operational data: request id, task id, webhook delivery status, error code.

## Retention

- Soft-deleted business data keeps `deleted_at`.
- Hard deletion is scheduled after the configured retention period.
- Logs must be rotated and must not become the long-term source of user content.

## Deletion Flow

1. Authenticate the user or operator action.
2. Mark product/evaluation/report/conversation records with `deleted_at`.
3. Keep credit ledger rows for reconciliation unless legal deletion is required.
4. Queue physical cleanup for files and generated artifacts after retention expires.

## Logging Boundaries

Never log JWT, WeChat code, Ark API key, object-storage signed URL, raw product images, or full original answer content.

## Internal Access

Only operators with a production need may access user content. Access must be logged with operator identity, request id, purpose, and timestamp.

## Webhook Data

Follow-up webhook payloads may include openid, nickname, product image key, original answers, task id, and token/cost fields. Configure destinations carefully and rotate secrets when staff or vendors change.
