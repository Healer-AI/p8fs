# Device Authentication Flow - Development Testing Guide

## Overview

This document provides end-to-end testing examples for the email-based device registration and verification flow.

## Test Environment

- **API Endpoint**: `http://localhost:8001/api/v1/oauth`
- **Email Service**: Gmail SMTP (requires `EMAIL_PASSWORD` environment variable)
- **Email Subject**: "EEPIS Verification Code"
- **Code TTL**: 15 minutes (900 seconds)

## Complete Test Flow

### Step 1: Device Registration

**Endpoint**: `POST /api/v1/oauth/device/register`

**Request Payload**:
```json
{
  "email": "amartey@gmail.com",
  "public_key": "sQzY2MjI2NmYwNjYwNjYwNjI2NWY2NjI2NmEwNjU2NTY1",
  "device_info": {
    "device_name": "Test Device",
    "platform": "iOS",
    "version": "1.0",
    "imei": "123456789012345"
  }
}
```

**Response**:
```json
{
  "registration_id": "reg_Vc1dukZF0BO0vBT2wKRhjg",
  "message": "Verification code sent to email",
  "expires_in": 900
}
```

**What Happens**:
- Creates pending registration in KV storage with 15-minute TTL
- Generates random 6-digit verification code
- Sends email via Gmail SMTP to provided email address
- Email contains verification code valid for 15 minutes

**Email Content**:
- **Subject**: EEPIS Verification Code
- **Body**: HTML email with large, centered 6-digit code
- **Example Code**: `950217`

### Step 2: Email Verification

**Endpoint**: `POST /api/v1/oauth/device/verify`

**Request Payload**:
```json
{
  "registration_id": "reg_Vc1dukZF0BO0vBT2wKRhjg",
  "verification_code": "950217",
  "challenge_signature": "placeholder"
}
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJFUzI1NiIsImtpZCI6ImZpbGUta2V5IiwidHlwIjoiSldUIn0...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": null,
  "scope": null,
  "tenant_id": "tenant-f3438e64eebfd8d16b78170de002f532"
}
```

**What Happens**:
1. Retrieves pending registration from KV storage using `registration_id`
2. Verifies the 6-digit code matches
3. Creates Device with `EMAIL_VERIFIED` trust level
4. Creates or retrieves Tenant:
   - **With IMEI**: Deterministic tenant ID based on `SHA256(imei)`
   - **Without IMEI**: Random tenant ID (logs warning)
5. Generates JWT access token with ES256 signing
6. Creates sample data for new tenant (5 moments, 10 sessions)
7. Cleans up pending registration from KV storage

## JWT Token Details

### Decoding the Token

**Command**:
```bash
echo 'TOKEN_HERE' | cut -d'.' -f2 | base64 -d | python3 -m json.tool
```

**Decoded Payload Example**:
```json
{
  "iss": "p8fs-auth",
  "aud": "p8fs-api",
  "exp": 1761929636,
  "iat": 1761926036,
  "jti": "934b744d-4930-48d4-94dc-b3582454b0ae",
  "sub": "device-c9bc2e208343f41b624637c3d0f23cdf",
  "user_id": "device-c9bc2e208343f41b624637c3d0f23cdf",
  "client_id": "mobile_device",
  "scope": "read write",
  "device_id": "device-c9bc2e208343f41b624637c3d0f23cdf",
  "kid": "file-key",
  "email": "amartey@gmail.com",
  "tenant": "tenant-f3438e64eebfd8d16b78170de002f532",
  "device_name": "Test Device"
}
```

**Token Claims**:
- **iss**: Issuer (`p8fs-auth`)
- **aud**: Audience (`p8fs-api`)
- **sub**: Subject (device ID)
- **email**: Verified email address
- **tenant**: Tenant ID (deterministic with IMEI, random without)
- **device_id**: Unique device identifier
- **device_name**: Human-readable device name
- **scope**: Access scopes (`read write`)
- **exp**: Expiration timestamp (1 hour from issuance)

## Testing with cURL

### Full Flow with cURL

```bash
# Step 1: Register device
RESPONSE=$(curl -s -X POST http://localhost:8001/api/v1/oauth/device/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your-email@gmail.com",
    "public_key": "sQzY2MjI2NmYwNjYwNjYwNjI2NWY2NjI2NmEwNjU2NTY1",
    "device_info": {
      "device_name": "Test Device",
      "platform": "test",
      "version": "1.0"
    }
  }')

echo "Registration Response:"
echo $RESPONSE | python3 -m json.tool

# Extract registration_id
REGISTRATION_ID=$(echo $RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['registration_id'])")

echo ""
echo "Registration ID: $REGISTRATION_ID"
echo ""
echo "Check your email for the verification code, then enter it:"
read VERIFICATION_CODE

# Step 2: Verify with code
curl -s -X POST http://localhost:8001/api/v1/oauth/device/verify \
  -H "Content-Type: application/json" \
  -d "{
    \"registration_id\": \"$REGISTRATION_ID\",
    \"verification_code\": \"$VERIFICATION_CODE\",
    \"challenge_signature\": \"placeholder\"
  }" | python3 -m json.tool
```

## Device Info Metadata

### Standard Fields

The `device_info` object stores device metadata and supports these fields:

```json
{
  "device_name": "iPhone 15 Pro",
  "platform": "iOS",
  "version": "1.0.0",
  "imei": "123456789012345",
  "model": "iPhone15,2",
  "os_version": "17.2",
  "app_version": "1.0.0"
}
```

### IMEI for Tenant Determinism

**With IMEI**:
```python
# Tenant ID is deterministic based on IMEI hash
tenant_id = f"tenant-{SHA256(imei)[:16]}"
# Same IMEI always produces same tenant
# Allows device replacement/re-registration
```

**Without IMEI**:
```python
# Tenant ID is random
tenant_id = f"tenant-{random_hex(16)}"
# Each registration creates new tenant
# Logs WARNING: "No IMEI provided for device {device_id}, using random tenant ID"
```

## Error Scenarios

### Invalid or Expired Code

**Request**:
```json
{
  "registration_id": "reg_Vc1dukZF0BO0vBT2wKRhjg",
  "verification_code": "000000",
  "challenge_signature": "placeholder"
}
```

**Response** (400):
```json
{
  "error": "http_error_400",
  "message": "Verification failed: Invalid verification code"
}
```

### Registration Not Found

**Request**:
```json
{
  "registration_id": "reg_InvalidID",
  "verification_code": "123456",
  "challenge_signature": "placeholder"
}
```

**Response** (400):
```json
{
  "error": "http_error_400",
  "message": "Verification failed: Registration not found or expired"
}
```

### Code Expired (After 15 minutes)

**Response** (400):
```json
{
  "error": "http_error_400",
  "message": "Verification failed: Verification code expired"
}
```

## Email Configuration

### Environment Variables

```bash
# Required for email sending
export EMAIL_PASSWORD="your-gmail-app-password"

# Optional email settings (defaults shown)
export P8FS_EMAIL_ENABLED=true
export P8FS_EMAIL_PROVIDER=gmail
export P8FS_EMAIL_SMTP_SERVER=smtp.gmail.com
export P8FS_EMAIL_SMTP_PORT=587
export P8FS_EMAIL_USERNAME=saoirse@dreamingbridge.io
```

### Honest Error Messages

The system returns honest messages about email sending:

**Email Sent Successfully**:
```json
{
  "message": "Verification code sent to email"
}
```

**Development Mode (No Email Configured)**:
```json
{
  "message": "Registration created (email not configured - code in response)",
  "verification_code": "950217"
}
```

**Production Mode (No Email Configured)**:
```json
{
  "error": "Email service not configured - cannot send verification code. Set EMAIL_PASSWORD environment variable."
}
```

## Server Logs

### Successful Registration

```
INFO: Pending registration created: reg_Vc1dukZF0BO0vBT2wKRhjg email=amartey@gmail.com
INFO: Email sent successfully to amartey@gmail.com
INFO: Verification code sent to amartey@gmail.com
```

### Successful Verification

```
WARNING: No IMEI provided for device device-c9bc2e208343f41b624637c3d0f23cdf, using random tenant ID
INFO: Tenant created: tenant-f3438e64eebfd8d16b78170de002f532 email=amartey@gmail.com method=random
INFO: Sample data initialized for new tenant tenant-f3438e64eebfd8d16b78170de002f532: 5 moments, 10 sessions
INFO: Device verified from pending registration: device-c9bc2e208343f41b624637c3d0f23cdf tenant=tenant-f3438e64eebfd8d16b78170de002f532 email=amartey@gmail.com
```

## Key Implementation Files

- **Device Model**: `p8fs-auth/src/p8fs_auth/models/auth.py:34`
  - Added `metadata` field for device info storage

- **Mobile Service**: `p8fs-auth/src/p8fs_auth/services/mobile_service.py`
  - `register_device()` - Creates pending registration (line 138)
  - `verify_pending_registration()` - Completes verification (line 222)
  - `_create_tenant_from_device()` - IMEI-based tenant creation (line 320)

- **Auth Controller**: `p8fs-api/src/p8fs_api/controllers/auth_controller.py`
  - `register_device()` - Registration endpoint (line 222)
  - `verify_registration()` - Verification endpoint (line 255)

- **Email Service**: `p8fs/src/p8fs/services/email/email_service.py:47`
  - `send_verification_code()` - Sends EEPIS verification email

- **Response Models**: `p8fs-api/src/p8fs_api/models/responses.py:29`
  - `AuthTokenResponse` - Includes `tenant_id` for backwards compatibility

## Changes in v1.1.35

1. **Email Integration**: Wired EmailService into device registration flow
2. **Honest Error Messaging**: Returns accurate status about email sending
3. **Metadata Field**: Added `metadata` to Device model for IMEI and device info
4. **Brand Update**: Changed email subject from "P8FS" to "EEPIS"
5. **Backwards Compatibility**: Added `tenant_id` to auth token response
6. **Verification Flow**: Implemented `verify_pending_registration()` for complete flow
