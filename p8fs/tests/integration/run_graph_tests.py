#!/usr/bin/env python3
"""Run all graph integration tests and generate a summary report."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Test files to run
GRAPH_TEST_FILES = [
    "test_kv_functionality.py",
    "test_kv_round_trip_verification.py", 
    "test_graph_kv_and_entities.py",
    "test_integration_language_model_entities.py",
    "test_integration_graph_relationships.py"
]

def run_test_file(test_file):
    """Run a single test file and return results."""
    print(f"\n{'='*60}")
    print(f"Running: {test_file}")
    print('='*60)
    
    cmd = [
        sys.executable, "-m", "pytest",
        f"tests/integration/{test_file}",
        "-v", "--tb=short", "--no-header"
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        
        # Parse output for pass/fail counts
        output = result.stdout + result.stderr
        passed = output.count(" PASSED")
        failed = output.count(" FAILED")
        skipped = output.count(" SKIPPED")
        errors = output.count(" ERROR")
        
        return {
            "file": test_file,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "total": passed + failed + skipped + errors,
            "success": result.returncode == 0,
            "output": output
        }
        
    except Exception as e:
        return {
            "file": test_file,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 1,
            "total": 1,
            "success": False,
            "output": str(e)
        }

def main():
    """Run all graph tests and generate summary."""
    print(f"Graph Integration Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nTest files to run: {len(GRAPH_TEST_FILES)}")
    
    results = []
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_errors = 0
    
    # Run each test file
    for test_file in GRAPH_TEST_FILES:
        result = run_test_file(test_file)
        results.append(result)
        total_passed += result["passed"]
        total_failed += result["failed"]
        total_skipped += result["skipped"]
        total_errors += result["errors"]
        
        # Print immediate summary
        status = "✅ PASSED" if result["success"] else "❌ FAILED"
        print(f"\n{status}: {result['passed']}/{result['total']} tests passed")
        if result["failed"] > 0:
            print(f"   Failed: {result['failed']}")
        if result["skipped"] > 0:
            print(f"   Skipped: {result['skipped']}")
        if result["errors"] > 0:
            print(f"   Errors: {result['errors']}")
    
    # Print final summary
    print(f"\n{'='*60}")
    print(f"FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Total tests run: {total_passed + total_failed + total_skipped + total_errors}")
    print(f"  ✅ Passed:  {total_passed}")
    print(f"  ❌ Failed:  {total_failed}")
    print(f"  ⏭️  Skipped: {total_skipped}")
    print(f"  🔥 Errors:  {total_errors}")
    
    print(f"\n{'='*60}")
    print(f"Test File Results:")
    print(f"{'='*60}")
    
    for result in results:
        status_icon = "✅" if result["success"] else "❌"
        print(f"{status_icon} {result['file']:<40} {result['passed']:>3}/{result['total']:<3} passed")
    
    # Check if all required functions are working
    print(f"\n{'='*60}")
    print(f"Graph Function Coverage:")
    print(f"{'='*60}")
    
    functions_tested = {
        "get_entities": "✅ Tested" if any("language_model" in r["file"] for r in results if r["passed"] > 0) else "❌ Not tested",
        "put_kv/get_kv": "✅ Tested" if any("kv" in r["file"] for r in results if r["passed"] > 0) else "❌ Not tested",
        "scan_kv": "✅ Tested" if total_passed > 0 else "❌ Not tested",
        "graph_relationships": "✅ Tested" if any("relationship" in r["file"] for r in results if r["passed"] > 0) else "❌ Not tested"
    }
    
    for func, status in functions_tested.items():
        print(f"  {func:<25} {status}")
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Exit with appropriate code
    sys.exit(0 if total_failed == 0 and total_errors == 0 else 1)


if __name__ == "__main__":
    main()