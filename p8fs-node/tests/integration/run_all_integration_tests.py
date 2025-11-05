"""Run all integration tests for p8fs-node content providers."""

import logging
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

# Import test modules
from tests.integration.providers.test_audio_integration import (
    run_tests as run_audio_tests,
)
from tests.integration.providers.test_pdf_integration import run_tests as run_pdf_tests
from tests.integration.providers.test_structured_integration import (
    run_tests as run_structured_tests,
)
from tests.integration.providers.test_text_integration import (
    run_tests as run_text_tests,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run all p8fs-node integration tests."""
    logger.info("🚀 Starting P8FS Node Integration Tests")
    logger.info("=" * 60)
    
    test_suites = [
        ("PDF Content Provider", run_pdf_tests),
        ("Audio Content Provider", run_audio_tests),
        ("Text Content Provider", run_text_tests),
        ("Structured Content Provider", run_structured_tests),
    ]
    
    results = {}
    
    for suite_name, test_runner in test_suites:
        logger.info(f"\n📋 Running {suite_name} Tests")
        logger.info("-" * 40)
        
        try:
            success = test_runner()
            results[suite_name] = success
            
            if success:
                logger.info(f"✅ {suite_name}: ALL TESTS PASSED")
            else:
                logger.info(f"❌ {suite_name}: SOME TESTS FAILED")
                
        except Exception as e:
            logger.error(f"💥 {suite_name}: FAILED TO RUN - {e}")
            results[suite_name] = False
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 INTEGRATION TEST SUMMARY")
    logger.info("=" * 60)
    
    passed_suites = sum(1 for success in results.values() if success)
    total_suites = len(results)
    
    for suite_name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{suite_name:<30} {status}")
    
    logger.info("-" * 60)
    logger.info(f"Total: {passed_suites}/{total_suites} test suites passed")
    
    if passed_suites == total_suites:
        logger.info("🎉 All integration tests completed successfully!")
        return True
    else:
        logger.info("⚠️  Some integration tests failed or were skipped")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)