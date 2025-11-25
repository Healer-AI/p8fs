"""
Files command for S3 storage operations.

Content-MD5 is included by default for AWS S3 compliance.
If your S3 server has issues with Content-MD5 (some older SeaweedFS servers),
you can disable it by passing use_content_md5=False to S3StorageService.

File integrity is always verified using SHA-256 hashing.
See docs/11-seaweedfs-events.md for details.
"""

import sys
from pathlib import Path
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def files_command(args):
    """
    Handle files operations (upload, download, list, delete, info).

    Content-MD5 is included by default for AWS S3 compliance.
    If your S3 server has issues with Content-MD5, you can disable it
    by passing use_content_md5=False to S3StorageService.

    File integrity is always verified using SHA-256 hashing.
    See docs/11-seaweedfs-events.md for details.
    """
    try:
        from p8fs.services.s3_storage import S3StorageService

        # Initialize S3 service (use_content_md5=True by default for AWS S3 compliance)
        s3 = S3StorageService()
        tenant_id = args.tenant_id

        if args.files_action == "upload":
            # Upload file
            local_path = Path(args.local_path)
            if not local_path.exists():
                print(f"❌ File not found: {local_path}", file=sys.stderr)
                return 1

            # Determine remote path
            if args.remote_path:
                remote_path = args.remote_path
            else:
                remote_path = local_path.name

            # Detect content type
            import mimetypes
            content_type = args.content_type
            if not content_type:
                content_type, _ = mimetypes.guess_type(str(local_path))
                if not content_type:
                    content_type = "application/octet-stream"

            print(f"📤 Uploading {local_path.name} to {remote_path}...")
            result = await s3.upload_file(
                local_path, remote_path, tenant_id, content_type
            )

            print(f"✅ Upload successful!")
            print(f"   Path: {result['path']}")
            print(f"   Size: {result['size_bytes']:,} bytes")
            print(f"   Type: {result['content_type']}")

        elif args.files_action == "download":
            # Download file - first positional is remote_path, second is local_path
            remote_path = args.local_path or args.remote_path
            if not remote_path:
                print(f"❌ Remote path required for download", file=sys.stderr)
                return 1

            print(f"📥 Downloading {remote_path}...")
            result = await s3.download_file(remote_path, tenant_id)

            if not result:
                print(f"❌ File not found: {remote_path}", file=sys.stderr)
                return 1

            # Determine local path
            if args.remote_path and args.local_path:
                # Both provided: first is remote, second is local
                local_path = Path(args.remote_path)
            elif args.remote_path:
                # Only remote provided in second position
                filename = remote_path.split("/")[-1]
                local_path = Path.cwd() / filename
            else:
                # Only one arg: use filename from remote path
                filename = remote_path.split("/")[-1]
                local_path = Path.cwd() / filename

            # Write file
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(result["content"])

            print(f"✅ Download successful!")
            print(f"   Saved to: {local_path}")
            print(f"   Size: {result['size_bytes']:,} bytes")

        elif args.files_action == "list":
            # List files
            path = args.path or "/"
            print(f"📁 Listing files in {path}...")
            result = await s3.list_files(
                path, tenant_id, recursive=args.recursive, limit=args.limit
            )

            if not result["files"]:
                print("No files found")
            else:
                print(f"\n{'Path':<60} {'Size':>15} {'Modified':<25}")
                print("-" * 100)
                for file in result["files"]:
                    size_str = f"{file['size_bytes']:,}"
                    modified = file.get("modified_at", "")[:19] if file.get("modified_at") else ""
                    print(f"{file['path']:<60} {size_str:>15} {modified:<25}")
                print(f"\n{result['total']} files")

        elif args.files_action == "delete":
            # Delete file - first positional is remote_path
            remote_path = args.local_path or args.remote_path
            if not remote_path:
                print(f"❌ Remote path required for delete", file=sys.stderr)
                return 1

            if not args.force:
                response = input(f"Delete {remote_path}? (y/N): ")
                if response.lower() != "y":
                    print("Cancelled")
                    return 0

            print(f"🗑️  Deleting {remote_path}...")
            deleted = await s3.delete_file(remote_path, tenant_id)

            if deleted:
                print(f"✅ File deleted successfully")
            else:
                print(f"❌ File not found: {remote_path}", file=sys.stderr)
                return 1

        elif args.files_action == "info":
            # Get file info - first positional is remote_path
            remote_path = args.local_path or args.remote_path
            if not remote_path:
                print(f"❌ Remote path required for info", file=sys.stderr)
                return 1

            print(f"ℹ️  Getting info for {remote_path}...")
            result = await s3.get_file_info(remote_path, tenant_id)

            if not result:
                print(f"❌ File not found: {remote_path}", file=sys.stderr)
                return 1

            print(f"\nFile Information:")
            print(f"  Path: {result['path']}")
            print(f"  Size: {result['size_bytes']:,} bytes")
            print(f"  Type: {result['content_type']}")
            print(f"  Modified: {result.get('last_modified', 'N/A')}")
            print(f"  ETag: {result.get('etag', 'N/A')}")

        return 0

    except Exception as e:
        logger.error(f"Files command failed: {e}", exc_info=True)
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
