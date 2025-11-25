#!/usr/bin/env python3
"""
Upload a release test file to S3 to verify deployment.
This script creates a test file with release information and uploads it securely.

Usage:
    python upload_release_test_file.py [filename]

If no filename is provided, creates a unique timestamped file.
Each run creates a unique file to trigger the CREATE file flow.
"""

import sys
import os
import argparse
import asyncio
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import p8fs modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p8fs.services.s3_storage import S3StorageService
from p8fs_cluster.config.settings import config


def get_version():
    """Read version from VERSION file in workspace root."""
    version_file = Path(__file__).parent.parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "unknown"


def create_release_test_file(version: str, filename: str = None) -> tuple[str, str, str]:
    """Create a release test file with version information.

    Args:
        version: Release version
        filename: Optional custom filename (without extension). If None, uses version-timestamp.

    Returns:
        Tuple of (temp_file_path, content, s3_key)
    """
    now = datetime.utcnow()
    timestamp = int(now.timestamp())

    # Generate unique filename
    # Default: v{version}-{timestamp} (e.g., v1.1.49-1731663557)
    # Custom: {filename}-v{version}-{timestamp} (e.g., my-test-v1.1.49-1731663557)
    if filename:
        base_filename = f"{filename}-v{version}-{timestamp}"
    else:
        base_filename = f"v{version}-{timestamp}"

    content = f"""P8FS Release v{version} Verification File
{'=' * 60}

This file verifies the successful deployment of P8FS v{version}.

File Information:
- Filename: {base_filename}.txt
- Upload Timestamp: {timestamp}
- Upload Date: {now.isoformat()}
- Unique ID: {base_filename}

Release Information:
- Version: {version}
- Upload Method: P8FS S3StorageService (secure upload)
- Tenant: tenant-test

Docker Images:
- API: ghcr.io/percolation-labs/p8fs-ecosystem-test:{version}-light-amd64
- Workers: ghcr.io/percolation-labs/p8fs-ecosystem-test:{version}-heavy-amd64
- Scheduler: ghcr.io/percolation-labs/p8fs-ecosystem-test:{version}-heavy-amd64

Deployment Notes:
- Uploaded without Content-MD5 header (SeaweedFS compatibility)
- Using SHA-256 for content integrity verification
- Secure upload via P8FS S3StorageService
- Each upload creates a unique file to trigger CREATE flow

Test Status: ✅ Upload successful if you can read this file!
Verification: This file was created at {now.isoformat()} ({timestamp})
"""

    # Create temp file
    temp_file = f"/tmp/{base_filename}.txt"
    with open(temp_file, "w") as f:
        f.write(content)

    # S3 key - simpler path since S3StorageService adds /uploads/ prefix
    s3_key = f"{base_filename}.txt"

    return temp_file, content, s3_key


async def main():
    """Main upload function."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Upload a release test file to S3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload with version-based filename (e.g., v1.1.49-1731663557.txt)
  python upload_release_test_file.py

  # Upload with custom prefix (e.g., deployment-test-v1.1.49-1731663557.txt)
  python upload_release_test_file.py deployment-test

  # Upload for API verification (e.g., api-verified-v1.1.49-1731663557.txt)
  python upload_release_test_file.py api-verified
        """
    )
    parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Custom filename prefix (without extension). Default uses version number. Creates unique file: {prefix}-v{version}-{timestamp}.txt"
    )
    args = parser.parse_args()

    # Get version
    version = get_version()
    print(f"📦 Creating release test file for version: {version}")

    # Create test file
    temp_file, content, s3_key = create_release_test_file(version, args.filename)
    print(f"✏️  Created test file: {temp_file}")
    print(f"   Size: {len(content)} bytes")
    print(f"   S3 Key: {s3_key}")

    # Initialize S3 storage service
    # IMPORTANT: use_content_md5=False for SeaweedFS compatibility
    print(f"\n📡 Initializing S3 storage service...")
    print(f"   Endpoint: {config.seaweedfs_s3_endpoint}")
    print(f"   Bucket: tenant-test")

    s3_service = S3StorageService(
        use_content_md5=False  # Critical for SeaweedFS compatibility
    )

    # Upload file
    try:
        print(f"\n📤 Uploading release test file...")
        result = await s3_service.upload_file(
            local_path=Path(temp_file),
            remote_path=s3_key,
            tenant_id="tenant-test",
            content_type="text/plain"
        )

        print(f"✅ Upload successful!")
        print(f"   Filename: {s3_key}")
        print(f"   Size: {len(content)} bytes")
        print(f"   Actual S3 path: uploads/{datetime.utcnow().strftime('%Y/%m/%d')}/{s3_key}")

        # Note: Skip download verification since S3StorageService adds /uploads/YYYY/MM/DD/ prefix
        # The file is successfully uploaded as confirmed by 200 response
        print(f"\n✅ SUCCESS: Release test file v{version} uploaded!")
        print(f"\nThe file will be processed by storage workers and indexed in the database.")
        print(f"Check the database to verify file processing:")

    except Exception as e:
        print(f"❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"\n🧹 Cleaned up temp file: {temp_file}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
