# InkSight Backend Deployment Notes

This document describes what was changed to make the device pairing flow work with:

- backend on Vercel: `https://mnml-backend.vercel.app`
- web app on Vercel: `https://mnml-webapp.vercel.app`
- ESP32 firmware provisioning through captive portal

It also lists what should be done for full production hardening (no temporary TLS fallback).

---

## What is fixed now

### 1) Vercel startup and runtime stability

- JWT secret loading no longer tries to write `.jwt_secret` on read-only serverless filesystem.
- Backend now prefers `INKSIGHT_JWT_SECRET` / `JWT_SECRET`.
- If missing, backend uses an in-memory fallback secret so process can boot.

### 2) Postgres adapter compatibility (Neon/Vercel)

- Fixed `500 Internal Server Error` on `POST /api/device/{mac}/token`.
- Root cause: custom DB cursor wrapper for Postgres did not expose `rowcount` (and `description`).
- Added those fields in `core/db_adapter.py` so token provisioning logic works.

### 3) CORS / origin restrictions

- Kept support for LAN development mode.
- Explicitly allowed `*.vercel.app` origins so hosted frontend is not blocked in production deployments.

### 4) Device pairing flow

Current pairing flow is:

1. Device connects to Wi-Fi.
2. Device calls `POST /api/device/{mac}/token`.
3. Device calls `POST /api/device/{mac}/claim-token` with `X-Device-Token`.
4. Web app consumes code via `POST /api/claim/consume`.

The backend side of this flow is operational after the fixes above.

---

## Important current limitation (TLS on ESP32)

The firmware currently uses a **host-specific TLS fallback** (`setInsecure()`) for:

- `mnml-backend.vercel.app`

Reason:

- Some ESP32 + mbedTLS builds fail certificate verification (`-9984`) against the current Vercel chain even after successful NTP sync.

This is why provisioning now works reliably, but it is not the final production security posture yet.

---

## Production checklist (target: 1/1 secure setup)

### Backend (required)

1. Set stable secrets and DB env vars on Vercel:
   - `DATABASE_URL` (or `NEON_DATABASE_URL`)
   - `INKSIGHT_JWT_SECRET` (recommended) or `JWT_SECRET`
2. Keep CORS explicit:
   - include `https://mnml-webapp.vercel.app`
   - keep only required origins in production.
3. Keep `TrustedHostMiddleware` aligned with real domains.

### Firmware TLS (required for full hardening)

Replace host-specific `setInsecure()` fallback with one of:

1. **Preferred**: certificate/public-key pinning for `mnml-backend.vercel.app`.
2. **Alternative**: robust CA bundle update strategy (root + needed intermediates), tested against Vercel chain rotations.

Also keep NTP sync before all HTTPS calls:

- NTP is mandatory so certificate validity dates can be checked.

### Operational validation before release

Run these checks after each production deployment:

1. `POST /api/device/{mac}/token` returns `200`.
2. `POST /api/device/{mac}/claim-token` returns `200`.
3. `POST /api/claim/consume` from web app succeeds.
4. `GET /api/config/{mac}` from device succeeds.
5. `GET /api/render?...` from device succeeds.
6. No `origin_not_allowed` or `FUNCTION_INVOCATION_FAILED` in Vercel logs.
7. No `-9984` TLS failures in firmware serial monitor.

---

## Quick curl smoke tests

Use a real MAC:

```bash
curl -i -X POST "https://mnml-backend.vercel.app/api/device/30:ED:A0:3A:0B:6C/token"
```

Then with returned token:

```bash
curl -i -X POST "https://mnml-backend.vercel.app/api/device/30:ED:A0:3A:0B:6C/claim-token" \
  -H "Content-Type: application/json" \
  -H "X-Device-Token: <TOKEN>" \
  -d '{"pair_code":"123456"}'
```

If both return `200`, backend pairing endpoints are healthy.
