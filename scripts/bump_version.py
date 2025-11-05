#!/usr/bin/env python3
"""
Version bumping utility for P8FS workspace.

Manages semantic versioning across the entire workspace with a single source of truth.
Automatically updates VERSION file, pyproject.toml files, and creates a git commit.

RECOMMENDED WORKFLOW:
    1. Bump version with --pr flag to create pull request:
       python scripts/bump_version.py --pr -m "Add new feature"

    2. Review and merge PR to main via GitHub

    3. Switch to main and tag for release 
       (this is the thing that builds so maybe bump version is now redundant 
           because if you bump it must be a release candidate
           :. it probable makes to pr with or without a bump. the bump implies a build-rc - then when we merge to main we can rebase main and tag for deployment
           ):
       git checkout main && git pull
       git tag v1.1.26-rc && git push origin v1.1.26-rc

    4. After RC testing, create production release:
       git tag v1.1.26 && git push origin v1.1.26

The --pr flag automates: commit → test → push → create PR

Usage:
    # Bump patch version and create PR (recommended)
    python scripts/bump_version.py --pr

    # Bump minor version with PR
    python scripts/bump_version.py --minor --pr -m "Add OAuth2 authentication"

    # Bump major version with PR
    python scripts/bump_version.py --major --pr

    # Bump without PR (manual workflow)
    python scripts/bump_version.py

    # Preview changes without committing
    python scripts/bump_version.py --dry-run

    # Custom version
    python scripts/bump_version.py --set 1.2.3
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Tuple


def get_root_dir() -> Path:
    """Get repository root directory."""
    return Path(__file__).parent.parent


def read_current_version() -> str:
    """Read current version from VERSION file."""
    version_file = get_root_dir() / "VERSION"
    if not version_file.exists():
        raise FileNotFoundError("VERSION file not found. Run from repository root.")
    return version_file.read_text().strip()


def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse semantic version string into tuple."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise ValueError(f"Invalid version format: {version}. Expected x.y.z")
    return tuple(map(int, match.groups()))


def bump_version(current: str, bump_type: str) -> str:
    """
    Bump version according to semantic versioning rules.

    Args:
        current: Current version string (e.g., "0.1.0")
        bump_type: One of "major", "minor", "patch"

    Returns:
        New version string
    """
    major, minor, patch = parse_version(current)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")


def update_version_file(new_version: str, dry_run: bool = False) -> None:
    """Update VERSION file with new version."""
    version_file = get_root_dir() / "VERSION"

    if dry_run:
        print(f"[DRY RUN] Would update VERSION: {new_version}")
        return

    version_file.write_text(f"{new_version}\n")
    print(f"Updated VERSION: {new_version}")


def update_pyproject_toml(file_path: Path, new_version: str, dry_run: bool = False) -> bool:
    """
    Update version in pyproject.toml file.

    Returns:
        True if file was modified, False otherwise
    """
    if not file_path.exists():
        return False

    content = file_path.read_text()

    # Match version in [project] section
    pattern = r'(version\s*=\s*")[^"]+(")'
    replacement = rf'\g<1>{new_version}\g<2>'

    new_content = re.sub(pattern, replacement, content)

    if new_content == content:
        return False

    if dry_run:
        print(f"[DRY RUN] Would update {file_path.relative_to(get_root_dir())}: {new_version}")
        return True

    file_path.write_text(new_content)
    print(f"Updated {file_path.relative_to(get_root_dir())}: {new_version}")
    return True


def update_all_pyproject_files(new_version: str, dry_run: bool = False) -> list[Path]:
    """Update version in all workspace pyproject.toml files."""
    root = get_root_dir()
    updated_files = []

    # Root pyproject.toml
    root_pyproject = root / "pyproject.toml"
    if update_pyproject_toml(root_pyproject, new_version, dry_run):
        updated_files.append(root_pyproject)

    # Module pyproject.toml files
    modules = ["p8fs-api", "p8fs-auth", "p8fs", "p8fs-cluster", "p8fs-node"]
    for module in modules:
        module_pyproject = root / module / "pyproject.toml"
        if update_pyproject_toml(module_pyproject, new_version, dry_run):
            updated_files.append(module_pyproject)

    return updated_files


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def create_git_commit(new_version: str, updated_files: list[Path], dry_run: bool = False, message: str = "Bumping build") -> None:
    """Create git commit with version bump changes."""
    root = get_root_dir()

    if dry_run:
        print(f"\n[DRY RUN] To trigger a build  push tag:")
        print(f"  git tag v{new_version}-rc &&  git tag push origin v{new_version}-rc")
        print(f"  Files: {len(updated_files) + 1}")
        return

    # Stage files
    files_to_stage = ["VERSION"] + [str(f.relative_to(root)) for f in updated_files]
    subprocess.run(["git", "add"] + files_to_stage, cwd=root, check=True)

    # Create commit with build trigger
    commit_message = f"* build v{new_version} - {message}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=root,
        capture_output=True,
        text=True
    )

    # If commit failed (likely due to pre-commit hook modifying files), retry once
    if result.returncode != 0:
        print(f"Pre-commit hook modified files, staging changes and retrying...")
        # Stage any modified files (like uv.lock)
        subprocess.run(["git", "add", "-u"], cwd=root, check=True)
        # Retry commit
        subprocess.run(["git", "commit", "-m", commit_message], cwd=root, check=True)

    print(f"\n✓ Created commit: {commit_message}")
    print(f"✓ Staged {len(files_to_stage)} file(s)")
    print(f"\nNext steps:")
    print(f"  1. Push to trigger build: git push origin <branch>")
    print(f"  2. After testing, create release tag: git tag v{new_version}-rc && git push origin v{new_version}-rc")


def create_pr_workflow(new_version: str, updated_files: list[Path], dry_run: bool = False, message: str = "Bumping build") -> None:
    """Create git commit, push branch, and open pull request."""
    root = get_root_dir()

    if dry_run:
        print(f"\n[DRY RUN] Would run PR workflow:")
        print(f"  1. Create commit: v{new_version}")
        print(f"  2. Run tests (pre-commit hooks)")
        print(f"  3. Push branch to origin")
        print(f"  4. Create pull request")
        print(f"  Files: {len(updated_files) + 1}")
        return

    # Get current branch
    branch = get_current_branch()
    print(f"Current branch: {branch}")

    # Stage files
    files_to_stage = ["VERSION"] + [str(f.relative_to(root)) for f in updated_files]
    subprocess.run(["git", "add"] + files_to_stage, cwd=root, check=True)

    # Create commit with build trigger
    commit_message = f"* build v{new_version} - {message}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=root,
        capture_output=True,
        text=True
    )

    # If commit failed (likely due to pre-commit hook modifying files), retry once
    if result.returncode != 0:
        print(f"Pre-commit hook modified files, staging changes and retrying...")
        # Stage any modified files (like uv.lock)
        subprocess.run(["git", "add", "-u"], cwd=root, check=True)
        # Retry commit
        subprocess.run(["git", "commit", "-m", commit_message], cwd=root, check=True)

    print(f"✓ Created commit: {commit_message}")
    print(f"✓ Staged {len(files_to_stage)} file(s)")

    # Push branch
    print(f"\nPushing branch '{branch}' to origin...")
    try:
        subprocess.run(["git", "push", "origin", branch], cwd=root, check=True)
        print(f"✓ Pushed branch to origin")
    except subprocess.CalledProcessError:
        print(f"✗ Failed to push branch. You may need to push manually.")
        return

    # Create PR using gh CLI
    print(f"\nCreating pull request...")
    pr_title = f"Build v{new_version}: {message}"
    pr_body = f"""## Version Bump: v{new_version}

{message}

### Changes
- Updated VERSION file to {new_version}
- Updated all pyproject.toml files to {new_version}

### Next Steps
After merging this PR:
1. Switch to main: `git checkout main && git pull`
2. Tag RC for build: `git tag v{new_version}-rc && git push origin v{new_version}-rc`
3. After testing, release: `git tag v{new_version} && git push origin v{new_version}`

Automated version bump via bump_version.py"""

    try:
        result = subprocess.run(
            ["gh", "pr", "create", "--title", pr_title, "--body", pr_body],
            cwd=root,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✓ Pull request created successfully!")
        print(result.stdout)
        print(f"\nNext steps:")
        print(f"  1. Review and merge PR on GitHub")
        print(f"  2. git checkout main && git pull")
        print(f"  3. git tag v{new_version}-rc && git push origin v{new_version}-rc")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to create PR. Error: {e.stderr}")
        print(f"You can create it manually with: gh pr create")


def main():
    parser = argparse.ArgumentParser(
        description="Bump version across P8FS workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    bump_group = parser.add_mutually_exclusive_group()
    bump_group.add_argument(
        "--major",
        action="store_true",
        help="Bump major version (X.0.0)"
    )
    bump_group.add_argument(
        "--minor",
        action="store_true",
        help="Bump minor version (x.X.0)"
    )
    bump_group.add_argument(
        "--patch",
        action="store_true",
        default=True,
        help="Bump patch version (x.x.X) [default]"
    )
    bump_group.add_argument(
        "--set",
        metavar="VERSION",
        help="Set specific version (e.g., 1.2.3)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Don't create git commit"
    )
    parser.add_argument(
        "-m", "--message",
        metavar="MESSAGE",
        default="Bumping build",
        help="Commit message description (default: 'Bumping build')"
    )
    parser.add_argument(
        "--pr",
        action="store_true",
        help="Create pull request after commit (runs: commit → test → push → PR)"
    )

    args = parser.parse_args()

    try:
        # Determine bump type
        if args.set:
            new_version = args.set
            parse_version(new_version)  # Validate format
            current_version = read_current_version()
        elif args.major:
            bump_type = "major"
            current_version = read_current_version()
            new_version = bump_version(current_version, bump_type)
        elif args.minor:
            bump_type = "minor"
            current_version = read_current_version()
            new_version = bump_version(current_version, bump_type)
        else:
            bump_type = "patch"
            current_version = read_current_version()
            new_version = bump_version(current_version, bump_type)

        # Display version change
        if args.set:
            print(f"Setting version: {current_version} → {new_version}")
        else:
            print(f"Bumping {bump_type} version: {current_version} → {new_version}")

        if args.dry_run:
            print("\n[DRY RUN MODE - No files will be modified]\n")

        # Update files
        update_version_file(new_version, args.dry_run)
        updated_files = update_all_pyproject_files(new_version, args.dry_run)

        # Display version with -rc for developers to copy
        version_display = f"v{new_version}-rc"
        print(f"\nVersion for developers to use: {version_display}")

        # Create commit or PR workflow
        if not args.no_commit:
            if args.pr:
                create_pr_workflow(new_version, updated_files, args.dry_run, args.message)
            else:
                create_git_commit(new_version, updated_files, args.dry_run, args.message)
        elif not args.dry_run:
            print(f"\n✓ Version updated to {new_version}")
            print("  Run 'git add VERSION */pyproject.toml && git commit -m \"build v{new_version}\"' to commit")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()