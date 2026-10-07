# FiniSpeak commercial API v1

Base path: `/api/v1`  
Machine-readable contract: `/api/openapi.json`

## Authentication

Send the one-time key value in `X-API-Key`. Keys are stored only as a keyed SHA-256 digest and can be scoped, expired, and revoked. Never put keys in browser code or URLs.

Administrators issue keys with `POST /api/admin/api-keys` and an authenticated Firebase administrator token:

```json
{
  "action": "create",
  "organizationId": "organization-id",
  "name": "Production server",
  "scopes": ["interpreters:read", "routing:read", "usage:read"],
  "minuteLimit": 60,
  "dailyQuota": 10000,
  "expiresInDays": 365
}
```

The plaintext `token` is returned once. Configure `FINISPEAK_API_KEY_PEPPER` with at least 32 random bytes before issuing keys.

## Endpoints

- `GET /api/v1/interpreters` searches verified profiles. Repeat `language` to require all selected languages.
- `POST /api/v1/routing/recommendations` ranks matching interpreters.
- `GET /api/v1/usage` reports remaining minute and daily allowance.

Required scopes are `interpreters:read`, `routing:read`, and `usage:read`, respectively.

Responses include `X-Request-ID`, `X-RateLimit-Remaining`, and `X-DailyQuota-Remaining`. A `429` response includes `Retry-After`. Administrators can review `/api/admin/api-usage`, revoke a key at `/api/admin/api-keys/{keyId}/revoke`, and list keys at `/api/admin/api-keys`.

## Operations

Usage events contain key/organization identifiers, endpoint, method, status, duration, request ID, and timestamp—never credentials or request bodies. Configure Firestore TTL policies for `apiUsageCounters.expiresAt` and the desired retention policy for `apiUsageEvents.createdAt`.
