# FilaOps API Conventions

Conventions and patterns used across the FilaOps REST API (`/api/v1/`).

## Response Formats

### List Endpoints

List endpoints return a paginated envelope:

```json
{
  "total": 42,
  "items": [ ... ]
}
```

Newer endpoints using the `ListResponse` wrapper include pagination metadata:

```json
{
  "items": [ ... ],
  "pagination": {
    "total": 42,
    "offset": 0,
    "limit": 50,
    "returned": 42
  }
}
```

### Single-Item Endpoints

Single-item endpoints (GET by ID, POST create, PATCH update) return the
resource object directly -- no wrapper.

```json
{
  "id": 1,
  "sku": "WIDGET-001",
  "name": "Widget",
  ...
}
```

## URL Naming

- Plural nouns for collections: `/products`, `/vendors`, `/sales-orders`
- Kebab-case for multi-word resources: `/sales-orders`, `/production-orders`,
  `/purchase-orders`, `/work-centers`
- Sub-resources use nesting: `/sales-orders/{id}/events`,
  `/purchase-orders/{id}/lines`
- Actions use POST with verb suffix: `/production-orders/{id}/release`,
  `/sales-orders/{id}/cancel`

> **Note:** Some legacy endpoints use singular nouns or different casing.
> These are not renamed for backward compatibility.

## Pagination

List endpoints accept `skip` and `limit` query parameters:

| Parameter | Default | Max | Description              |
|-----------|---------|-----|--------------------------|
| `skip`    | 0       | --  | Number of records to skip |
| `limit`   | 50      | 500 | Maximum records to return |

Some newer endpoints use `offset` instead of `skip` (same semantics).

## Error Responses

All errors return a JSON body with a `detail` field and an appropriate
HTTP status code:

```json
{
  "detail": "Product with ID 123 not found"
}
```

Common status codes:

| Code | Meaning                                      |
|------|----------------------------------------------|
| 400  | Bad request / validation error               |
| 401  | Authentication required or invalid token      |
| 403  | Forbidden -- insufficient permissions        |
| 404  | Resource not found                           |
| 409  | Conflict (duplicate SKU, invalid transition) |
| 422  | Unprocessable entity (business rule violation)|
| 500  | Internal server error                        |

## Authentication

Almost every endpoint requires a JWT Bearer token:

```
Authorization: Bearer <access_token>
```

### Who can call what

Every route needs a **staff** account (admin or operator), and admin-only
routes need an **admin** account. A valid login alone is not enough, because
customer accounts sign in too. The only
exceptions are:

- **No login needed:** `/auth/login`, `/auth/logout`, `/auth/refresh`,
  `/auth/portal/login`, the password reset routes (`/auth/password-reset/*`),
  customer self-registration (`/auth/register` and `/auth/portal/register`,
  which answer 403 unless `ENABLE_PUBLIC_QUOTER=true`), first-run setup
  (`/setup/status`, `/setup/initial-admin`), `/system/version`,
  `/system/info`, `/system/health`, `/settings/company/logo`, and `/health`
  (outside `/api/v1`).
- **Any logged-in account, limited to its own records:** `GET /auth/me` and
  the customer quote routes: `POST /quotes/portal`,
  `POST /quotes/portal/{quote_id}/accept`,
  `POST /quotes/portal/{quote_id}/checkout`, `GET /quotes/{quote_id}/archive`,
  `GET /quotes/{quote_id}/files` and
  `GET /quotes/{quote_id}/files/{file_id}/download`.

Every other route answers 401 without a token and 403 for a customer account.

When you add a route, gate it with `Depends(get_current_staff_user)` or
`Depends(get_current_admin_user)` from `app.api.v1.deps`, preferably on the
module's `APIRouter(dependencies=[...])` so new routes in that module are
covered too. `backend/tests/endpoints/test_route_authz_allowlist.py` fails for
any route that has neither and is not on its reviewed allowlist.

## Versioning

The API is versioned via URL prefix: `/api/v1/`. No breaking changes are
made within a major version.
