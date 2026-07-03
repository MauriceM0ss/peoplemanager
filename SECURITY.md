# Security notes — People Viewer

People Viewer is a **single-user, self-hosted personal CRM**. It stores people,
conversations, tasks, notes and file attachments in a **SQLCipher-encrypted
SQLite database** unlocked by a PIN. This document records the threat model, the
findings from the hardening review, and operational recommendations.

## Threat model

**Assets.** The personal data in the database (names, notes, meeting content,
uploaded documents and pictures). Confidentiality is the priority.

**Deployment.** Docker — Flask serves on `0.0.0.0:8080` in the container,
published to the host (default `http://localhost:8081`). Data lives in the
`peoplemanager-data` volume.

**Trusted.** The host machine, its filesystem, the Docker daemon, and the person
who knows the PIN. Anyone with the running process's memory or the host
filesystem is already inside the trust boundary (the encryption key is held in
process memory while unlocked).

**In scope.**

- Confidentiality of data at rest (someone copies the DB volume/file).
- Network reachability of the web port on a shared LAN.
- Malicious content replayed to the single user's browser (stored XSS).
- Cross-site request forgery from a site the user visits while unlocked.
- Brute-forcing the PIN.
- Resource exhaustion via large uploads.

**Out of scope.** A local attacker with root/filesystem access on the host, or
memory access to the running process — both are inside the trust boundary. This
is a personal tool, not a multi-tenant service; there is no per-user
authorization model.

## Data protection

- Database encrypted with **SQLCipher**; key derived from the PIN with
  **PBKDF2-HMAC-SHA256, 260,000 iterations**, 32-byte random salt.
- PIN also stored as a **bcrypt** hash (separate from the encryption key) to
  verify unlock attempts.
- The derived key is kept **server-side in memory only** (`_sessions`); the
  browser cookie holds only an opaque random session id.
- Sessions auto-expire after the configured idle timeout (5/15/30/60 min).

## Findings & status

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| F1 | State-changing routes relied on `SameSite=Lax` alone for CSRF defence | Medium | **Fixed** — Origin/Referer check on all POST/PUT/PATCH/DELETE (`_csrf_origin_guard`) rejects cross-origin requests; `SameSite=Lax` + `HttpOnly` cookie retained. |
| F2 | `upload_photo` stored the client-supplied mimetype unchecked and `get_photo` served it **inline**, enabling stored XSS (e.g. a `text/html` or `image/svg+xml` "photo"); pictures accepted any `image/*` including SVG | Medium | **Fixed** — served Content-Type is derived from an extension allowlist (`safe_image_mime`), SVG/HTML/unknown types are rejected (415), and `X-Content-Type-Options: nosniff` is sent on every response. |
| F3 | No `MAX_CONTENT_LENGTH`; uploads read fully into memory/DB → resource exhaustion | Low | **Fixed** — request body capped at `MAX_UPLOAD_MB` (default 32 MB, env-configurable); oversize → 413. |
| F4 | No throttle on PIN unlock; short numeric PINs are brute-forceable | Medium | **Fixed** — escalating cooldown after 5 failed attempts (30s → 60s → … capped at 15 min); bcrypt already slows each guess. |
| A1 | Export/import write a **plaintext** temp DB to the data dir briefly | Low | **Accepted + documented** — same trust boundary (the process already holds the key); files are removed in a `finally` block. Keep the data volume on trusted storage. |
| A2 | Flask binds `0.0.0.0` in Docker → reachable on the LAN | Low | **Accepted + documented** — intended for self-hosting behind the user's own network/proxy; still PIN-gated. See recommendations. |
| A3 | `app_secret.key` stored in plaintext beside the DB | Low | **Accepted + documented** — only signs the session cookie holding an opaque sid; it does not protect data and is inside the trust boundary. |

### Non-issues confirmed during review

- SQL is parameterised throughout; the few f-string identifiers
  (`update_person` field, `ALTER TABLE` columns) come from fixed allowlists, and
  the `ATTACH`/`VACUUM INTO` paths are server-controlled temp files, not user
  input.
- `debug=False` in all entrypoints.
- Downloaded document filenames are sanitised by Werkzeug's `send_file`.

## Operational recommendations

- **Network exposure.** If you don't need LAN access, publish the port to
  localhost only (`127.0.0.1:8081:8080` in `docker-compose.yml`) or place the app
  behind a reverse proxy with TLS. The app speaks plain HTTP; don't expose it to
  untrusted networks without TLS in front.
- **Choose a strong PIN.** 4 characters is the minimum the app allows, not a
  recommendation. Longer, non-obvious PINs materially raise the brute-force bar.
- **Back up the encrypted volume**, not a decrypted export, for at-rest safety
  (see the README backup section). Store exports (which are plaintext SQLite)
  only on trusted media and delete them when done.
- **Keep the base image patched.** The Docker base image is pinned by digest for
  reproducibility; rebuild periodically to pick up upstream security updates
  (see README → *Updating*).
- **Trust the host.** Data is only as private as the machine and volume it lives
  on; the encryption protects a stolen/copied volume, not a compromised host.

## Reporting

This is a personal project. File an issue on the repository for any security
concern.
