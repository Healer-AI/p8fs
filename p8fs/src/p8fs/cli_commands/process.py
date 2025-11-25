"""Process command for processing files/folders using storage worker."""

import sys
from pathlib import Path
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


async def process_command(args):
    """Process files or folders using storage worker."""
    try:
        from p8fs.workers.storage import StorageWorker

        path = Path(args.path).resolve()
        worker = StorageWorker(tenant_id=args.tenant_id)

        if path.is_dir():
            # Process folder
            results = await worker.process_folder(
                str(path),
                args.tenant_id,
                sync_mode=not args.force,  # Default to sync mode unless --force is used
                limit=args.limit
            )
            print(f"✅ Processed {results['success']} files, {results['failed']} failed")
            return 0 if results['failed'] == 0 else 1
        else:
            # Process single file
            await worker.process_file(str(path), args.tenant_id)
            print(f"✅ Processed {path.name}")
            return 0

    except Exception as e:
        logger.error(f"Process command failed: {e}", exc_info=True)
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
