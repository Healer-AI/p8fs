# P8FS API Local Development Guide

## Starting the API Server

### Prerequisites

1. **Start Database Services**
   ```bash
   # From p8fs directory
   cd /Users/sirsh/code/p8fs-modules/p8fs
   docker compose up postgres -d  # PostgreSQL (default)
   # OR
   docker compose up tidb -d      # TiDB (production-compatible)
   ```

2. **Apply Migrations**

   PostgreSQL migrations run automatically on container startup.

   For TiDB, apply migrations manually:
   ```bash
   cd /Users/sirsh/code/p8fs-modules
   uv run python -c "
   import pymysql
   from pathlib import Path

   migration = Path('p8fs/extensions/migrations/tidb/install.sql').read_text()
   conn = pymysql.connect(host='localhost', port=4000, user='root', autocommit=True)
   cursor = conn.cursor()

   for statement in [s.strip() for s in migration.split(';') if s.strip() and not s.strip().startswith('--')]:
       try:
           cursor.execute(statement)
       except Exception as e:
           print(f'Warning: {e}')

   cursor.close()
   conn.close()
   print('✅ TiDB migration complete')
   "
   ```

### Running the Server

#### Development Mode (with auto-reload)

**IMPORTANT**: Always use `uv run` and `--reload` for development. Check that nothing is already running on port 8001 to avoid confusion (404s, stale code, etc.).

```bash
# Check for existing process on port 8001
lsof -ti :8001 | xargs kill -9  # Kill if needed

# Start with PostgreSQL (default)
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_DEBUG=true uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001

# Start with TiDB provider
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_DEBUG=true P8FS_STORAGE_PROVIDER=tidb uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001
```

**Development Features**:
- Auto-reload on file changes (uvicorn `--reload`)
- Editable installs via uv workspaces (changes in dependencies immediately available)
- Debug logging enabled
- CORS allows all origins
- Detailed error messages

#### Production Mode

```bash
cd /Users/sirsh/code/p8fs-modules/p8fs-api
P8FS_STORAGE_PROVIDER=tidb uv run uvicorn src.p8fs_api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Environment Variables

```bash
# Core Settings
P8FS_DEBUG=true                    # Enable debug mode
P8FS_STORAGE_PROVIDER=postgresql   # Database provider (postgresql|tidb|rocksdb)

# API Configuration
P8FS_API_HOST=0.0.0.0             # API host
P8FS_API_PORT=8001                # API port

# Database Connection Strings (built automatically from centralized config)
# PostgreSQL: postgresql://postgres:postgres@localhost:5438/app
# TiDB: mysql://root@localhost:4000/public

# Authentication
P8FS_DEV_TOKEN_SECRET=your-dev-token  # Dev endpoint authentication

# LLM Services (optional)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Verify Server is Running

```bash
# Health check
curl http://localhost:8001/health

# API info
curl http://localhost:8001/

# OAuth discovery
curl http://localhost:8001/.well-known/openid-configuration

# API documentation
open http://localhost:8001/docs
```

### Hot Reload in Development

The uv workspace setup provides seamless hot reload:

1. **Editable Installs**: Changes to dependencies (p8fs-cluster, p8fs-auth, p8fs) are immediately available
2. **Uvicorn Reload**: Service restarts automatically on file changes
3. **Combined Effect**: Modify any dependency code → service restarts with changes

Example workflow:
```bash
# 1. Start API server with --reload
cd p8fs-api
P8FS_DEBUG=true uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001

# 2. In another terminal, modify auth logic
cd ../p8fs-auth/src/p8fs_auth
vim services/mobile_service.py

# 3. Save file → uvicorn detects change → service restarts → new code active
```

## Testing Authentication

### Device Registration (CLI)

Register a device and get authentication tokens:

```bash
# Register with PostgreSQL (default)
cd /Users/sirsh/code/p8fs-modules/p8fs-api
uv run python -m p8fs_api.cli.device --local register \
  --email test@example.com \
  --tenant test-tenant

# Register with TiDB
P8FS_STORAGE_PROVIDER=tidb uv run python -m p8fs_api.cli.device --local register \
  --email test@example.com \
  --tenant test-tenant

# Check device status
uv run python -m p8fs_api.cli.device --local status

# Test token validity
uv run python -m p8fs_api.cli.device --local ping
```

### Verify Authentication in Database

**PostgreSQL**:
```bash
docker exec percolate psql -U postgres -d app -c \
  "SELECT tenant_id, email, active FROM tenants WHERE email='test@example.com';"
```

**TiDB**:
```bash
uv run python -c "
import pymysql
conn = pymysql.connect(host='localhost', port=4000, user='root', database='public')
cursor = conn.cursor()
cursor.execute('SELECT tenant_id, email, active FROM tenants WHERE email=\"test@example.com\"')
print(cursor.fetchall())
cursor.close()
conn.close()
"
```

### Device Authorization Flow

Test the full OAuth device flow with QR code:

```bash
# 1. Open the device verification page in browser
open http://localhost:8001/api/v1/oauth/device

# 2. Scan QR code or note the user code (e.g., A1B2-C3D4)

# 3. Approve the device using registered CLI device
uv run python -m p8fs_api.cli.device --local approve A1B2-C3D4

# 4. The browser page will detect approval and redirect/show success
```

## Database Connections

### DBeaver Setup for TiDB

1. **Create New Connection**
   - Database: MySQL
   - Server Host: `localhost`
   - Port: `4000`
   - Database: `public`
   - Username: `root`
   - Password: (empty)

2. **Connection Settings**
   - Driver: MySQL 8.x
   - JDBC URL: `jdbc:mysql://localhost:4000/public`

3. **Browse Tables**
   ```
   public/
   ├── tenants          # Tenant/user accounts
   ├── kv_storage       # Key-value temporary data
   ├── language_model_apis
   ├── resources
   └── ...

   embeddings/
   ├── resources_embeddings
   ├── agents_embeddings
   └── ...
   ```

### DBeaver Setup for PostgreSQL

1. **Create New Connection**
   - Database: PostgreSQL
   - Server Host: `localhost`
   - Port: `5438`
   - Database: `app`
   - Username: `postgres`
   - Password: `postgres`

2. **Browse Tables**
   ```
   public/
   ├── tenants
   ├── resources
   └── ...

   embeddings/
   └── (embedding tables)
   ```

## Common Issues

### Port Already in Use

```bash
# Find process using port 8001
lsof -ti :8001

# Kill the process
lsof -ti :8001 | xargs kill -9
```

### Database Connection Failures

**PostgreSQL**:
```bash
# Check container is running
docker ps | grep percolate

# Restart if needed
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose restart postgres
```

**TiDB**:
```bash
# Check container is running
docker ps | grep tidb

# Restart if needed
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose restart tidb

# Verify TiDB is responsive
uv run python -c "import pymysql; pymysql.connect(host='localhost', port=4000, user='root').close(); print('✅ TiDB connection OK')"
```

### Module Import Errors

The uv workspace should handle imports automatically. If you see import errors:

```bash
# Reinstall workspace dependencies
cd /Users/sirsh/code/p8fs-modules/p8fs-api
uv sync

# Verify workspace members are installed
uv pip list | grep p8fs
```

### Authentication Failures

```bash
# Regenerate dev tokens
cd /Users/sirsh/code/p8fs-modules/p8fs-api
uv run python scripts/dev/generate_dev_token.py

# Re-register device
uv run python -m p8fs_api.cli.device --local register --email test@example.com --tenant test-tenant

# Check token file
cat ~/.p8fs/auth/token.json
```

## Development Workflow

### Standard Development Cycle

```bash
# 1. Start database
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose up postgres -d

# 2. Start API server with hot reload
cd ../p8fs-api
P8FS_DEBUG=true uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001

# 3. Register test device
uv run python -m p8fs_api.cli.device --local register --email dev@example.com --tenant test-tenant

# 4. Make code changes
# - Edit files in p8fs-api, p8fs-auth, p8fs, or p8fs-cluster
# - Server automatically restarts on save
# - Test changes immediately

# 5. Run tests
uv run pytest tests/unit/ -v          # Unit tests
uv run pytest tests/integration/ -v  # Integration tests
```

### Testing Against TiDB

```bash
# 1. Start TiDB
cd /Users/sirsh/code/p8fs-modules/p8fs
docker compose up tidb -d

# 2. Apply migrations (one-time)
cd ..
uv run python -c "import pymysql; ... "  # See migrations section above

# 3. Start API with TiDB provider
cd p8fs-api
P8FS_DEBUG=true P8FS_STORAGE_PROVIDER=tidb uv run uvicorn src.p8fs_api.main:app --reload --host 0.0.0.0 --port 8001

# 4. Test with TiDB
P8FS_STORAGE_PROVIDER=tidb uv run python -m p8fs_api.cli.device --local register --email test@example.com --tenant test-tenant
```

## API Endpoints Reference

### Authentication Endpoints

- `POST /oauth/token` - Token exchange (all grant types)
- `POST /oauth/device_authorization` - Initiate device flow
- `POST /oauth/device/register` - Register new mobile device
- `POST /oauth/device/approve` - Approve device (protected)
- `GET /oauth/ping` - Test token validity (protected)
- `GET /oauth/device` - Device verification page (QR code)

### Discovery Endpoints

- `GET /.well-known/openid-configuration` - OAuth/OpenID discovery
- `GET /.well-known/oauth-authorization-server` - OAuth metadata
- `GET /.well-known/jwks.json` - Public keys for JWT verification

### Development Endpoints

- `POST /api/v1/auth/dev/register` - Dev device registration (requires dev token)
- `GET /health` - Health check
- `GET /docs` - OpenAPI documentation

### MCP Server

- `POST /api/mcp/` - MCP protocol endpoint
- MCP tools available after authentication

## Next Steps

- See `/Users/sirsh/code/p8fs-modules/how-to.md` for complete usage guide
- See `/Users/sirsh/code/p8fs-modules/p8fs-auth/docs/authentication-flows.md` for auth architecture
- See `/Users/sirsh/code/p8fs-modules/p8fs/extensions/migrations/README.md` for database setup
