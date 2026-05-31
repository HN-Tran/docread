# Security model & hardening

This page documents docread's security posture and how to deploy it safely.
To **report** a vulnerability, see [`SECURITY.md`](../SECURITY.md).

## Threat model

docread runs **without user accounts or login**. It is suitable for personal
use, demos, internal tools, and production deployments serving multiple users.

- Every request is independent; there is no login or session.
- Users are isolated by **unguessable capability IDs**, not accounts: async
  analyze results and benchmark jobs are addressed only by random IDs, and no
  endpoint lists results, so one caller cannot discover or enumerate another
  caller's data.
- Uploaded files are processed per request and are not tied to an identity.
- Outbound HTTP to inference servers and optional compare engines happens only
  according to **your** configuration.

What docread does **not** provide out of the box: authentication, authorization,
per-account access control, or rate limiting. If your audience is untrusted,
add those at your reverse-proxy / IAM / network layer (see below).

## Outbound requests (SSRF protection)

Several features fetch a caller-supplied URL server-side: the `plain_text`,
`self_peer`, and `azure` compare engines (`POST /api/compare` and
`POST /api/benchmark`), peer-model discovery (`GET /api/peer-models`), and the
Azure-compatible `urlSource` analyze input.

All of these go through a shared hardened HTTP client (`app/services/safe_http.py`)
that, by default:

- allows only `http`/`https` schemes,
- resolves the target host and **rejects** any address that is not a public
  unicast address (loopback, RFC1918 private, link-local incl. the
  `169.254.169.254` cloud-metadata IP, multicast, reserved, unspecified, and the
  IPv6 / IPv4-mapped equivalents),
- pins the connection to the validated IP to prevent DNS-rebinding,
- preserves the original `Host` header and TLS SNI, and revalidates every
  redirect hop,
- caps the response size.

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTBOUND_ALLOW_HOSTS` | *(empty)* | Comma-separated hostnames and/or CIDRs that are allowed as outbound targets even if internal (e.g. `localhost,172.17.0.0/16`). Use this to compare against another docread/OCR instance on your LAN or Docker network. |
| `OUTBOUND_ALLOW_PRIVATE` | `false` | Escape hatch that allows **any** private/internal address. Only enable on a trusted deployment that untrusted users cannot reach. |
| `OUTBOUND_MAX_RESPONSE_BYTES` | `67108864` | Cap (bytes) on a server-fetched response body. `0` disables the cap. |

## Deploying for remote / multi-user access

If you expose docread to a network beyond your machine:

1. **Terminate TLS in front of it.** docread speaks plain HTTP; put it behind a
   reverse proxy (nginx, Caddy, Traefik) with HTTPS so uploaded documents and
   OCR output cannot be sniffed in transit. Use `APP_BASE_PATH` if mounting
   under a sub-path.
2. **Add your own access control if the audience is untrusted.** docread has no
   built-in authentication by design; gate it with your proxy / IAM / network
   policy as needed.
3. **Keep `OUTBOUND_ALLOW_PRIVATE` off** on any internet-reachable instance, and
   keep `OUTBOUND_ALLOW_HOSTS` limited to the internal targets you actually need.
4. **Disable or isolate third-party compare engines** (Azure, Google) in
   production unless you intend to call them.
