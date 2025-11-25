# P8FS XStorage - Cloud Storage Provider Integration

## Overview

XStorage provides OAuth-based integration with popular cloud storage providers, enabling users to sync files from their cloud accounts to P8FS for indexing while maintaining links to original sources. Files are processed and indexed but not permanently stored, only summaries and metadata are retained.

## Architecture

### Core Principles

1. **User-Device Execution**: OAuth flows run on user's device for security
2. **Selective Sync**: Users choose folders to watch/sync
3. **Index-Only Storage**: Process files for indexing, store only summaries
4. **Source Linking**: Maintain links to original documents in cloud storage
5. **MCP Integration**: OAuth flows exposed via Model Context Protocol

### Provider Support

- iCloud Drive
- Google Drive  
- Dropbox
- Box
- OneDrive
- Others (extensible architecture)

## Implementation Strategy

### Base Provider Interface

```python
class CloudStorageProvider(ABC):
    @abstractmethod
    async def authenticate(self, redirect_uri: str) -> AuthResult
    @abstractmethod
    async def list_folders(self, access_token: str) -> List[Folder]
    @abstractmethod
    async def watch_folder(self, folder_id: str, webhook_url: str) -> WatchResult
    @abstractmethod
    async def download_file(self, file_id: str, access_token: str) -> AsyncIterator[bytes]
    @abstractmethod
    async def get_file_link(self, file_id: str) -> str
```

## Provider-Specific Implementation Plans

### Google Drive

**OAuth Setup Requirements:**
- Google Cloud Console project
- OAuth 2.0 Client ID (Web Application type)
- Authorized redirect URIs
- Drive API enabled
- Scopes: `drive.readonly`, `drive.metadata.readonly`

**Implementation Approach:**
1. Use Google's OAuth 2.0 flow with PKCE
2. Store refresh tokens encrypted with user's key
3. Use Drive API v3 for file operations
4. Implement push notifications via Google Drive Push Notifications API
5. Use `changes.watch` for folder monitoring

**What We Need From Users:**
- Google account authorization
- Folder selection for syncing
- Sync frequency preferences

**Best Practices:**
- Use incremental sync with change tokens
- Batch API requests for efficiency
- Handle rate limiting with exponential backoff
- Use fields parameter to minimize data transfer

### iCloud Drive

**OAuth Setup Requirements:**
- Apple Developer account
- Sign in with Apple configuration
- CloudKit container
- iCloud Drive entitlements

**Implementation Approach:**
1. Use Sign in with Apple for authentication
2. CloudKit JS for web-based access
3. CloudKit Web Services for server operations
4. File Provider Extension for native sync

**What We Need From Users:**
- Apple ID authorization
- iCloud Drive folder access permissions
- Two-factor authentication completion

**Best Practices:**
- Use CloudKit subscriptions for change notifications
- Implement proper error handling for 2FA
- Cache authentication tokens securely
- Handle iCloud rate limits gracefully

### Dropbox

**OAuth Setup Requirements:**
- Dropbox App Console registration
- OAuth 2.0 App Key and Secret
- Redirect URLs configuration
- Scopes: `files.metadata.read`, `files.content.read`

**Implementation Approach:**
1. OAuth 2.0 with PKCE flow
2. Use Dropbox API v2
3. Implement webhook notifications
4. Use cursor-based pagination for large folders

**What We Need From Users:**
- Dropbox account authorization
- Folder path selection
- Webhook endpoint (auto-configured)

**Best Practices:**
- Use Dropbox Paper API for document previews
- Implement selective sync with path filters
- Use batch operations for multiple files
- Handle team folders appropriately

### Box

**OAuth Setup Requirements:**
- Box Developer account
- Box Application creation
- OAuth 2.0 credentials
- Application scope configuration

**Implementation Approach:**
1. Box OAuth 2.0 with JWT or standard flow
2. Use Box Events API for change tracking
3. Implement webhook notifications
4. Use Box View API for document previews

**What We Need From Users:**
- Box account authorization
- Folder selection via Box Picker
- Collaboration permissions

**Best Practices:**
- Use Box Skills for metadata extraction
- Implement proper token refresh logic
- Use representation API for previews
- Handle enterprise restrictions

### OneDrive

**OAuth Setup Requirements:**
- Azure AD app registration
- Microsoft Graph API permissions
- Redirect URI configuration
- Scopes: `Files.Read`, `Files.Read.All`

**Implementation Approach:**
1. Microsoft Identity Platform OAuth 2.0
2. Use Microsoft Graph API
3. Implement delta queries for changes
4. Use webhooks via Graph subscriptions

**What We Need From Users:**
- Microsoft account authorization
- OneDrive folder selection
- Personal vs Business account type

**Best Practices:**
- Use delta tokens for efficient sync
- Implement resumable downloads
- Handle throttling with retry-after
- Support both personal and business accounts

## MCP Integration

### OAuth Flow via MCP

```typescript
// MCP method definition
{
  name: "xstorage.authenticate",
  description: "Initiate OAuth flow for cloud storage provider",
  parameters: {
    provider: "gdrive" | "icloud" | "dropbox" | "box" | "onedrive",
    scopes: string[],
    redirect_uri: string
  },
  returns: {
    auth_url: string,
    state: string,
    code_verifier?: string  // for PKCE
  }
}

{
  name: "xstorage.complete_auth",
  description: "Complete OAuth flow with authorization code",
  parameters: {
    provider: string,
    code: string,
    state: string,
    code_verifier?: string
  },
  returns: {
    access_token: string,
    refresh_token?: string,
    expires_in: number
  }
}
```

## Sync Architecture

### Workflow

1. **Initial Setup**
   - User authorizes via MCP OAuth flow
   - Select folders to watch
   - Configure sync preferences

2. **Continuous Sync**
   - Monitor selected folders for changes
   - Download new/modified files
   - Process through p8fs-node content providers
   - Store summaries and metadata
   - Delete local copy after processing

3. **Access Pattern**
   - User searches indexed content
   - Results show summaries with source links
   - Click-through opens original in cloud provider

### Data Flow

```
Cloud Provider → OAuth → File Download → Content Processing → Index Storage → Summary Display
                                              ↓                      ↓
                                         Delete Local           Keep Source Link
```

## Security Considerations

1. **Token Storage**
   - Encrypt refresh tokens with user's p8fs encryption key
   - Store in secure keychain/credential manager
   - Implement token rotation

2. **Data Privacy**
   - Process files in memory when possible
   - Clear temporary files immediately
   - Don't log file contents

3. **Access Control**
   - Respect cloud provider permissions
   - Implement least-privilege scopes
   - Regular permission audits

## Error Handling

1. **Authentication Errors**
   - Token expiration → Auto-refresh
   - Revoked access → Re-authenticate
   - Rate limiting → Backoff strategy

2. **Sync Errors**
   - Network failures → Retry queue
   - File conflicts → User resolution
   - Quota exceeded → User notification

## Performance Optimization

1. **Batch Operations**
   - Group API calls where possible
   - Use provider-specific batch endpoints
   - Implement request pooling

2. **Incremental Sync**
   - Track last sync timestamps
   - Use change tokens/cursors
   - Skip unchanged files

3. **Parallel Processing**
   - Concurrent file downloads
   - Parallel content extraction
   - Async index updates

## Testing Strategy

1. **OAuth Flow Testing**
   - Mock OAuth providers
   - Test token refresh
   - Error state handling

2. **Sync Testing**
   - Simulated file changes
   - Webhook delivery
   - Conflict resolution

3. **Integration Testing**
   - Real provider APIs (sandboxed)
   - End-to-end sync flows
   - Performance benchmarks