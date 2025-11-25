# P8FS Development Scripts

This directory contains development scripts for working with P8FS authentication and MCP.

## Scripts

### get_dev_jwt.py
Generates development JWT tokens with device keypairs for P8FS API access.

```bash
# Generate token for default email (testing@percolationlabs.ai)
python get_dev_jwt.py

# Generate token for custom email
python get_dev_jwt.py --email user@example.com

# Save to custom location
python get_dev_jwt.py -o custom_token.json

# Test message signing
python get_dev_jwt.py --test-sign
```

**What it does:**
1. Generates Ed25519 keypair for device identity
2. Registers device with P8FS using dev token
3. Gets JWT access token
4. Saves everything to `~/.p8fs/auth/token.json`

### dev_device_approve.py
Simulates mobile device approval for OAuth device authorization flow.

```bash
# Auto-detect and approve from QR login page (default)
python dev_device_approve.py

# Explicitly auto-detect from QR page
python dev_device_approve.py --detect

# Approve specific user code
python dev_device_approve.py --user-code 1A09-DE7E

# Auto-approve first pending request
python dev_device_approve.py --auto

# List pending authorization requests
python dev_device_approve.py --list

# Use with custom port (defaults to 8001)
python dev_device_approve.py --port 8000

# Or specify full URL
python dev_device_approve.py --url http://localhost:8000
```

**What it does:**
1. Uses saved device keys from `get_dev_jwt.py`
2. Can automatically detect active device authorization from QR login page
3. Parses JSON metadata from meta tag for complete automation
4. Signs approval with device private key
5. Approves pending device authorization requests
6. Simulates what happens when user scans QR code on mobile

**Auto-detection feature:**
- When run without arguments, automatically checks the device verification page
- Extracts user code from JSON metadata in `<meta name="p8fs-device-auth">` tag
- Defaults to port 8001 (standard p8fs-api port)
- Falls back to trying ports 8000 if 8001 doesn't work
- Enables one-command approval for OAuth device flow

### test_device_flow.py
End-to-end test of the complete OAuth device authorization flow.

```bash
# Run complete flow test
python test_device_flow.py
```

**What it demonstrates:**
1. Device authorization initiation
2. Automatic approval simulation
3. Token polling and retrieval
4. Using OAuth token with MCP

### generate_server_jwt_signing_keys.py
Generates JWT signing keys for the P8FS server.

```bash
# Generate new signing keys
python generate_server_jwt_signing_keys.py

# Save to custom file
python generate_server_jwt_signing_keys.py -o custom_keys.json
```

## Development Workflow

### 1. Initial Setup
```bash
# Set dev token environment variable
export P8FS_DEV_TOKEN_SECRET='p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58'

# Generate dev credentials
python get_dev_jwt.py
```

### 2. Testing OAuth Device Flow
```bash
# In one terminal, initiate device flow
curl -X POST http://localhost:8000/api/v1/oauth/device_authorization \
  -d "client_id=mcp_client&scope=read write"

# In another terminal, approve the request
python dev_device_approve.py --user-code <USER-CODE>

# Or run the complete test
python test_device_flow.py
```

### 3. Testing MCP with OAuth
```bash
# Add MCP server to Claude
claude mcp add -t http p8fs-mcp http://localhost:8000/api/mcp

# The QR login page will be available at:
# http://localhost:8000/api/mcp/auth/qr-login

# Or test programmatically with device flow
python test_device_flow.py
```

## Token Storage

Tokens and keys are stored in `~/.p8fs/auth/token.json`:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "tenant_id": "tenant-...",
  "device_keys": {
    "private_key_pem": "-----BEGIN PRIVATE KEY-----...",
    "public_key_pem": "-----BEGIN PUBLIC KEY-----...",
    "public_key_b64": "..."
  }
}
```

## Security Notes

- The dev token secret is for development only
- Device private keys should be kept secure
- Tokens expire and need to be refreshed
- Production should use proper OAuth flow with mobile app