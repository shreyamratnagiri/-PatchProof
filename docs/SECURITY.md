# Security boundaries and threat model

**Do not deploy PatchProof for adversarial multi-tenant public submissions.** Docker containers are not equivalent to VM/hardware isolation and may share kernel attack surface.

## Supported controls

Archive ZIPs are size bounded and extracted one member at a time into a temporary directory. Absolute paths, path traversal, backslashes, special filesystem entries, casefold collisions, reserved directories and excessive decompression ratios are rejected. Unpacked size and file count caps apply. Accepted source content is treated as data, not code to import.

Git ingestion permits only `https://github.com/OWNER/REPO` HTTPS paths, without credentials, fragments or arbitrary ports. The Git process has an isolated configuration, no checkout, no hooks, no filters, no submodules, disabled redirects and bounded time. Files are read as Git blob objects and written into restricted storage. Public GitHub network access may be unavailable. **Redirect/proxy/remote infrastructure and Git client vulnerabilities still form an untrusted network boundary.**

API operations require the configured `X-PatchProof-Key` and return HTTP 503 if the key is missing. The key supports a trusted single-user deployment only; there is no tenant isolation, account roles, or sophisticated request rate-limiting beyond selected operational caps.

Ollama is external to the API and receives sanitized-size, but *untrusted*, source snippets and bug reports. Model outputs must conform to Pydantic schema, remain in top-ranked source scope, identify a uniquely occurring old fragment, and pass language syntax checks. Prompt injection remains possible but cannot grant model-produced shell commands authority to execute outside sandbox.

Docker runner options include `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit 64`, `--cpus 1`, `--memory 256m`, `--user 65534:65534`, readonly source bind mount, bounded tmpfs and timeout with container removal. Host credentials and Docker socket are not mounted into test containers. Captured logs are capped at 12,000 bytes per stream; the trusted Docker CLI process is killed on cancellation or timeout, and forced container cleanup is requested. Only disposable sandbox copies have world-readable source permissions to support the unprivileged container UID; imported originals remain 0600. Docker daemon compromise, container breakout, and unsafe trusted orchestration are residual risks.

The API container in docker-compose is intentionally not given the Docker socket. Docker verification executes only through the persistent job queue and `python -m packages.sandbox_worker` trusted host-side process (see `docs/TRUSTED_WORKER.md`); never by dropping sandbox constraints or falling back to subprocess on host.

## Known gaps

- Authentication is static API key; not enterprise multi-user identity or authorization.
- No CSRF defense if browser-based cookie auth is later added (currently no cookies).
- No endpoint-wide reverse-proxy request size enforcement or global IP rate-limit.
- No dedicated VM/microVM separation from hostile repositories.
- No external vulnerability scan run in the authoring environment.
- Docker timeout/cleanup cannot be empirically demonstrated without Docker.
- Generated regression tests are untrusted code and require sandbox isolation.

## Deployment hardening

Use HTTPS with external auth and a private network, rotate API tokens, place quotas at ingress, pin image digests, isolate Docker orchestration on a worker host, use microVMs for hostile submissions, and log security-relevant actions without leaking source secrets. Never share host Docker control with untrusted containers.

**Operational limitation:** The Docker runner only discovers Python `unittest` scripts and uses fixed container options. A trusted host process controls the Docker daemon. Do not expose the API or daemon to arbitrary Internet users.

## Release candidate security change

The trusted host worker has broad Docker daemon capabilities and private DB/artifact access; protect its OS account. The API has no Docker daemon access. Job enqueue/claim/cancellation are persisted as SQL records in migration `0004`. Host worker crashes leave a leased job that becomes `interrupted`, and retries require an explicit operator action. This is not hardened multi-tenant isolation. The network-disabled Docker test container can still be dangerous if a host kernel escape exists.
