#!/usr/bin/env python3
"""
Diagnostic script to trace user files across TiDB database and S3 storage.

This script verifies data collection and consistency for a given tenant by:
1. Querying TiDB for resources and files
2. Checking S3 bucket contents
3. Verifying data consistency between database and storage

Requirements:
- TiDB port-forwarded to localhost:4000
- SeaweedFS S3 port-forwarded to localhost:8333
- S3 credentials available in cluster secrets

Usage:
    # With port forwards already established
    uv run python scripts/diagnostic_tracing_user_files.py --tenant-id tenant-05344896230b819b

    # Script will check if port forwards are needed
    uv run python scripts/diagnostic_tracing_user_files.py --tenant-id tenant-05344896230b819b --setup-ports
"""

import argparse
import sys
import pymysql
import boto3
from typing import Dict, List, Tuple


def print_section(title: str, char: str = "="):
    """Print a formatted section header."""
    print(f"\n{char * 80}")
    print(title)
    print(f"{char * 80}\n")


def check_tidb_data(tenant_id: str, host: str = "localhost", port: int = 4000) -> Tuple[List[Dict], List[Dict]]:
    """Query TiDB for resources and files for the given tenant."""
    print_section(f"Checking TiDB for tenant: {tenant_id}")

    conn = pymysql.connect(
        host=host,
        port=port,
        user="root",
        database="public",
        cursorclass=pymysql.cursors.DictCursor
    )

    cursor = conn.cursor()

    # Check resources
    print("--- RESOURCES ---")
    cursor.execute("""
        SELECT id, name, category, LENGTH(content) as content_length,
               created_at, updated_at, tenant_id
        FROM resources
        WHERE tenant_id = %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (tenant_id,))

    resources = cursor.fetchall()
    print(f"Found {len(resources)} resources\n")

    for r in resources:
        print(f"ID: {r['id']}")
        print(f"  Name: {r['name']}")
        print(f"  Category: {r['category']}")
        print(f"  Content Length: {r['content_length']} bytes")
        print(f"  Created: {r['created_at']}")
        print()

    # Check files
    print("--- FILES ---")
    cursor.execute("""
        SELECT *
        FROM files
        WHERE tenant_id = %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (tenant_id,))

    files = cursor.fetchall()
    print(f"Found {len(files)} files\n")

    for f in files:
        print(f"ID: {f['id']}")
        print(f"  URI: {f.get('uri', 'N/A')}")
        print(f"  MIME Type: {f.get('mime_type', 'N/A')}")
        print(f"  File Size: {f.get('file_size', 'N/A')} bytes")
        print(f"  Content Hash: {f.get('content_hash', 'N/A')[:16] if f.get('content_hash') else 'N/A'}...")
        print(f"  Created: {f['created_at']}")
        print()

    cursor.close()
    conn.close()

    return resources, files


def check_s3_data(tenant_id: str, access_key: str, secret_key: str,
                  endpoint_url: str = "http://localhost:8333") -> Dict[str, int]:
    """Check S3 bucket contents for the given tenant."""
    print_section(f"Checking S3 bucket: {tenant_id}")

    s3_client = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='us-east-1'
    )

    try:
        response = s3_client.list_objects_v2(Bucket=tenant_id)

        s3_files = {}
        if 'Contents' in response:
            print(f"Found {len(response['Contents'])} objects\n")
            for obj in response['Contents']:
                s3_files[obj['Key']] = obj['Size']
                print(f"{obj['LastModified']}  {obj['Size']:>10} bytes  {obj['Key']}")
        else:
            print("Bucket is empty")

        return s3_files

    except Exception as e:
        print(f"Error accessing S3 bucket: {e}")
        return {}


def verify_consistency(tenant_id: str, db_files: List[Dict], s3_files: Dict[str, int]):
    """Verify data consistency between database and S3."""
    print_section("DATA CONSISTENCY VERIFICATION", "-")

    missing_in_s3 = []
    size_mismatches = []
    verified = []

    for db_file in db_files:
        # Extract S3 key from URI by removing the bucket prefix
        uri = db_file['uri']
        # URI format: /buckets/tenant-05344896230b819b/uploads/...
        # S3 key format: uploads/...
        s3_key = uri.split(f'/buckets/{tenant_id}/')[-1]

        db_size = int(db_file['file_size']) if db_file['file_size'] else 0

        print(f"\nFile: {db_file['id']}")
        print(f"  Database URI: {uri}")
        print(f"  S3 Key: {s3_key}")
        print(f"  Database Size: {db_size} bytes")

        if s3_key in s3_files:
            s3_size = s3_files[s3_key]
            print(f"  S3 Size: {s3_size} bytes")

            if db_size == s3_size:
                print(f"  ✓ VERIFIED - Sizes match")
                verified.append(db_file['id'])
            else:
                print(f"  ✗ SIZE MISMATCH - DB: {db_size}, S3: {s3_size}")
                size_mismatches.append({
                    'id': db_file['id'],
                    'uri': uri,
                    'db_size': db_size,
                    's3_size': s3_size
                })
        else:
            print(f"  ✗ MISSING IN S3")
            missing_in_s3.append({
                'id': db_file['id'],
                'uri': uri,
                's3_key': s3_key
            })

    # Check for files in S3 not in database
    print("\n" + "-" * 80)
    print("FILES IN S3 NOT IN DATABASE")
    print("-" * 80)

    db_s3_keys = set()
    for db_file in db_files:
        uri = db_file['uri']
        s3_key = uri.split(f'/buckets/{tenant_id}/')[-1]
        db_s3_keys.add(s3_key)

    orphaned_s3_files = []
    for s3_key in s3_files:
        if s3_key not in db_s3_keys:
            orphaned_s3_files.append(s3_key)
            print(f"  {s3_key} ({s3_files[s3_key]} bytes)")

    if not orphaned_s3_files:
        print("  None")

    # Summary
    print_section("SUMMARY", "=")
    print(f"Total database records: {len(db_files)}")
    print(f"Total S3 objects: {len(s3_files)}")
    print(f"Verified (matching): {len(verified)}")
    print(f"Missing in S3: {len(missing_in_s3)}")
    print(f"Size mismatches: {len(size_mismatches)}")
    print(f"Orphaned in S3 (not in DB): {len(orphaned_s3_files)}")

    if len(verified) == len(db_files) and len(missing_in_s3) == 0 and len(size_mismatches) == 0:
        print("\n✓ DATA COLLECTION IS WORKING CORRECTLY")
        print("  - All database files exist in S3 with matching sizes")
        if orphaned_s3_files:
            print(f"  - {len(orphaned_s3_files)} extra file(s) in S3 (possibly from earlier uploads)")
    else:
        print("\n✗ DATA INCONSISTENCIES DETECTED")
        if missing_in_s3:
            print(f"  - {len(missing_in_s3)} files missing in S3")
        if size_mismatches:
            print(f"  - {len(size_mismatches)} files with size mismatches")

    return {
        'verified': len(verified),
        'missing_in_s3': len(missing_in_s3),
        'size_mismatches': len(size_mismatches),
        'orphaned_in_s3': len(orphaned_s3_files)
    }


def main():
    parser = argparse.ArgumentParser(
        description='Trace user files across TiDB and S3 storage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with existing port forwards
  uv run python scripts/diagnostic_tracing_user_files.py --tenant-id tenant-05344896230b819b

  # Use custom ports
  uv run python scripts/diagnostic_tracing_user_files.py \\
    --tenant-id tenant-05344896230b819b \\
    --tidb-port 4001 \\
    --s3-endpoint http://localhost:8888

Port Forwarding:
  Before running this script, establish port forwards:

  # TiDB
  kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000 &

  # SeaweedFS S3
  kubectl port-forward -n seaweed svc/seaweedfs-s3 8333:8333 &

S3 Credentials:
  Get credentials from cluster:
  kubectl get secret seaweedfs-s3-config -n p8fs -o yaml
        """
    )

    parser.add_argument(
        '--tenant-id',
        required=True,
        help='Tenant ID to trace (e.g., tenant-05344896230b819b)'
    )

    parser.add_argument(
        '--tidb-host',
        default='localhost',
        help='TiDB host (default: localhost)'
    )

    parser.add_argument(
        '--tidb-port',
        type=int,
        default=4000,
        help='TiDB port (default: 4000)'
    )

    parser.add_argument(
        '--s3-endpoint',
        default='http://localhost:8333',
        help='S3 endpoint URL (default: http://localhost:8333)'
    )

    parser.add_argument(
        '--s3-access-key',
        default='p8fs-admin-access',
        help='S3 access key (default: p8fs-admin-access)'
    )

    parser.add_argument(
        '--s3-secret-key',
        default='r52xFgeWpX4qnJRW78QtlhlbOt7JghMHTXwaTo2vH/o=',
        help='S3 secret key'
    )

    args = parser.parse_args()

    try:
        # Check TiDB
        resources, files = check_tidb_data(
            args.tenant_id,
            host=args.tidb_host,
            port=args.tidb_port
        )

        # Check S3
        s3_files = check_s3_data(
            args.tenant_id,
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            endpoint_url=args.s3_endpoint
        )

        # Verify consistency
        if files:
            results = verify_consistency(args.tenant_id, files, s3_files)

            # Exit with appropriate code
            if results['missing_in_s3'] > 0 or results['size_mismatches'] > 0:
                sys.exit(1)
        else:
            print("\nNo files found in database to verify against S3")

        sys.exit(0)

    except pymysql.Error as e:
        print(f"\n✗ Database error: {e}", file=sys.stderr)
        print("\nMake sure TiDB is port-forwarded:")
        print("  kubectl port-forward -n tikv-cluster svc/fresh-cluster-tidb 4000:4000")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
