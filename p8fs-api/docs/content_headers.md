# Content Headers

The following content headers can be sent on any payload to identify users, devices and original content.

## Header Reference

| Header Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| **User Context** | | | |
| `X-User-Source-ID` | Unique identifier for the user | `user-123e4567-e89b-12d3-a456-426614174000` | No |
| `X-User-Email` | User's email address | `alice@example.com` | No |
| `X-User-Name` | User's display name | `Alice Smith` | No |
| `X-User-Role` | User's role or permission level | `admin`, `editor`, `viewer` | No |
| `X-User-Organization` | User's organization or team | `Engineering Team` | No |
| **Device Context** | | | |
| `X-Device-Info` | JSON object with device properties | `{"location": {"lat": 37.7749, "lng": -122.4194}, "accelerometer": {"x": 0.1, "y": 0.2, "z": 9.8}}` | No |
| `X-Device-ID` | Unique device identifier | `device-abc123def456`, `550e8400-e29b-41d4-a716-446655440000` | No |
| `X-Device-Type` | Type of device | `mobile`, `desktop`, `tablet`, `iot` | No |
| `X-Device-Platform` | Operating system or platform | `iOS`, `Android`, `Windows`, `macOS`, `Linux` | No |
| `X-Device-Version` | Device OS version | `iOS 17.0`, `Android 13` | No |
| `X-Device-Model` | Device hardware model | `iPhone15,2` (iPhone 14 Pro), `SM-S918B` (Galaxy S23 Ultra) | No |
| `X-App-Version` | Client application version | `1.2.3` | No |
| `X-OS-Version` | Detailed OS version | `17.2.1`, `14.0.0` | No |
| `X-Platform` | Simplified platform name | `iOS`, `Android`, `Web` | No |
| **Mobile App Specific** | | | |
| `X-Biometric-Available` | Device biometric capability | `true`, `false` | No |
| `X-Secure-Enclave` | Hardware security module available | `true`, `false` | No |
| `X-Push-Token` | Push notification token | `fcm:abc123...`, `apns:def456...` | No |
| **Authentication Context** | | | |
| `Authorization` | Bearer token for API authentication | `Bearer p8fs_at_eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...` | Yes* |
| `X-Tenant-ID` | Tenant identifier | `tenant_12345678` | No |
| `X-Session-ID` | Session identifier | `session_abc123def456` | No |
| **Browser Headers (Standard)** | | | |
| `User-Agent` | Browser/app identification string | See examples below | Yes |
| `Accept` | Acceptable content types | `application/json`, `text/html`, `*/*` | Yes |
| `Accept-Language` | Preferred languages | `en-US,en;q=0.9`, `es-ES,es;q=0.8` | No |
| `Accept-Encoding` | Acceptable encodings | `gzip, deflate, br` | No |
| `Referer` | Previous page URL | `https://app.p8fs.io/files` | No |
| `Origin` | Request origin | `https://app.p8fs.io` | No** |
| **Content Source** | | | |
| `X-Content-Source-ID` | Original document or content ID | `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms` | No |
| `X-Content-Source-URL` | Public URL to access original content | `https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms` | No |
| `X-Content-Source-Provider` | Source provider or service | `GOOGLE_DRIVE`, `ICLOUD`, `BOX`, `DROPBOX`, `ONEDRIVE` | No |
| `X-Content-Source-Type` | Type of source content | `document`, `spreadsheet`, `presentation`, `image`, `video` | No |
| `X-Content-Source-Version` | Version of the source content | `v1.2`, `rev-123` | No |
| `X-Content-Source-Modified` | Last modified timestamp of source | `2024-01-15T10:30:00Z` | No |
| **Content Classification** | | | |
| `X-Content-Type` | MIME type of content | `application/pdf`, `text/plain`, `image/jpeg` | No |
| `X-Content-Language` | Language of the content | `en-US`, `es-ES`, `fr-FR` | No |
| `X-Content-Encoding` | Content encoding method | `gzip`, `deflate`, `br` | No |
| `X-Content-Sensitivity` | Data sensitivity level | `public`, `internal`, `confidential`, `restricted` | No |
| `X-Content-Tags` | Comma-separated content tags | `meeting-notes,project-alpha,urgent` | No |
| `X-Content-Category` | Content category | `documents`, `media`, `code`, `data` | No |
| **Processing Context** | | | |
| `X-Processing-Context` | Processing context or workflow | `ocr-extraction`, `transcription`, `analysis` | No |
| `X-Processing-Priority` | Processing priority level | `high`, `medium`, `low` | No |
| `X-Processing-Deadline` | Processing deadline | `2024-01-20T15:00:00Z` | No |
| `X-Processing-Options` | JSON processing options | `{"extract_text": true, "generate_thumbnail": true}` | No |
| **Security Context** | | | |
| `X-Encryption-Key-ID` | Encryption key identifier | `key-abc123def456` | No |
| `X-Signature` | Content signature for integrity | `SHA256:abc123def456...` | No |
| `X-Access-Token` | OAuth or access token for source | `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` | No |
| `X-Audit-ID` | Audit trail identifier | `audit-789xyz123` | No |
| `X-TTL` | Time-to-live in seconds | `3600` (1 hour), `86400` (24 hours) | No |
| **Workflow Context** | | | |
| `X-Workflow-ID` | Workflow or process identifier | `workflow-456def789` | No |
| `X-Workflow-Step` | Current step in workflow | `extract`, `analyze`, `store` | No |
| `X-Workflow-Parent` | Parent workflow or request ID | `parent-123abc456` | No |
| `X-Batch-ID` | Batch processing identifier | `batch-2024-01-15-001` | No |
| **Chat/Conversation Context** | | | |
| `X-Chat-Is-Audio` | Indicates audio input in chat completions | `true`, `false` | No |

## Notes

* **Authorization**: Required for authenticated endpoints. Not required for public endpoints like health checks.
** **Origin**: Required for CORS requests from browsers. Mobile apps typically don't send this.

## User-Agent Examples

### Browser User-Agents
```
# Desktop Chrome on macOS
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36

# Mobile Safari on iPhone
Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1

# Firefox on Windows
Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0
```

### Mobile App User-Agents
```
# P8FS iOS App
P8FS/1.0 iOS/17.2

# P8FS Android App
P8FS/1.0 Android/14.0

# P8-Node Desktop
P8-Node/1.0.0 (Darwin 23.2.0)
```

## Browser vs Mobile App Headers

### Key Differences
| Aspect | Browser | Mobile App |
|--------|---------|------------|
| User-Agent | Complex Mozilla string | Simple app identifier |
| Custom Headers | ❌ Not available | ✅ X-Device-Model, X-Device-ID, etc. |
| Device Info | Limited to User-Agent parsing | Full device details via headers |
| Authentication | Cookies + Bearer tokens | Bearer tokens only |
| CORS Headers | Origin, Referer sent | Usually not sent |
| Persistent ID | Must use cookies/localStorage | X-Device-ID header |

## Usage Examples

### Mobile App Registration
```http
POST /api/v1/auth/register
Content-Type: application/json
User-Agent: P8FS/1.0 iOS/17.2
X-Device-Model: iPhone15,2
X-Device-ID: 550e8400-e29b-41d4-a716-446655440000
X-App-Version: 1.0.0
X-Platform: iOS
X-OS-Version: 17.2.1
X-Biometric-Available: true
X-Secure-Enclave: true

{
  "email": "user@example.com",
  "public_key": "YPNErrgftPwi1RecvJ2HThX5SvJbEiMvKyG8eGqJRoI=",
  "device_info": {
    "name": "John's iPhone",
    "model": "iPhone 14 Pro"
  }
}
```

### Desktop OAuth Device Authorization
```http
POST /oauth/device/code
Content-Type: application/x-www-form-urlencoded
User-Agent: P8-Node/1.0.0 (Darwin 23.2.0)
X-Device-Type: desktop
X-Platform: macOS
X-App-Version: 1.0.0

client_id=p8-node-desktop&scope=read+write+sync
```

### Browser File Upload
```http
POST /api/v1/files
Content-Type: multipart/form-data
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Accept: application/json
Accept-Language: en-US,en;q=0.9
Origin: https://app.p8fs.io
Referer: https://app.p8fs.io/upload
Authorization: Bearer p8fs_at_eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...
X-User-Email: alice@example.com
X-Content-Tags: meeting-notes,project-alpha

[file data]
```

### Basic File Upload (Mobile App)
```http
POST /api/v1/files
Content-Type: multipart/form-data
User-Agent: P8FS/1.0 Android/14.0
Authorization: Bearer p8fs_at_eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...
X-Device-Model: SM-S918B
X-Device-ID: 660e8400-a41d-e29b-4716-446655440000
X-User-Email: alice@example.com
X-Device-Type: mobile
X-Content-Type: application/pdf
X-Content-Tags: meeting-notes,project-alpha

[file data]
```

### Google Drive Document Import
```http
POST /api/v1/import
Content-Type: application/json
X-User-Source-ID: user-123e4567-e89b-12d3-a456-426614174000
X-Content-Source-Provider: GOOGLE_DRIVE
X-Content-Source-ID: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
X-Content-Source-URL: https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
X-Access-Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### IoT Device Data Upload
```http
POST /api/v1/sensor-data
Content-Type: application/json
X-Device-ID: sensor-abc123def456
X-Device-Type: iot
X-Device-Platform: Arduino
X-Device-Info: {"location": {"lat": 37.7749, "lng": -122.4194}, "temperature": 23.5}
X-Content-Category: data
X-Processing-Priority: high
X-TTL: 3600
```

### Batch Processing
```http
POST /api/v1/batch
Content-Type: application/json
X-Batch-ID: batch-2024-01-15-001
X-Workflow-ID: ocr-workflow-456
X-Processing-Context: ocr-extraction
X-Processing-Options: {"extract_text": true, "generate_thumbnail": true}
```

### Chat Completions with Audio Input
```http
POST /api/v1/chat/completions
Content-Type: application/json
Authorization: Bearer p8fs_at_eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...
X-Chat-Is-Audio: true
X-Device-Type: mobile
X-Platform: iOS

{
  "model": "gpt-4",
  "messages": [
    {
      "role": "user",
      "content": "UklGRiQFAABXQVZFZm10IBAAAAABAAEA..."  // Base64 encoded WAV audio
    }
  ],
  "stream": true
}
```

When `X-Chat-Is-Audio: true` is present, the first user message content should be intercepted and processed as base64-encoded WAV audio data. The audio is transcribed to text before being passed to the chat completion handler.

## Header Validation

- All headers are optional unless specified otherwise
- Headers starting with `X-` are custom headers for P8FS
- JSON values in headers must be valid JSON strings
- Timestamps should be in ISO 8601 format (UTC)
- Provider names should be uppercase with underscores
- Content sensitivity levels: `public`, `internal`, `confidential`, `restricted`
- Processing priorities: `high`, `medium`, `low`
- TTL values should be positive integers representing seconds

## Security Considerations

- Never include sensitive information in headers that might be logged
- Use `X-Access-Token` for authentication tokens, not in URL parameters
- Encrypt sensitive device information in `X-Device-Info`
- Validate all header values on the server side
- Consider rate limiting based on device/user headers

## Device Detection Implementation

### FastAPI Middleware Example
```python
from fastapi import Request

async def extract_device_info(request: Request):
    """Extract device information from request headers."""
    headers = request.headers
    
    # Check for mobile app headers first
    if headers.get("x-device-model") or headers.get("x-device-id"):
        return {
            "type": "mobile_app",
            "model": headers.get("x-device-model"),
            "device_id": headers.get("x-device-id"),
            "platform": headers.get("x-platform"),
            "app_version": headers.get("x-app-version"),
        }
    else:
        # Parse User-Agent for browser info
        user_agent = headers.get("user-agent", "")
        return {
            "type": "browser",
            "user_agent": user_agent,
            # Additional parsing logic here
        }
```

### Key Points
1. **Browsers cannot send custom X-* headers** - they are restricted by browser security
2. **Only native mobile apps** can send device-specific headers
3. **User-Agent parsing** is required for browser device detection
4. **Device ID persistence** - Mobile apps generate and store a UUID, browsers must use cookies/localStorage
5. **CORS considerations** - Browsers send Origin/Referer, mobile apps typically don't

