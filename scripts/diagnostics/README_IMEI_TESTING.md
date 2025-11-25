# IMEI-Based Deterministic Tenant ID Testing

This directory contains scripts to verify that device registration with IMEI produces deterministic tenant IDs.

## Overview

The P8FS authentication system supports IMEI-based tenant ID generation:
- Devices with the same IMEI get the same tenant ID
- Devices without IMEI get random tenant IDs
- Tenant ID is computed as: `tenant-{SHA256(imei)[:16]}`

## Scripts

### 1. Local Testing: `verify_imei_tenant_local.py`

Tests IMEI-based tenant IDs using local database (PostgreSQL or TiDB).

**Usage:**
```bash
# With PostgreSQL
P8FS_STORAGE_PROVIDER=postgresql uv run python scripts/diagnostics/verify_imei_tenant_local.py

# With TiDB
P8FS_STORAGE_PROVIDER=tidb uv run python scripts/diagnostics/verify_imei_tenant_local.py
```

**Requirements:**
- Local PostgreSQL or TiDB running
- P8FS_STORAGE_PROVIDER environment variable set

**What it tests:**
- ✅ Device 1 with IMEI creates expected tenant ID
- ✅ Device 2 with same IMEI reuses same tenant
- ✅ Device 3 without IMEI gets random tenant

### 2. Remote Testing: `verify_imei_tenant_remote.py`

Tests IMEI-based tenant IDs on a remote server using production OAuth flow with email verification.

**Step 1: Register devices (sends verification emails)**
```bash
uv run python scripts/diagnostics/verify_imei_tenant_remote.py register \
  --server https://p8fs.eepis.ai \
  --email your@email.com
```

**Step 2: Verify with codes from email**
```bash
uv run python scripts/diagnostics/verify_imei_tenant_remote.py verify \
  CODE1 CODE2 CODE3
```

**Environment Variables:**
- `REMOTE_SERVER`: Server URL (default: https://p8fs.eepis.ai)
- `USER_EMAIL`: Email for verification (can use --email flag instead)

**What it tests:**
- ✅ Device 1 with IMEI creates expected tenant ID on remote server
- ✅ Device 2 with same IMEI reuses same tenant on remote server
- ✅ Device 3 without IMEI gets random tenant on remote server

### 3. Dev Endpoint Testing: `verify_imei_tenant_dev.py`

⚠️ **NOTE**: The dev endpoint does NOT use IMEI-based tenant IDs. It uses the default `tenant-test` for development convenience.

**Usage:**
```bash
# Test local server
uv run python scripts/diagnostics/verify_imei_tenant_dev.py \
  --server http://localhost:8000

# Test remote server
uv run python scripts/diagnostics/verify_imei_tenant_dev.py \
  --server https://p8fs.eepis.ai
```

**Environment Variables:**
- `P8FS_DEV_TOKEN`: Dev token (default from settings.py)
- `DEV_TOKEN_SECRET`: Alternative name for dev token

**Default dev token:**
```
p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58
```

Found in: `p8fs-cluster/src/p8fs_cluster/config/settings.py`

## How IMEI-Based Tenant IDs Work

### Code Location
`p8fs-auth/src/p8fs_auth/services/mobile_service.py:350-363`

### Algorithm
```python
import hashlib

# 1. Extract IMEI from device metadata
device_imei = device.metadata.get("imei")

if device_imei:
    # 2. Hash IMEI with SHA-256
    hash_value = hashlib.sha256(device_imei.encode()).hexdigest()[:16]

    # 3. Create deterministic tenant ID
    tenant_id = f"tenant-{hash_value}"
else:
    # 4. Generate random tenant ID if no IMEI
    import secrets
    random_value = secrets.token_hex(16)
    tenant_id = f"tenant-{random_value}"
```

### Example Calculation

**Input IMEI:** `999888777666555`

**Step 1: SHA-256 Hash**
```
Full hash: 0d9ba3ed4679da3e8a2a2f588a425315741f39dce7c3c09e1bc88793b72170c4
```

**Step 2: Take first 16 characters**
```
0d9ba3ed4679da3e
```

**Step 3: Create tenant ID**
```
tenant-0d9ba3ed4679da3e
```

## Registration Payload

To register a device with IMEI:

```json
{
  "email": "user@example.com",
  "public_key": "<base64-encoded-Ed25519-public-key>",
  "device_info": {
    "platform": "iOS",
    "model": "iPhone 15",
    "imei": "999888777666555",  ← This creates deterministic tenant
    "device_name": "My Device"
  }
}
```

The `device_info.imei` field is what drives the deterministic tenant ID generation.

## Endpoints

### Production Flow (uses IMEI)
1. **POST** `/api/v1/oauth/device/register` - Register device
2. **POST** `/api/v1/oauth/device/verify` - Verify with email code

### Dev Flow (does NOT use IMEI)
- **POST** `/api/v1/auth/dev/register` - Dev registration (returns tenant-test)

## Testing Results

### Local Tests ✅
```
Device 1 (IMEI: 123456789012345) → tenant-e27a7686b8028cfe
Device 2 (IMEI: 123456789012345) → tenant-e27a7686b8028cfe ✅ Same
Device 3 (No IMEI)               → tenant-<random>         ✅ Different
```

### Remote Tests (p8fs.eepis.ai) ✅
```
Device 1 (IMEI: 999888777666555) → tenant-0d9ba3ed4679da3e
Device 2 (IMEI: 999888777666555) → tenant-0d9ba3ed4679da3e ✅ Same
Device 3 (No IMEI)               → tenant-<random>         ✅ Different
```

## Troubleshooting

### "No module named 'httpx'"
Install dependencies:
```bash
pip install httpx cryptography
```

Or use uv (recommended):
```bash
uv run python scripts/diagnostics/verify_imei_tenant_remote.py ...
```

### "Dev token not found"
Set environment variable:
```bash
export P8FS_DEV_TOKEN="p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58"
```

Or the script will use the default from settings.py.

### "Database connection failed"
For local testing, ensure PostgreSQL or TiDB is running:
```bash
cd p8fs
docker-compose up postgres -d
```

### Email verification codes not received
- Check spam folder
- Ensure email service is configured on remote server
- For local testing, verification codes are returned in response in dev mode

## References

- Implementation: `p8fs-auth/src/p8fs_auth/services/mobile_service.py`
- Tests: `p8fs-auth/tests/integration/test_device_token_claims.py`
- Config: `p8fs-cluster/src/p8fs_cluster/config/settings.py`
