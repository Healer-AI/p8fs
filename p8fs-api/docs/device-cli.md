# Device CLI Documentation

The P8FS Device CLI provides commands for managing device authentication, including registration, approval, and token management.

## Installation

The CLI is part of the `p8fs-api` package and available via `uv`:

```bash
cd p8fs-api
uv run python -m p8fs_api.cli.device <command>
```

## Configuration

### Default Server

By default, the CLI uses the production server at `https://p8fs.eepis.ai`.

### Using Local Server

To use a local development server:

```bash
uv run python -m p8fs_api.cli.device --local <command>
```

This uses `http://localhost:8001` as the server URL.

### Custom Server

To specify a custom server URL:

```bash
uv run python -m p8fs_api.cli.device --base-url https://custom.server.com <command>
```

## Storage Location

All device credentials, JWT tokens, and keypairs are stored in:

```
~/.p8fs/auth/
├── token.json       # JWT tokens and device keys
└── device.json      # Device metadata
```

## Commands

### register

Register a new device and obtain JWT tokens.

**Usage:**
```bash
uv run python -m p8fs_api.cli.device register --email <email> [options]
```

**Options:**
- `--email EMAIL` (required): User email address
- `--device-name NAME`: Device display name (optional)
- `--tenant TENANT`: Tenant ID, use `test-tenant` for testing (optional)

**Examples:**

Register with production server:
```bash
uv run python -m p8fs_api.cli.device register --email user@example.com
```

Register with local dev server:
```bash
uv run python -m p8fs_api.cli.device --local register \
  --email dev@example.com \
  --tenant test-tenant \
  --device-name "My Dev Machine"
```

**How it works:**

1. Generates an Ed25519 keypair locally
2. Sends registration request with public key to server
3. For test-tenant or local server: Uses dev endpoint, returns tokens immediately
4. For production: Sends verification email, requires verification step
5. Saves tokens and keypair to `~/.p8fs/auth/token.json`

### approve

Approve a device authorization request using your registered device.

**Usage:**
```bash
uv run python -m p8fs_api.cli.device approve <user-code>
```

**Arguments:**
- `user-code`: The user code from QR scan (e.g., `A1B2-C3D4`)

**Example:**

Approve device with code from MCP login:
```bash
uv run python -m p8fs_api.cli.device approve 1A09-DE7E
```

**How it works:**

1. Reads your access token from `~/.p8fs/auth/token.json`
2. If token is expired, automatically refreshes it
3. Sends approval request to server with your credentials
4. Desktop/MCP client can now complete OAuth flow

**Integration with MCP:**

When Claude Desktop or MCP server initiates device flow:
1. User sees QR code with user code (e.g., `1A09-DE7E`)
2. Run `approve` command with that code
3. MCP client polls and receives tokens
4. Authentication complete

### ping

Test if your current token is valid.

**Usage:**
```bash
uv run python -m p8fs_api.cli.device ping
```

**Example:**
```bash
uv run python -m p8fs_api.cli.device ping
```

**Output:**
```
Testing token validity...
Using server: https://p8fs.eepis.ai
✓ Token is valid!
  Authenticated: True
  User ID: dev-0cabbbcc761a9ee1
  Email: dev@example.com
  Tenant ID: tenant-test
```

**How it works:**

1. Reads access token from storage
2. Sends request to `/oauth/ping` endpoint
3. Returns 0 if valid, 1 if invalid/expired

### refresh

Refresh your access token using the refresh token.

**Usage:**
```bash
uv run python -m p8fs_api.cli.device refresh
```

**Example:**
```bash
uv run python -m p8fs_api.cli.device refresh
```

**Output:**
```
Refreshing access token...
Using server: https://p8fs.eepis.ai
✓ Token refreshed successfully!
  New token expires in: 86400 seconds
```

**How it works:**

1. Reads refresh token from storage
2. Sends refresh request to `/oauth/token` endpoint
3. Updates stored tokens with new access token
4. Preserves device keys and metadata

**Note:** The `approve` command automatically refreshes expired tokens.

### status

Show device and token status.

**Usage:**
```bash
uv run python -m p8fs_api.cli.device status
```

**Example:**
```bash
uv run python -m p8fs_api.cli.device status
```

**Output:**
```
Device Status
==================================================
Status: Registered
Email: user@example.com
Tenant ID: tenant-abc123
Server: https://p8fs.eepis.ai
Token File: /Users/you/.p8fs/auth/token.json
Token: Valid ✓

Device Info:
  Device ID: dev-0cabbbcc761a9ee1
  Device Name: CLI Device
  Trust Level: EMAIL_VERIFIED
```

## Workflows

### First Time Setup (Production)

1. Register device:
```bash
uv run python -m p8fs_api.cli.device register --email user@example.com
```

2. Check email for verification code

3. Verify device (if prompted)

4. Test token:
```bash
uv run python -m p8fs_api.cli.device ping
```

### First Time Setup (Development)

1. Register with test tenant:
```bash
uv run python -m p8fs_api.cli.device --local register \
  --email dev@example.com \
  --tenant test-tenant
```

2. Tokens saved immediately, no verification needed

3. Test token:
```bash
uv run python -m p8fs_api.cli.device --local ping
```

### Approving MCP Device Flow

When using Claude Desktop or MCP server:

1. MCP client initiates OAuth flow
2. User sees QR code with user code (e.g., `1A09-DE7E`)
3. Run approval:
```bash
uv run python -m p8fs_api.cli.device approve 1A09-DE7E
```
4. MCP client completes authentication

### Token Maintenance

Check status periodically:
```bash
uv run python -m p8fs_api.cli.device status
```

If token expired:
```bash
uv run python -m p8fs_api.cli.device refresh
```

Or let `approve` handle it automatically.

## Authentication Flow

### Device Registration

```
┌─────────────────┐
│   CLI Device    │
└────────┬────────┘
         │ 1. Generate Ed25519 keypair
         │
         ▼
┌─────────────────┐
│   Local Disk    │  ~/.p8fs/auth/
│  (private key)  │
└─────────────────┘
         │ 2. Register with public key
         ▼
┌─────────────────┐
│  P8FS Server    │
│  (eepis.ai)     │
└────────┬────────┘
         │ 3. Return JWT tokens
         ▼
┌─────────────────┐
│   Local Disk    │  ~/.p8fs/auth/token.json
│  (JWT + keys)   │
└─────────────────┘
```

### Device Approval Flow

```
┌─────────────────┐      ┌─────────────────┐
│  MCP Client     │      │   CLI Device    │
│ (Claude Desktop)│      │  (Registered)   │
└────────┬────────┘      └────────┬────────┘
         │                        │
         │ 1. Initiate OAuth      │
         ▼                        │
┌─────────────────┐               │
│  P8FS Server    │               │
└────────┬────────┘               │
         │                        │
         │ 2. Return user code    │
         │    (e.g., 1A09-DE7E)   │
         ▼                        │
┌─────────────────┐               │
│      User       │               │
│  Sees QR Code   │               │
└────────┬────────┘               │
         │                        │
         │ 3. Run: approve 1A09-DE7E
         │◄───────────────────────┤
         │                        │
         │                        │ 4. Send approval
         │                        │    with JWT token
         │                        ▼
         │               ┌─────────────────┐
         │               │  P8FS Server    │
         │               └────────┬────────┘
         │                        │
         │ 5. MCP polls           │
         ├───────────────────────►│
         │                        │
         │ 6. Return tokens       │
         │◄───────────────────────┤
         │                        │
┌────────▼────────┐               │
│  MCP Client     │               │
│ (Authenticated) │               │
└─────────────────┘               │
```

## Security

### Key Storage

- **Private keys** stored in `~/.p8fs/auth/token.json`
- File permissions should be `0600` (user read/write only)
- Never share or commit this file

### Token Expiry

- Access tokens expire after configured period (default: 1 hour)
- Refresh tokens have longer lifetime (default: 7 days)
- Use `refresh` command to get new access token
- `approve` command auto-refreshes expired tokens

### Device Trust Levels

- `UNVERIFIED`: Initial registration state
- `EMAIL_VERIFIED`: After email verification
- `TRUSTED`: After additional verification
- `REVOKED`: Device access revoked

## Troubleshooting

### Token Expired

```bash
# Check status
uv run python -m p8fs_api.cli.device status

# Refresh token
uv run python -m p8fs_api.cli.device refresh
```

### Connection Error

```bash
# Check server is running
curl https://p8fs.eepis.ai/health

# For local development
curl http://localhost:8001/health
```

### Invalid Token

If refresh fails, re-register:

```bash
# Production
uv run python -m p8fs_api.cli.device register --email user@example.com

# Development
uv run python -m p8fs_api.cli.device --local register \
  --email dev@example.com \
  --tenant test-tenant
```

### Clear Stored Credentials

```bash
rm -rf ~/.p8fs/auth/
```

Then re-register.

## API Endpoints Used

The CLI interacts with these endpoints:

- **Dev Registration**: `POST /api/v1/auth/dev/register`
- **Standard Registration**: `POST /oauth/device/register`
- **Device Approval**: `POST /oauth/device/approve`
- **Token Refresh**: `POST /oauth/token` (grant_type=refresh_token)
- **Token Validation**: `GET /oauth/ping`

## Related Documentation

- [Authentication Flows](../../p8fs-auth/docs/authentication-flows.md)
- [OAuth 2.1 Compliance](../src/p8fs_api/routers/auth.py)
- [Device Storage](../../p8fs-auth/src/p8fs_auth/utils/device_storage.py)
