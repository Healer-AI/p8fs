# Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality by running tests automatically.

## Hooks Configuration

- **Pre-commit hook**: Runs unit tests before each commit
- **Pre-push hook**: Runs integration tests before pushing to remote

## Usage

### Normal Usage
```bash
# Commits will run unit tests automatically
git commit -m "your message"

# Pushes will run integration tests automatically
git push
```

### Bypassing Hooks
Use `--no-verify` to skip hooks when needed:

```bash
# Skip pre-commit unit tests
git commit -m "your message" --no-verify

# Skip pre-push integration tests  
git push --no-verify
```

## Setup

Pre-commit hooks are already installed. If you need to reinstall:

```bash
# Install pre-commit
uv add --dev pre-commit

# Install hooks
uv run pre-commit install
uv run pre-commit install -t pre-push
```

## Requirements

- Docker must be running for integration tests (pre-push)
- All tests must pass for commits/pushes to succeed (unless using --no-verify)