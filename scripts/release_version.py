#!/usr/bin/env python3
"""
Release version utility for P8FS workspace.

Creates a git tag for the current version and pushes it to trigger the release pipeline.
This should be run AFTER testing the build created by bump_version.py.

Usage:
    # Create and push release tag for current version
    python scripts/release_version.py

    # Preview what would be done
    python scripts/release_version.py --dry-run

    # Create tag but don't push
    python scripts/release_version.py --no-push

Workflow:
    1. bump_version.py → Creates "build v1.2.3" commit → Triggers build pipeline
    2. Test the CalVer images from build pipeline
    3. release_version.py → Creates "v1.2.3" tag → Triggers release pipeline
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_root_dir() -> Path:
    """Get repository root directory."""
    return Path(__file__).parent.parent


def read_current_version() -> str:
    """Read current version from VERSION file."""
    version_file = get_root_dir() / "VERSION"
    if not version_file.exists():
        raise FileNotFoundError("VERSION file not found. Run from repository root.")
    return version_file.read_text().strip()


def check_git_status() -> bool:
    """Check if git working directory is clean."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=get_root_dir(),
        capture_output=True,
        text=True,
        check=True
    )
    return len(result.stdout.strip()) == 0


def tag_exists(tag: str) -> bool:
    """Check if a git tag already exists."""
    result = subprocess.run(
        ["git", "tag", "-l", tag],
        cwd=get_root_dir(),
        capture_output=True,
        text=True,
        check=True
    )
    return len(result.stdout.strip()) > 0


def get_current_branch() -> str:
    """Get current git branch name."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=get_root_dir(),
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def create_and_push_tag(version: str, dry_run: bool = False, no_push: bool = False) -> None:
    """
    Create git tag and push to remote.

    Args:
        version: Version number (e.g., "1.2.3")
        dry_run: Preview without making changes
        no_push: Create tag but don't push
    """
    root = get_root_dir()
    tag = f"v{version}"

    # Check if tag already exists
    if tag_exists(tag):
        print(f"⚠️  Tag {tag} already exists")
        response = input("Do you want to delete and recreate it? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted")
            sys.exit(1)

        if dry_run:
            print(f"[DRY RUN] Would delete tag: {tag}")
        else:
            subprocess.run(["git", "tag", "-d", tag], cwd=root, check=True)
            print(f"✓ Deleted existing tag: {tag}")

    # Create tag
    tag_message = f"Release {version}"

    if dry_run:
        print(f"\n[DRY RUN] Would create annotated tag:")
        print(f"  Tag: {tag}")
        print(f"  Message: {tag_message}")
    else:
        subprocess.run(
            ["git", "tag", "-a", tag, "-m", tag_message],
            cwd=root,
            check=True
        )
        print(f"✓ Created tag: {tag}")

    # Push tag
    if not no_push:
        if dry_run:
            print(f"\n[DRY RUN] Would push tag to origin:")
            print(f"  git push origin {tag}")
        else:
            subprocess.run(["git", "push", "origin", tag], cwd=root, check=True)
            print(f"✓ Pushed tag to origin: {tag}")

            print(f"\n🚀 Release pipeline triggered!")
            print(f"\nWhat happens next:")
            print(f"  1. Release pipeline finds CalVer images matching v{version}")
            print(f"  2. Images retagged as {version}-light-amd64, {version}-heavy-amd64, etc.")
            print(f"  3. Images signed with Cosign")
            print(f"  4. SBOM generated and attached")
            print(f"  5. Trivy security scan")
            print(f"  6. Kubernetes manifests updated in p8fs-cloud repo")
            print(f"  7. ArgoCD deploys to production")
            print(f"\nMonitor progress:")
            print(f"  gh run list --workflow=release.yml")
            print(f"  gh run watch")
    else:
        print(f"\n✓ Tag created: {tag}")
        print(f"  Push manually with: git push origin {tag}")


def main():
    parser = argparse.ArgumentParser(
        description="Create release tag for current version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without creating tag"
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Create tag but don't push to remote"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip git status check (allow dirty working directory)"
    )

    args = parser.parse_args()

    try:
        # Read current version
        version = read_current_version()
        tag = f"v{version}"

        print(f"Current version: {version}")
        print(f"Release tag: {tag}")

        # Check git status
        if not args.force and not args.dry_run:
            is_clean = check_git_status()
            if not is_clean:
                print("\n⚠️  Warning: Working directory has uncommitted changes")
                print("  Commit or stash changes before creating release tag")
                print("  Or use --force to proceed anyway")
                sys.exit(1)

        # Get current branch
        branch = get_current_branch()
        print(f"Current branch: {branch}")

        if args.dry_run:
            print("\n[DRY RUN MODE - No changes will be made]\n")

        # Confirm action
        if not args.dry_run:
            print(f"\nThis will:")
            print(f"  1. Create tag: {tag}")
            if not args.no_push:
                print(f"  2. Push tag to origin")
                print(f"  3. Trigger release pipeline")

            response = input("\nContinue? [y/N]: ")
            if response.lower() != 'y':
                print("Aborted")
                sys.exit(0)

        # Create and push tag
        create_and_push_tag(version, args.dry_run, args.no_push)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
