"""
S3 storage service for SeaweedFS with AWS v4 signing.

Content-MD5 Header Configuration
=================================

By default, this service includes the Content-MD5 header for proper AWS S3 compliance
and data integrity verification.

IMPORTANT: Some SeaweedFS S3 servers have a bug where the Content-MD5 header causes
a 500 Internal Server Error during PUT operations. This affects:
- s3.eepis.ai (confirmed broken)
- Other older SeaweedFS instances may also be affected

Working servers that support Content-MD5:
- s3.percolationlabs.ai (confirmed working)
- AWS S3 (standard)
- Most modern S3-compatible servers

Symptoms of the bug:
- PUT requests return 500 Internal Server Error
- Error message: "We encountered an internal error, please try again"
- Same request works perfectly without Content-MD5 header

Solution:
- Default: use_content_md5=True (AWS S3 standard compliance)
- If your server has issues, pass use_content_md5=False to constructor
- SHA-256 hash is always calculated for data integrity verification

See docs/11-seaweedfs-events.md for full details.
"""

import base64
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import quote, urlparse

import httpx
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class AWSV4Signer:
    """AWS Signature Version 4 request signer for SeaweedFS S3 compatibility."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        service: str = "s3",
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.service = service

    def _sign(self, key: bytes, msg: str) -> bytes:
        """Sign a message with a key using HMAC SHA256."""
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(self, date_stamp: str) -> bytes:
        """Generate the signing key."""
        k_date = self._sign(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, "aws4_request")
        return k_signing

    def sign_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: bytes = b"",
    ) -> dict[str, str]:
        """
        Sign an HTTP request with AWS Signature Version 4.

        Args:
            method: HTTP method (GET, PUT, POST, DELETE)
            url: Full URL including scheme, host, path, and query
            headers: Request headers dict
            payload: Request body bytes

        Returns:
            Headers dict with Authorization header added
        """
        from urllib.parse import parse_qs, urlencode

        # Parse URL
        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"
        query = parsed.query

        # Get current time
        t = datetime.utcnow()
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = t.strftime("%Y%m%d")

        # Calculate payload hash
        payload_hash = hashlib.sha256(payload).hexdigest()

        # Add required headers
        headers_to_sign = headers.copy()
        headers_to_sign["Host"] = host
        headers_to_sign["X-Amz-Date"] = amz_date
        headers_to_sign["X-Amz-Content-Sha256"] = payload_hash

        # Create canonical URI - URL encode each path segment
        if not path:
            canonical_uri = "/"
        else:
            segments = path.split("/")
            encoded_segments = [quote(segment, safe="") for segment in segments]
            canonical_uri = "/".join(encoded_segments)

        # Create canonical query string - parse, sort, and encode
        if not query:
            canonical_querystring = ""
        else:
            params = parse_qs(query, keep_blank_values=True)
            sorted_params = []
            for key in sorted(params.keys()):
                for value in sorted(params[key]):
                    encoded_key = quote(key, safe="")
                    encoded_value = quote(value, safe="")
                    sorted_params.append(f"{encoded_key}={encoded_value}")
            canonical_querystring = "&".join(sorted_params)

        # Create canonical headers - lowercase, sort, format with newline at end
        canonical_headers_dict = {}
        for key, value in headers_to_sign.items():
            canonical_headers_dict[key.lower()] = " ".join(value.split())

        sorted_headers = sorted(canonical_headers_dict.items())
        canonical_headers = "\n".join([f"{key}:{value}" for key, value in sorted_headers]) + "\n"
        signed_headers = ";".join([key for key, _ in sorted_headers])

        # Create canonical request
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_querystring,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )

        # Create string to sign
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        string_to_sign = "\n".join(
            [
                algorithm,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )

        # Calculate signature
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Create authorization header
        authorization_header = (
            f"{algorithm} Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        # Add authorization to headers
        headers_to_sign["Authorization"] = authorization_header

        return headers_to_sign


class S3StorageService:
    """Service for S3 operations with SeaweedFS backend."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        use_content_md5: bool = True,
    ):
        """
        Initialize S3 storage service.

        Args:
            endpoint: S3 endpoint URL (defaults to config.seaweedfs_s3_endpoint)
            access_key: S3 access key (defaults to config.seaweedfs_access_key)
            secret_key: S3 secret key (defaults to config.seaweedfs_secret_key)
            use_content_md5: Whether to include Content-MD5 header (default: True)
                           Set to False if your S3 server has issues with Content-MD5.
                           Some SeaweedFS servers return 500 errors with Content-MD5.
                           See module docstring for details.
        """
        self.endpoint = endpoint or config.seaweedfs_s3_endpoint
        self.access_key = access_key or config.seaweedfs_access_key
        self.secret_key = secret_key or config.seaweedfs_secret_key
        self.use_content_md5 = use_content_md5
        self.signer = AWSV4Signer(self.access_key, self.secret_key)

    def _build_s3_url(self, tenant_id: str, path: str) -> str:
        """Build S3 URL for a tenant and path."""
        clean_path = path.lstrip("/")
        return f"{self.endpoint}/{tenant_id}/{clean_path}"

    async def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        tenant_id: str,
        content_type: str = "application/octet-stream",
        multipart_threshold: int = 8 * 1024 * 1024,
        multipart_chunksize: int = 8 * 1024 * 1024,
        max_concurrent_requests: int = 10,
        progress_callback: callable = None,
    ) -> dict[str, Any]:
        """
        Upload a file to S3 with automatic multipart upload for large files.

        Uses AWS CLI strategy:
        - Single PUT for files < multipart_threshold (8MB default)
        - Multipart upload for files >= multipart_threshold
        - 8MB chunks, up to 10 concurrent requests

        Args:
            local_path: Local file path
            remote_path: Remote path (will be prefixed with uploads/YYYY/MM/DD/)
            tenant_id: Tenant ID
            content_type: Content type
            multipart_threshold: Size threshold for multipart upload (default 8MB)
            multipart_chunksize: Size of each part (default 8MB)
            max_concurrent_requests: Max concurrent part uploads (default 10)
            progress_callback: Optional progress callback function

        Returns:
            Upload response with file metadata
        """
        # Get file size
        file_size = local_path.stat().st_size

        # Build date-partitioned path
        now = datetime.utcnow()
        date_path = now.strftime("%Y/%m/%d")
        filename = remote_path.split("/")[-1]
        upload_path = f"uploads/{date_path}/{filename}"

        # Build S3 URL
        s3_url = self._build_s3_url(tenant_id, upload_path)

        logger.info(
            f"Uploading {local_path.name} ({file_size:,} bytes / {file_size/1024/1024:.1f} MB) to {upload_path}"
        )

        # Decide between single PUT or multipart upload
        if file_size < multipart_threshold:
            logger.info(f"Using single PUT upload (file < {multipart_threshold/1024/1024:.1f}MB)")

            result = await self._single_put_upload(
                local_path, s3_url, upload_path, content_type, file_size
            )
        else:
            logger.info(f"Using multipart upload (file >= {multipart_threshold/1024/1024:.1f}MB)")

            result = await self._multipart_upload(
                local_path, s3_url, upload_path, content_type, file_size,
                multipart_chunksize, max_concurrent_requests, progress_callback
            )

        return {
            "path": upload_path,
            "size_bytes": file_size,
            "content_type": content_type,
            "tenant_id": tenant_id,
            "created_at": now.isoformat(),
            **result,
        }

    async def _single_put_upload(
        self,
        local_path: Path,
        s3_url: str,
        upload_path: str,
        content_type: str,
        file_size: int,
    ) -> dict[str, Any]:
        """
        Handle single PUT upload for small files.

        Content-MD5 is included by default for AWS S3 compliance.
        Set use_content_md5=False if your server has compatibility issues.

        Some older SeaweedFS servers (including s3.eepis.ai) return 500 Internal Server Error
        when Content-MD5 header is included. This is a known SeaweedFS bug.

        AWS CLI compatibility notes:
        - Content-Type: proper MIME type (included)
        - Host: must match endpoint (auto-added by signer)
        - Content-MD5: included by default (can be disabled via use_content_md5=False)

        Based on reference: mr_saoirse/p8-fs files.py:248-329
        """
        # Read file data
        with open(local_path, "rb") as f:
            file_data = f.read()

        # Prepare headers
        headers = {
            "Content-Type": content_type,
        }

        # Add Content-MD5 for AWS S3 compliance (enabled by default)
        # IMPORTANT: Some older SeaweedFS servers (s3.eepis.ai) return 500 errors with Content-MD5
        # If your server has issues, initialize with use_content_md5=False
        content_md5 = None
        if self.use_content_md5:
            logger.debug("Calculating MD5 hash for Content-MD5 header...")
            md5_hash = hashlib.md5(file_data).digest()
            content_md5 = base64.b64encode(md5_hash).decode("ascii")
            headers["Content-MD5"] = content_md5
            logger.debug(f"Content-MD5: {content_md5}")

        # Sign the request
        signed_headers = self.signer.sign_request("PUT", s3_url, headers, file_data)

        # Upload using httpx async client
        logger.debug("Starting single PUT upload matching AWS CLI...")
        logger.debug(f"PUT {s3_url}")
        logger.debug(f"Content size: {len(file_data)} bytes")
        logger.debug(f"Headers: {list(signed_headers.keys())}")

        # Log full request for debugging
        logger.debug(f"Request body first 100 bytes: {file_data[:100]}")

        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            # Build request manually to inspect
            request = client.build_request(
                "PUT", s3_url, headers=signed_headers, content=file_data
            )
            logger.debug(f"Request content length from httpx: {len(request.content) if request.content else 0}")

            # Send the request
            response = await client.send(request)

        logger.debug(f"Upload response: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")

        if response.status_code not in [200, 201]:
            raise RuntimeError(
                f"Single PUT upload failed: {response.status_code} - {response.text}"
            )

        logger.info("Single PUT upload completed successfully")

        result = {"upload_method": "single_put"}
        if content_md5:
            result["md5"] = content_md5
        return result

    async def _multipart_upload(
        self,
        local_path: Path,
        s3_url: str,
        upload_path: str,
        content_type: str,
        file_size: int,
        chunk_size: int,
        max_concurrent: int,
        progress_callback: callable = None,
    ) -> dict[str, Any]:
        """
        Handle multipart upload for large files.

        Based on reference: mr_saoirse/p8-fs files.py:331-476
        """
        import xml.etree.ElementTree as ET
        import asyncio

        # Step 1: Initiate multipart upload
        logger.debug("Initiating multipart upload...")

        init_url = f"{s3_url}?uploads"
        init_headers = {"Content-Type": content_type}
        signed_headers = self.signer.sign_request("POST", init_url, init_headers, b"")

        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.post(init_url, headers=signed_headers)

        if response.status_code not in [200, 201]:
            raise RuntimeError(
                f"Failed to initiate multipart upload: {response.status_code} {response.text}"
            )

        # Parse upload ID from response
        try:
            logger.debug(f"Multipart init response: {response.text}")
            root = ET.fromstring(response.text)

            upload_id_element = (
                root.find(".//{https://s3.amazonaws.com/doc/2006-03-01/}UploadId")
                or root.find(".//UploadId")
                or root.find(".//{http://s3.amazonaws.com/doc/2006-03-01/}UploadId")
            )

            if upload_id_element is None:
                raise RuntimeError(
                    f"UploadId not found in response: {response.text}"
                )

            upload_id = upload_id_element.text
            logger.info(f"Multipart upload initiated with ID: {upload_id}")
        except Exception as e:
            raise RuntimeError(f"Failed to parse upload ID from response: {e}")

        # Step 2: Upload parts
        num_parts = (file_size + chunk_size - 1) // chunk_size
        logger.info(
            f"Uploading {num_parts} parts of {chunk_size/1024/1024:.1f}MB each"
        )

        parts_info = []
        semaphore = asyncio.Semaphore(max_concurrent)
        uploaded_bytes = 0

        async def upload_part(
            part_number: int, start: int, end: int
        ) -> Tuple[int, str]:
            """Upload a single part"""
            nonlocal uploaded_bytes
            async with semaphore:
                result = await self._upload_single_part(
                    local_path, s3_url, upload_id, part_number, start, end
                )

                # Update progress tracking
                part_size = end - start
                uploaded_bytes += part_size

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(
                        part_number, num_parts, part_size, uploaded_bytes, file_size
                    )

                return result

        # Create upload tasks
        tasks = []
        for i in range(num_parts):
            part_number = i + 1
            start = i * chunk_size
            end = min(start + chunk_size, file_size)

            task = upload_part(part_number, start, end)
            tasks.append(task)

        # Execute uploads concurrently
        try:
            parts_results = await asyncio.gather(*tasks)
            parts_info = [(part_num, etag) for part_num, etag in parts_results]
            parts_info.sort()
        except Exception as e:
            logger.error(f"Part upload failed: {e}")
            await self._abort_multipart_upload(s3_url, upload_id)
            raise RuntimeError(f"Multipart upload failed: {e}")

        # Step 3: Complete multipart upload
        logger.debug("Completing multipart upload...")

        complete_url = f"{s3_url}?uploadId={upload_id}"
        complete_xml = self._build_complete_multipart_xml(parts_info)
        complete_xml_bytes = complete_xml.encode("utf-8")

        complete_headers = {"Content-Type": "application/xml"}
        signed_complete_headers = self.signer.sign_request(
            "POST", complete_url, complete_headers, complete_xml_bytes
        )

        async with httpx.AsyncClient(verify=False, timeout=120.0) as client:
            response = await client.post(
                complete_url, headers=signed_complete_headers, content=complete_xml_bytes
            )

        if response.status_code not in [200, 201]:
            raise RuntimeError(
                f"Failed to complete multipart upload: {response.status_code} {response.text}"
            )

        logger.info("Multipart upload completed successfully!")

        # Calculate overall file hash
        file_hash = await self._calculate_file_hash(local_path)

        return {
            "upload_method": "multipart",
            "parts": len(parts_info),
            "sha256": file_hash,
        }

    async def _upload_single_part(
        self,
        local_path: Path,
        s3_url: str,
        upload_id: str,
        part_number: int,
        start: int,
        end: int,
    ) -> Tuple[int, str]:
        """Upload a single part of the multipart upload"""
        part_size = end - start
        logger.debug(
            f"Uploading part {part_number}: {start}-{end} ({part_size:,} bytes)"
        )

        # Read part data
        with open(local_path, "rb") as f:
            f.seek(start)
            part_data = f.read(part_size)

        part_url = f"{s3_url}?partNumber={part_number}&uploadId={upload_id}"

        headers = {"Content-Length": str(part_size)}

        # Sign the request with part data
        signed_headers = self.signer.sign_request("PUT", part_url, headers, part_data)

        # Upload the part
        async with httpx.AsyncClient(verify=False, timeout=300.0) as client:
            response = await client.put(
                part_url, headers=signed_headers, content=part_data
            )

        if response.status_code not in [200, 201]:
            raise RuntimeError(
                f"Failed to upload part {part_number}: {response.status_code} {response.text}"
            )

        etag = response.headers.get("ETag", "").strip('"')
        if not etag:
            raise RuntimeError(f"No ETag returned for part {part_number}")

        logger.debug(
            f"Part {part_number} uploaded successfully ({part_size:,} bytes, ETag: {etag})"
        )
        return part_number, etag

    async def _abort_multipart_upload(self, s3_url: str, upload_id: str):
        """Abort a multipart upload"""
        try:
            abort_url = f"{s3_url}?uploadId={upload_id}"
            headers = {}
            signed_headers = self.signer.sign_request("DELETE", abort_url, headers, b"")

            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                await client.delete(abort_url, headers=signed_headers)

            logger.info(f"Aborted multipart upload {upload_id}")
        except Exception as e:
            logger.warning(f"Failed to abort multipart upload {upload_id}: {e}")

    def _build_complete_multipart_xml(self, parts_info: List[Tuple[int, str]]) -> str:
        """Build XML for completing multipart upload"""
        xml_parts = []
        for part_number, etag in parts_info:
            xml_parts.append(f"  <Part>")
            xml_parts.append(f"    <PartNumber>{part_number}</PartNumber>")
            xml_parts.append(f'    <ETag>"{etag}"</ETag>')
            xml_parts.append(f"  </Part>")

        xml = f"""<CompleteMultipartUpload>
{chr(10).join(xml_parts)}
</CompleteMultipartUpload>"""
        return xml

    async def _calculate_file_hash(self, local_path: Path) -> str:
        """Calculate SHA-256 hash of entire file"""
        sha256_hash = hashlib.sha256()
        with open(local_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    async def download_file(
        self, remote_path: str, tenant_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Download a file from S3.

        Args:
            remote_path: Remote file path - can be:
                - Full path: /buckets/{tenant_id}/uploads/2025/10/11/file.pdf
                - Relative path: uploads/2025/10/11/file.pdf
            tenant_id: Tenant ID

        Returns:
            File data dict or None if not found
        """
        # Normalize path - remove /buckets/{tenant_id}/ prefix if present
        normalized_path = remote_path
        if normalized_path.startswith(f"/buckets/{tenant_id}/"):
            normalized_path = normalized_path.replace(f"/buckets/{tenant_id}/", "", 1)
        elif normalized_path.startswith(f"buckets/{tenant_id}/"):
            normalized_path = normalized_path.replace(f"buckets/{tenant_id}/", "", 1)

        s3_url = self._build_s3_url(tenant_id, normalized_path)

        # Sign GET request
        headers = {}
        signed_headers = self.signer.sign_request("GET", s3_url, headers, b"")

        logger.debug(f"GET {s3_url}")

        # Download
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.get(s3_url, headers=signed_headers)

        logger.debug(f"Response: {response.status_code}, Content-Length: {response.headers.get('content-length', 'unknown')}")

        if response.status_code == 404:
            logger.warning(f"File not found in S3: {s3_url}")
            return None

        if response.status_code != 200:
            raise RuntimeError(
                f"Download failed: {response.status_code} - {response.text}"
            )

        content_size = len(response.content)
        logger.info(f"Downloaded {normalized_path}: {content_size:,} bytes")

        return {
            "path": remote_path,
            "content": response.content,
            "size_bytes": content_size,
            "content_type": response.headers.get("content-type", "application/octet-stream"),
        }

    async def list_files(
        self, path: str, tenant_id: str, recursive: bool = False, limit: int = 100
    ) -> dict[str, Any]:
        """
        List files in a path.

        Args:
            path: Directory path
            tenant_id: Tenant ID
            recursive: List recursively
            limit: Maximum files to return

        Returns:
            List response with files
        """
        import xml.etree.ElementTree as ET

        # Build prefix
        clean_path = path.strip("/")
        if clean_path:
            prefix = f"uploads/{clean_path}"
        else:
            prefix = "uploads/"

        # Build list request URL
        base_url = self._build_s3_url(tenant_id, "")
        params = f"list-type=2&prefix={prefix}&max-keys={min(limit, 1000)}"
        if not recursive:
            params += "&delimiter=/"

        list_url = f"{base_url}?{params}"

        # Sign request
        headers = {}
        signed_headers = self.signer.sign_request("GET", list_url, headers, b"")

        # List objects
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.get(list_url, headers=signed_headers)

        if response.status_code == 404:
            return {"files": [], "total": 0, "path": path}

        if response.status_code != 200:
            raise RuntimeError(f"List failed: {response.status_code} - {response.text}")

        # Parse XML response
        root = ET.fromstring(response.content)
        namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

        files = []
        for content in root.findall(".//s3:Contents", namespace):
            key_elem = content.find("s3:Key", namespace)
            size_elem = content.find("s3:Size", namespace)
            modified_elem = content.find("s3:LastModified", namespace)

            if key_elem is not None and key_elem.text:
                key = key_elem.text
                if key.endswith("/"):
                    continue

                filename = key.split("/")[-1]
                if not filename:
                    continue

                files.append(
                    {
                        "path": key,
                        "filename": filename,
                        "size_bytes": int(size_elem.text)
                        if size_elem is not None
                        else 0,
                        "modified_at": modified_elem.text if modified_elem is not None else None,
                    }
                )

        return {"files": files, "total": len(files), "path": path}

    async def delete_file(self, remote_path: str, tenant_id: str) -> bool:
        """
        Delete a file from S3.

        Args:
            remote_path: Remote file path
            tenant_id: Tenant ID

        Returns:
            True if deleted, False if not found
        """
        s3_url = self._build_s3_url(tenant_id, remote_path)

        # Sign DELETE request
        headers = {}
        signed_headers = self.signer.sign_request("DELETE", s3_url, headers, b"")

        # Delete
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.delete(s3_url, headers=signed_headers)

        if response.status_code == 404:
            return False

        if response.status_code not in [200, 204]:
            raise RuntimeError(
                f"Delete failed: {response.status_code} - {response.text}"
            )

        return True

    async def get_file_info(
        self, remote_path: str, tenant_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Get file info using HEAD request.

        Args:
            remote_path: Remote file path
            tenant_id: Tenant ID

        Returns:
            File info dict or None if not found
        """
        s3_url = self._build_s3_url(tenant_id, remote_path)

        # Sign HEAD request
        headers = {}
        signed_headers = self.signer.sign_request("HEAD", s3_url, headers, b"")

        # Get info
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.head(s3_url, headers=signed_headers)

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise RuntimeError(f"HEAD failed: {response.status_code} - {response.text}")

        return {
            "path": remote_path,
            "size_bytes": int(response.headers.get("content-length", 0)),
            "content_type": response.headers.get(
                "content-type", "application/octet-stream"
            ),
            "last_modified": response.headers.get("last-modified"),
            "etag": response.headers.get("etag", "").strip('"'),
        }
