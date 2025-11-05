#!/usr/bin/env python3
"""
Test S3 upload to verify SeaweedFS server is working correctly.
Tests upload to s3.eepis.ai using P8FS credentials.
"""

import boto3
import os
from datetime import datetime
from botocore.client import Config

def main():
    # P8FS S3 credentials from environment or defaults from cluster
    access_key = os.getenv("P8FS_SEAWEEDFS_ACCESS_KEY", os.getenv("P8FS_S3_ACCESS_KEY", "p8fs-admin-access"))
    secret_key = os.getenv("P8FS_SEAWEEDFS_SECRET_KEY", os.getenv("P8FS_S3_SECRET_ACCESS_KEY", "r52xFgeWpX4qnJRW78QtlhlbOt7JghMHTXwaTo2vH/o="))
    endpoint = os.getenv("P8FS_SEAWEEDFS_S3_ENDPOINT", "https://s3.eepis.ai")

    print(f"Testing S3 upload to {endpoint}")
    print(f"Access Key: {access_key}")
    print(f"Secret Key: {secret_key[:10]}...")

    # S3 client with proper configuration - disable SSL verification for self-signed certs
    # IMPORTANT: disable_chunked_encoding is required for SeaweedFS compatibility
    # See: https://github.com/seaweedfs/seaweedfs/issues/7024
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={
                "addressing_style": "path",
                "payload_signing_enabled": False
            },
            # Disable chunked encoding for SeaweedFS compatibility
            disable_chunked_encoding=True
        ),
        verify=False  # Disable SSL verification for self-signed certificates
    )

    # Upload path format: tenant-test/uploads/yyyy/mm/dd/test.txt
    now = datetime.utcnow()
    s3_key = f"uploads/{now.strftime('%Y/%m/%d')}/boto3_test_{int(now.timestamp())}.txt"
    bucket = "tenant-test"

    # Test content
    test_data = f"P8FS boto3 test upload {now.isoformat()}\nThis file should have content!\n"

    print(f"\nUploading to: {endpoint}/{bucket}/{s3_key}")
    print(f"Content length: {len(test_data)} bytes")

    try:
        # Upload WITHOUT Content-MD5 (let boto3/SeaweedFS handle it)
        # Note: boto3 calculates Content-MD5 automatically unless disabled
        response = s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=test_data.encode('utf-8'),
            ContentType="text/plain",
            # Don't set ContentMD5 - let boto3 calculate it or omit it
        )
        print(f"✅ Upload successful!")
        print(f"   ETag: {response.get('ETag', 'N/A')}")
        print(f"   URL: {endpoint}/{bucket}/{s3_key}")

        # Try to download and verify
        print(f"\nDownloading back to verify...")
        try:
            get_response = s3.get_object(Bucket=bucket, Key=s3_key)
            downloaded_content = get_response['Body'].read()
            print(f"✅ Download successful!")
            print(f"   Downloaded size: {len(downloaded_content)} bytes")
            print(f"   Content matches: {downloaded_content.decode('utf-8') == test_data}")
            print(f"   Content preview: {downloaded_content.decode('utf-8')[:100]}")

            if len(downloaded_content) == 0:
                print("❌ ERROR: Downloaded file is 0 bytes! Server is broken.")
            elif downloaded_content.decode('utf-8') != test_data:
                print("❌ ERROR: Downloaded content doesn't match uploaded content!")
            else:
                print("✅ SUCCESS: File uploaded and downloaded correctly!")

        except Exception as e:
            print(f"⚠️  Download failed: {e}")

    except Exception as e:
        print(f"❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
