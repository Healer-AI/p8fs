"""Integration tests for SeaweedFS presigned URL support.

Tests whether SeaweedFS properly supports AWS S3-style presigned URLs
for direct file uploads without authentication.
"""

import pytest
import boto3
import requests
from botocore.exceptions import ClientError
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

# Suppress SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)


@pytest.fixture
def s3_client():
    """Create S3 client for SeaweedFS."""
    import botocore

    # Disable SSL verification for self-signed certificates
    return boto3.client(
        's3',
        endpoint_url=config.seaweedfs_s3_endpoint,
        aws_access_key_id=config.seaweedfs_access_key,
        aws_secret_access_key=config.seaweedfs_secret_key,
        region_name='us-east-1',
        verify=False,  # Disable SSL verification for self-signed certs
        config=botocore.config.Config(signature_version='s3v4')
    )


@pytest.mark.integration
def test_seaweedfs_presigned_put_url(s3_client):
    """Test SeaweedFS presigned PUT URL generation and usage.

    This test verifies:
    1. Presigned URLs can be generated
    2. Files can be uploaded using presigned URLs without authentication
    3. Files are accessible after upload

    Uses P8FS path convention: uploads/{YYYY}/{MM}/{DD}/{filename}
    """
    from datetime import datetime

    # P8FS convention: bucket = tenant_id
    bucket = config.default_tenant_id

    # P8FS convention: uploads/{YYYY}/{MM}/{DD}/{filename}
    now = datetime.utcnow()
    date_path = now.strftime("%Y/%m/%d")
    key = f"uploads/{date_path}/presigned-upload-test.txt"

    test_content = b"Test content for presigned URL upload"

    try:
        # Step 1: Generate presigned PUT URL
        logger.info(f"Generating presigned PUT URL for s3://{bucket}/{key}")

        try:
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket,
                    'Key': key,
                    'ContentType': 'text/plain'
                },
                ExpiresIn=3600
            )
            logger.info(f"Generated presigned URL: {presigned_url[:100]}...")

        except Exception as e:
            pytest.skip(f"SeaweedFS presigned URL generation not supported: {e}")

        # Step 2: Upload using presigned URL (no AWS credentials)
        logger.info("Uploading file using presigned URL...")

        response = requests.put(
            presigned_url,
            data=test_content,
            headers={'Content-Type': 'text/plain'},
            verify=False  # Disable SSL verification for self-signed certs
        )

        assert response.status_code in [200, 204], \
            f"Upload failed with status {response.status_code}: {response.text}"

        logger.info(f"Upload successful: {response.status_code}")

        # Step 3: Verify file exists and content matches
        logger.info("Verifying uploaded file...")

        obj = s3_client.get_object(Bucket=bucket, Key=key)
        uploaded_content = obj['Body'].read()

        assert uploaded_content == test_content, \
            "Uploaded content doesn't match original"

        logger.info("✓ SeaweedFS presigned PUT URLs work correctly")

    finally:
        # Cleanup
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info("Cleaned up test file")
        except Exception as e:
            logger.warning(f"Failed to cleanup test file: {e}")


@pytest.mark.integration
def test_seaweedfs_presigned_get_url(s3_client):
    """Test SeaweedFS presigned GET URL for file downloads.

    Uses P8FS path convention: uploads/{YYYY}/{MM}/{DD}/{filename}
    """
    from datetime import datetime

    # P8FS convention
    bucket = config.default_tenant_id
    now = datetime.utcnow()
    date_path = now.strftime("%Y/%m/%d")
    key = f"uploads/{date_path}/presigned-download-test.txt"
    test_content = b"Test content for presigned URL download"

    try:
        # Upload test file
        logger.info(f"Uploading test file to s3://{bucket}/{key}")
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=test_content,
            ContentType='text/plain'
        )

        # Generate presigned GET URL
        logger.info("Generating presigned GET URL...")

        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket,
                    'Key': key
                },
                ExpiresIn=3600
            )
            logger.info(f"Generated presigned URL: {presigned_url[:100]}...")

        except Exception as e:
            pytest.skip(f"SeaweedFS presigned URL generation not supported: {e}")

        # Download using presigned URL (no AWS credentials)
        logger.info("Downloading file using presigned URL...")

        response = requests.get(presigned_url, verify=False)

        assert response.status_code == 200, \
            f"Download failed with status {response.status_code}: {response.text}"

        assert response.content == test_content, \
            "Downloaded content doesn't match original"

        logger.info("✓ SeaweedFS presigned GET URLs work correctly")

    finally:
        # Cleanup
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info("Cleaned up test file")
        except Exception as e:
            logger.warning(f"Failed to cleanup test file: {e}")


@pytest.mark.integration
def test_seaweedfs_presigned_url_expiration(s3_client):
    """Test that expired presigned URLs are rejected.

    Uses P8FS path convention: uploads/{YYYY}/{MM}/{DD}/{filename}
    """
    from datetime import datetime

    # P8FS convention
    bucket = config.default_tenant_id
    now = datetime.utcnow()
    date_path = now.strftime("%Y/%m/%d")
    key = f"uploads/{date_path}/presigned-expiration-test.txt"

    try:
        # Generate presigned URL with 1 second expiration
        logger.info("Generating presigned URL with 1 second expiration...")

        try:
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket,
                    'Key': key
                },
                ExpiresIn=1  # 1 second
            )
        except Exception as e:
            pytest.skip(f"SeaweedFS presigned URL generation not supported: {e}")

        # Wait for expiration
        import time
        time.sleep(2)

        # Try to upload with expired URL
        logger.info("Attempting upload with expired URL...")

        response = requests.put(
            presigned_url,
            data=b"Should fail",
            headers={'Content-Type': 'text/plain'},
            verify=False
        )

        # Should get 403 Forbidden or similar
        assert response.status_code >= 400, \
            "Expired presigned URL should be rejected"

        logger.info(f"✓ Expired URL rejected with status {response.status_code}")

    finally:
        # Cleanup (in case upload somehow succeeded)
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
        except:
            pass


@pytest.mark.integration
def test_seaweedfs_direct_upload_fallback(s3_client):
    """Test direct upload as fallback if presigned URLs don't work.

    This tests the alternative approach: returning the S3 endpoint URL
    and using basic auth credentials for upload.

    Uses P8FS path convention: uploads/{YYYY}/{MM}/{DD}/{filename}
    """
    from datetime import datetime

    # P8FS convention
    bucket = config.default_tenant_id
    now = datetime.utcnow()
    date_path = now.strftime("%Y/%m/%d")
    key = f"uploads/{date_path}/direct-upload-test.txt"
    test_content = b"Test content for direct upload"

    try:
        # Construct direct upload URL
        direct_url = f"{config.seaweedfs_s3_endpoint}/{bucket}/{key}"

        logger.info(f"Testing direct upload to {direct_url}")

        # Upload with basic auth
        from requests.auth import HTTPBasicAuth

        response = requests.put(
            direct_url,
            data=test_content,
            headers={'Content-Type': 'text/plain'},
            auth=HTTPBasicAuth(
                config.seaweedfs_access_key,
                config.seaweedfs_secret_key
            ),
            verify=False
        )

        assert response.status_code in [200, 204], \
            f"Direct upload failed with status {response.status_code}: {response.text}"

        logger.info(f"✓ Direct upload works as fallback: {response.status_code}")

        # Verify file exists
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        uploaded_content = obj['Body'].read()

        assert uploaded_content == test_content

    finally:
        # Cleanup
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info("Cleaned up test file")
        except Exception as e:
            logger.warning(f"Failed to cleanup test file: {e}")


@pytest.mark.integration
def test_determine_seaweedfs_upload_strategy():
    """Determine the best upload strategy for SeaweedFS.

    This test runs all strategies and reports which ones work.
    """
    logger.info("=" * 70)
    logger.info("SEAWEEDFS UPLOAD STRATEGY DETERMINATION")
    logger.info("=" * 70)

    import botocore

    # Disable SSL verification for self-signed certificates
    s3_client = boto3.client(
        's3',
        endpoint_url=config.seaweedfs_s3_endpoint,
        aws_access_key_id=config.seaweedfs_access_key,
        aws_secret_access_key=config.seaweedfs_secret_key,
        region_name='us-east-1',
        verify=False,
        config=botocore.config.Config(signature_version='s3v4')
    )

    strategies = {
        "presigned_put": False,
        "presigned_get": False,
        "direct_upload_basic_auth": False,
        "standard_s3_put": False
    }

    # P8FS convention: bucket = tenant_id
    bucket = config.default_tenant_id
    test_content = b"Strategy test content"

    # P8FS path convention
    from datetime import datetime
    now = datetime.utcnow()
    date_path = now.strftime("%Y/%m/%d")

    # Test 1: Presigned PUT
    try:
        key = f"uploads/{date_path}/strategy-presigned-put.txt"
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=300
        )
        response = requests.put(presigned_url, data=test_content, verify=False)
        if response.status_code in [200, 204]:
            strategies["presigned_put"] = True
            logger.info("✓ Presigned PUT URLs: SUPPORTED")
        s3_client.delete_object(Bucket=bucket, Key=key)
    except Exception as e:
        logger.warning(f"✗ Presigned PUT URLs: NOT SUPPORTED ({e})")

    # Test 2: Presigned GET
    try:
        key = f"uploads/{date_path}/strategy-presigned-get.txt"
        s3_client.put_object(Bucket=bucket, Key=key, Body=test_content)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=300
        )
        response = requests.get(presigned_url, verify=False)
        if response.status_code == 200:
            strategies["presigned_get"] = True
            logger.info("✓ Presigned GET URLs: SUPPORTED")
        s3_client.delete_object(Bucket=bucket, Key=key)
    except Exception as e:
        logger.warning(f"✗ Presigned GET URLs: NOT SUPPORTED ({e})")

    # Test 3: Direct upload with basic auth
    try:
        key = f"uploads/{date_path}/strategy-direct-upload.txt"
        direct_url = f"{config.seaweedfs_s3_endpoint}/{bucket}/{key}"
        from requests.auth import HTTPBasicAuth
        response = requests.put(
            direct_url,
            data=test_content,
            auth=HTTPBasicAuth(
                config.seaweedfs_access_key,
                config.seaweedfs_secret_key
            ),
            verify=False
        )
        if response.status_code in [200, 204]:
            strategies["direct_upload_basic_auth"] = True
            logger.info("✓ Direct upload with basic auth: SUPPORTED")
        s3_client.delete_object(Bucket=bucket, Key=key)
    except Exception as e:
        logger.warning(f"✗ Direct upload with basic auth: NOT SUPPORTED ({e})")

    # Test 4: Standard S3 PUT
    try:
        key = f"uploads/{date_path}/strategy-s3-put.txt"
        s3_client.put_object(Bucket=bucket, Key=key, Body=test_content)
        strategies["standard_s3_put"] = True
        logger.info("✓ Standard S3 PUT: SUPPORTED")
        s3_client.delete_object(Bucket=bucket, Key=key)
    except Exception as e:
        logger.warning(f"✗ Standard S3 PUT: NOT SUPPORTED ({e})")

    logger.info("=" * 70)
    logger.info("RECOMMENDATION:")

    if strategies["presigned_put"]:
        logger.info("✓ Use presigned PUT URLs for MCP file uploads")
    elif strategies["direct_upload_basic_auth"]:
        logger.info("⚠ Use direct upload with credentials (presigned URLs not available)")
    else:
        logger.info("✗ No suitable upload strategy found - check SeaweedFS configuration")

    logger.info("=" * 70)

    # At least one strategy should work
    assert any(strategies.values()), \
        "No upload strategy works - SeaweedFS may not be configured correctly"
