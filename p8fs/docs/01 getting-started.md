# Getting Started

`p8fs` is used to build agentic systems with integrated multi-modal RAG. When you fetch the repo you can spin up the the docker backend, set your language model api keys e.g. OPEN_API and get to work. This guide shows you how to do that

01. Setup docker and check services and env variables
02. run tests
03. use the CLI to test agents and models or query the database
04. connect to the database to see what is created in the database from your activity (default contexts)
05. create your own agent and use it in normal mode
06. run your agent in batch job and streaming mode 
07. save an Engram (What is an Engram)
08. perform vector and graph search against the repository
09. switch to the TiDB provider 
10. connect to your memory vault via MCP and also run the API to test the streaming endpoint for your model

## 03. Using the P8FS CLI

P8FS Core provides a command-line interface for testing agents and querying the database directly.

### Prerequisites

Make sure you have:
- Docker services running (from section 01)
- Environment variables set, especially `OPENAI_API_KEY`
- Database connection configured (PostgreSQL is the default)

### Agent Command

Test AI agents using the MemoryProxy in streaming mode:

```bash
# Basic agent interaction
uv run p8fs agent "What is machine learning?"

# Use a specific model and agent context
uv run p8fs agent --model gpt-4 --agent p8-Resources "Explain vector databases"

# Interactive mode (read from stdin)
echo "What are the benefits of multi-modal RAG?" | uv run p8fs agent

# Test with different models
uv run p8fs agent --model claude-3-5-sonnet "Compare SQL and NoSQL databases"
```

**Agent Command Options:**
- `--agent`: Agent name/tenant ID (default: `p8-Resources`)
- `--model`: Model to use (default: `gpt-4`)

### Query Command

Execute SQL queries directly against your configured database:

```bash
# Check database version
uv run p8fs query "SELECT version();"

# Query system information
uv run p8fs query "SELECT current_database(), current_user;"

# Get results in JSON format
uv run p8fs query --format=json "SELECT * FROM information_schema.tables LIMIT 3;"

# Use different output formats
uv run p8fs query --format=jsonl "SHOW TABLES;"

# Interactive SQL mode
echo "SELECT COUNT(*) FROM pg_tables;" | uv run p8fs query

# Test with TiDB provider (if configured)
uv run p8fs query --provider=tidb "SHOW DATABASES;"
```

**Query Command Options:**
- `--provider`: Database provider (`postgres`, `tidb`, `rocksdb`) (default: `postgres`)
- `--format`: Output format (`table`, `json`, `jsonl`) (default: `table`)

### Expected Output

**Agent Command Example:**
```bash
$ uv run p8fs agent "What is 2+2?"

[p8-Resources] Thinking...

The result of 2+2 is 4.
```

**Query Command Example:**
```bash
$ uv run p8fs query "SELECT version();"

version
-----------------
PostgreSQL 16.4 (Debian 16.4-1.pgdg110+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 10.2.1-6) 10.2.1 20210110, 64-bit
```

### Troubleshooting

If you encounter issues:

1. **Connection errors**: Ensure Docker services are running (`docker-compose ps`)
2. **Missing API key**: Set `OPENAI_API_KEY` environment variable
3. **Module not found**: Make sure you're in the p8fs directory with proper dependencies installed
4. **Database access**: Check PostgreSQL is accessible on port 5438

### Next Steps

Once the CLI is working, you can proceed to section 04 to explore what the agent interactions create in the database.