#!/usr/bin/env python3
"""Test script to process all sample files and verify database storage."""

import pytest
pytest.skip("Utility script, not a test file", allow_module_level=True)

import os
import subprocess
import json
from pathlib import Path
from p8fs_cluster.config.settings import config
from p8fs.repository.SystemRepository import SystemRepository
from p8fs.models.p8 import Files, Resources
from sqlalchemy import select, func
from datetime import datetime
import time

class SampleFileProcessor:
    def __init__(self):
        self.sample_dir = Path(__file__).parent / "sample_data" / "content"
        self.workspace_root = Path(__file__).parent.parent.parent.parent
        self.files_repo = SystemRepository(model_class=Files)
        self.resources_repo = SystemRepository(model_class=Resources)
        self.results = []
        
    def process_file(self, file_path: Path) -> dict:
        """Process a single file using p8fs-node CLI."""
        print(f"\n{'='*60}")
        print(f"Processing: {file_path.name}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        # Run p8fs-node process command
        cmd = [
            "uv", "run", "p8fs-node", "process", str(file_path),
            "--output-format", "json",
            "--save-to-storage",
            "--generate-embeddings"
        ]
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                cwd=self.workspace_root
            )
            
            if result.returncode != 0:
                print(f"❌ Error processing {file_path.name}")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return {
                    "file": file_path.name,
                    "success": False,
                    "error": result.stderr,
                    "duration": time.time() - start_time
                }
            
            # Parse the output
            try:
                output = json.loads(result.stdout)
                print(f"✓ Successfully processed {file_path.name}")
                print(f"  - Chunks created: {len(output.get('chunks', []))}")
                print(f"  - Processing time: {time.time() - start_time:.2f}s")
                
                return {
                    "file": file_path.name,
                    "success": True,
                    "chunks": len(output.get('chunks', [])),
                    "output": output,
                    "duration": time.time() - start_time
                }
            except json.JSONDecodeError:
                print(f"⚠️  Warning: Could not parse JSON output for {file_path.name}")
                print(f"Raw output: {result.stdout}")
                return {
                    "file": file_path.name,
                    "success": True,
                    "raw_output": result.stdout,
                    "duration": time.time() - start_time
                }
                
        except Exception as e:
            print(f"❌ Exception processing {file_path.name}: {str(e)}")
            return {
                "file": file_path.name,
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time
            }
    
    def verify_database_records(self) -> dict:
        """Verify that files and resources were created in the database."""
        print(f"\n{'='*60}")
        print("Verifying Database Records")
        print(f"{'='*60}")
        
        verification = {
            "files": {},
            "resources": {},
            "summary": {}
        }
        
        # Check files table using execute method
        files_data = self.files_repo.execute("SELECT uri, file_size, mime_type, content_hash FROM files")
        
        print(f"\nFiles in database: {len(files_data)}")
        for file_row in files_data:
            uri, file_size, mime_type, content_hash = file_row
            print(f"  - URI: {uri}")
            print(f"    Size: {file_size} bytes")
            print(f"    MIME: {mime_type}")
            print(f"    Hash: {content_hash[:16] if content_hash else 'None'}...")
            
            # Count resources for this file
            resources_count_result = self.resources_repo.execute(
                "SELECT COUNT(*) FROM resources WHERE uri = %s", (uri,)
            )
            resources_count = resources_count_result[0][0] if resources_count_result else 0
            
            print(f"    Resources: {resources_count}")
            
            verification["files"][uri] = {
                "size": file_size,
                "mime_type": mime_type,
                "hash": content_hash,
                "resources_count": resources_count
            }
        
        # Check total resources
        total_resources_result = self.resources_repo.execute("SELECT COUNT(*) FROM resources")
        total_resources = total_resources_result[0][0] if total_resources_result and len(total_resources_result) > 0 else 0
        print(f"\nTotal resources in database: {total_resources}")
        
        # Get sample resources
        sample_resources_data = self.resources_repo.execute("SELECT name, uri, ordinal, content FROM resources LIMIT 5")
        
        print("\nSample resources:")
        for resource_row in sample_resources_data:
            name, uri, ordinal, content = resource_row
            content_preview = content[:100] + "..." if content and len(content) > 100 else content
            print(f"  - Name: {name}")
            print(f"    URI: {uri}")
            print(f"    Ordinal: {ordinal}")
            print(f"    Content: {content_preview}")
            print()
        
        verification["summary"] = {
            "total_files": len(files_data),
            "total_resources": total_resources,
            "files_with_resources": len([f for f in verification["files"].values() if f["resources_count"] > 0])
        }
        
        return verification
    
    def run_all_tests(self):
        """Process all sample files and verify database storage."""
        print("Starting P8FS CLI Sample File Processing Tests")
        print(f"Sample directory: {self.sample_dir}")
        print(f"Storage provider: {config.storage_provider}")
        print(f"Database: {config.pg_connection_string if config.storage_provider == 'postgresql' else config.tidb_connection_string}")
        
        # Get all sample files
        sample_files = list(self.sample_dir.glob("*"))
        print(f"\nFound {len(sample_files)} sample files to process")
        
        # Process each file
        for file_path in sample_files:
            result = self.process_file(file_path)
            self.results.append(result)
        
        # Verify database records
        verification = self.verify_database_records()
        
        # Summary
        print(f"\n{'='*60}")
        print("PROCESSING SUMMARY")
        print(f"{'='*60}")
        
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]
        
        print(f"\nProcessed: {len(self.results)} files")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        
        if failed:
            print("\nFailed files:")
            for f in failed:
                print(f"  - {f['file']}: {f.get('error', 'Unknown error')}")
        
        print(f"\nDatabase Summary:")
        print(f"  - Total files in DB: {verification['summary']['total_files']}")
        print(f"  - Total resources in DB: {verification['summary']['total_resources']}")
        print(f"  - Files with resources: {verification['summary']['files_with_resources']}")
        
        total_time = sum(r["duration"] for r in self.results)
        print(f"\nTotal processing time: {total_time:.2f}s")
        
        # Return success status
        return len(failed) == 0 and verification['summary']['total_files'] > 0


def main():
    processor = SampleFileProcessor()
    success = processor.run_all_tests()
    
    if success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    exit(main())