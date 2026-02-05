# Security and Credential Management Manual

## Secret Handling Policy

All secrets **must** be loaded at runtime from environment variables or a centralized secrets manager. Secrets must **never** be hardcoded in source files, committed to version control, or embedded in configuration files that are checked into the repository.

Approved secret sources:

- Environment variables injected by the runtime environment (local shell, CI/CD, container orchestration, or deployment platform).
- Managed secrets services (for example: cloud secrets managers, Vault-like systems, or organization-approved secret stores).

Forbidden patterns:

- API keys, OAuth client secrets, tokens, JSON key contents, or private keys written directly in application code.
- Credentials in sample code that look real or are reusable.
- Plaintext credentials in tracked files, including `.env` files committed to Git.

## Required Secret Variables and Ownership

The following variable names are required and must be used consistently:

- `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`
  - Purpose: Filesystem path to the Google service account JSON credential file.
  - Owner: Data/Platform Engineering (or designated Google Cloud project administrators).
- `YOUTUBE_OAUTH_CLIENT_SECRET_PATH`
  - Purpose: Filesystem path to the YouTube OAuth client secret JSON file.
  - Owner: YouTube integration owners (or designated OAuth application administrators).
- `DEEPSEEK_API_KEY`
  - Purpose: API key used to authenticate to DeepSeek services.
  - Owner: AI Platform team (or designated service owners who manage vendor API subscriptions).
- `INWORLD_API_KEY`
  - Purpose: API key used to authenticate to Inworld services.
  - Owner: Conversational/Experience Platform team (or designated Inworld account administrators).

Ownership guidance:

- Every secret must have a clearly assigned team owner and a named backup owner.
- Owners are responsible for issuance, rotation cadence, least-privilege scope, incident response, and access reviews.
- Access to each secret must be restricted to the minimum set of services and operators required.

## Linux File-Permission Requirements for Credential Files

Any credential material stored as files (such as JSON client credentials) must be owner-readable only.

Required permissions:

- Credential files must be set to mode `600` (`rw-------`).
- File owner must be the runtime service account (or designated operator account).
- Group/other read, write, or execute permissions are prohibited.

Example hardening commands:

```bash
chmod 600 /path/to/google-service-account.json
chmod 600 /path/to/youtube-oauth-client-secret.json
chown <service-user>:<service-user-group> /path/to/credential-file.json
```

Validation guidance:

- Validate permissions during deployment startup and fail closed if permissions are too broad.
- Periodically audit credential-file paths for ownership and mode drift.

## Logging and Redaction Requirements

Tokens, API keys, OAuth secrets, and credential file contents must be redacted from logs.

Rules:

- Never log raw values of `DEEPSEEK_API_KEY`, `INWORLD_API_KEY`, OAuth secrets, access tokens, refresh tokens, or full credential JSON.
- Mask secret values in diagnostic output (for example, `sk-****...****`).
- Avoid dumping environment variables wholesale in logs.
- Ensure error paths and debug logging apply the same redaction rules.

## Key Rotation and Revocation Checklist (Compromised Credentials)

When a credential is suspected or confirmed compromised, perform the following immediately:

1. **Containment**
   - Disable affected workloads or revoke outbound calls if active abuse is possible.
   - Remove compromised credential from runtime environments and CI/CD variables.
2. **Revoke and regenerate by credential type**
   - `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`:
     - Revoke/disable compromised Google Cloud service account key in Google Cloud IAM.
     - Generate a replacement key (or migrate to keyless Workload Identity where possible).
   - `YOUTUBE_OAUTH_CLIENT_SECRET_PATH`:
     - Rotate the OAuth client secret in Google Cloud Console for the OAuth client.
     - Update authorized redirect URIs/scopes if review indicates misuse.
   - `DEEPSEEK_API_KEY`:
     - Revoke/regenerate in the DeepSeek developer console/account portal.
   - `INWORLD_API_KEY`:
     - Revoke/regenerate in the Inworld console/account portal.
3. **Redeploy and validate**
   - Update secret store/environment variables with new values/paths.
   - Redeploy all dependent services.
   - Verify authentication succeeds with new credentials and fails with old ones.
4. **Audit and cleanup**
   - Search logs, traces, and chat transcripts for exposed material and purge where possible.
   - Invalidate related session tokens or downstream credentials derived from compromised keys.
5. **Post-incident hardening**
   - Document incident timeline and root cause.
   - Shorten rotation interval and tighten permission boundaries.
   - Add or improve secret scanning and pre-commit/CI detection controls.

Minimum response SLA:

- Initial revocation action should begin immediately upon detection.
- Full rotation and redeploy should be completed as quickly as operationally feasible under incident procedures.
