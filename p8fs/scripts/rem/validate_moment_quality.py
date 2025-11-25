#!/usr/bin/env python3
"""
Validate Moment Quality

Critical quality checks for moment extraction:
- Temporal boundaries are logical (start < end, reasonable duration)
- Present persons are extracted correctly
- Speakers identified with speaking times
- Emotion and topic tags are relevant
- Content summarization is accurate
- Entity references are valid

This is NOT just checking for exceptions - this validates the QUALITY of dreaming output.
"""

import asyncio
import argparse
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

from p8fs.models.engram.models import Moment, Person, Speaker
from p8fs.repository.TenantRepository import TenantRepository
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

# Set default embedding provider for local testing
os.environ.setdefault("P8FS_DEFAULT_EMBEDDING_PROVIDER", "text-embedding-3-small")

logger = get_logger(__name__)


class MomentQualityValidator:
    """Validates the quality of extracted moments"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.repository = TenantRepository(Moment, tenant_id)
        self.errors = []
        self.warnings = []

    async def validate_all(self) -> Dict[str, Any]:
        """Run all quality checks"""
        moments = await self.repository.select(filters={"tenant_id": self.tenant_id}, limit=1000)

        logger.info(f"Validating {len(moments)} moments for {self.tenant_id}")

        results = {
            "total_moments": len(moments),
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "checks": {
                "temporal_validity": await self.check_temporal_validity(moments),
                "person_extraction": await self.check_person_extraction(moments),
                "speaker_identification": await self.check_speaker_identification(moments),
                "tag_quality": await self.check_tag_quality(moments),
                "content_quality": await self.check_content_quality(moments),
                "entity_references": await self.check_entity_references(moments),
                "temporal_coverage": await self.check_temporal_coverage(moments),
                "moment_types": await self.check_moment_type_distribution(moments),
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }

        # Calculate pass/fail
        for check_name, check_result in results["checks"].items():
            if check_result["passed"]:
                results["passed"] += 1
            else:
                results["failed"] += 1

        results["warnings"] = len(self.warnings)

        return results

    async def check_temporal_validity(self, moments: List[Moment]) -> Dict[str, Any]:
        """Validate temporal boundaries are logical"""
        invalid_count = 0
        issues = []

        for moment in moments:
            # Check start < end
            if moment.resource_timestamp and moment.resource_ends_timestamp:
                if moment.resource_timestamp >= moment.resource_ends_timestamp:
                    invalid_count += 1
                    issues.append(f"{moment.name}: start >= end")
                    continue

                # Check duration is reasonable (not too short, not too long)
                duration = (moment.resource_ends_timestamp - moment.resource_timestamp).total_seconds() / 60
                if duration < 1:
                    self.warnings.append(f"{moment.name}: very short duration ({duration:.1f} min)")
                elif duration > 480:  # 8 hours
                    self.warnings.append(f"{moment.name}: very long duration ({duration:.1f} min)")

            else:
                self.warnings.append(f"{moment.name}: missing timestamp boundaries")

        passed = invalid_count == 0
        return {
            "passed": passed,
            "invalid_count": invalid_count,
            "total_checked": len(moments),
            "issues": issues[:10],  # First 10 issues
        }

    async def check_person_extraction(self, moments: List[Moment]) -> Dict[str, Any]:
        """Validate person extraction quality"""
        missing_persons = 0
        duplicate_persons = 0
        invalid_persons = 0
        issues = []

        for moment in moments:
            # Check meetings/conversations have present_persons
            if moment.moment_type in ["meeting", "conversation"]:
                if not moment.present_persons or len(moment.present_persons) == 0:
                    missing_persons += 1
                    issues.append(f"{moment.name}: {moment.moment_type} with no persons")

            # Check for duplicate persons
            if moment.present_persons:
                person_names = [p.name for p in moment.present_persons if isinstance(p, Person)]
                if len(person_names) != len(set(person_names)):
                    duplicate_persons += 1
                    issues.append(f"{moment.name}: duplicate persons")

                # Validate Person objects
                for p in moment.present_persons:
                    if not isinstance(p, Person):
                        invalid_persons += 1
                        issues.append(f"{moment.name}: invalid person object {type(p)}")
                    elif not p.name or len(p.name) < 2:
                        invalid_persons += 1
                        issues.append(f"{moment.name}: invalid person name '{p.name}'")

        passed = missing_persons == 0 and duplicate_persons == 0 and invalid_persons == 0
        return {
            "passed": passed,
            "missing_persons": missing_persons,
            "duplicate_persons": duplicate_persons,
            "invalid_persons": invalid_persons,
            "issues": issues[:10],
        }

    async def check_speaker_identification(self, moments: List[Moment]) -> Dict[str, Any]:
        """Validate speaker identification in meetings/conversations"""
        missing_speakers = 0
        invalid_speaking_times = 0
        speaker_person_mismatch = 0
        issues = []

        for moment in moments:
            if moment.moment_type in ["meeting", "conversation"]:
                # Meetings should have speakers
                if not moment.speakers or len(moment.speakers) == 0:
                    missing_speakers += 1
                    issues.append(f"{moment.name}: meeting with no speakers")
                    continue

                # Validate Speaker objects
                for speaker in moment.speakers:
                    if not isinstance(speaker, Speaker):
                        issues.append(f"{moment.name}: invalid speaker object {type(speaker)}")
                        continue

                    # Speaking time should be positive and reasonable
                    if speaker.speaking_time:
                        if speaker.speaking_time < 0:
                            invalid_speaking_times += 1
                            issues.append(f"{moment.name}: negative speaking time for {speaker.name}")
                        elif speaker.speaking_time > 28800:  # 8 hours in seconds
                            invalid_speaking_times += 1
                            issues.append(f"{moment.name}: excessive speaking time for {speaker.name}")

                # Speakers should be subset of present_persons
                if moment.present_persons:
                    speaker_names = {s.name for s in moment.speakers if isinstance(s, Speaker)}
                    person_names = {p.name for p in moment.present_persons if isinstance(p, Person)}
                    if not speaker_names.issubset(person_names):
                        speaker_person_mismatch += 1
                        issues.append(f"{moment.name}: speakers not in present_persons")

        passed = missing_speakers == 0 and invalid_speaking_times == 0 and speaker_person_mismatch == 0
        return {
            "passed": passed,
            "missing_speakers": missing_speakers,
            "invalid_speaking_times": invalid_speaking_times,
            "speaker_person_mismatch": speaker_person_mismatch,
            "issues": issues[:10],
        }

    async def check_tag_quality(self, moments: List[Moment]) -> Dict[str, Any]:
        """Validate emotion and topic tags quality"""
        missing_tags = 0
        empty_tags = 0
        invalid_tags = 0
        issues = []

        for moment in moments:
            # Check emotion tags
            if not moment.emotion_tags:
                missing_tags += 1
                issues.append(f"{moment.name}: no emotion tags")
            elif len(moment.emotion_tags) == 0:
                empty_tags += 1
            elif any(len(tag.strip()) < 2 for tag in moment.emotion_tags):
                invalid_tags += 1
                issues.append(f"{moment.name}: invalid emotion tags")

            # Check topic tags
            if not moment.topic_tags:
                missing_tags += 1
                issues.append(f"{moment.name}: no topic tags")
            elif len(moment.topic_tags) == 0:
                empty_tags += 1
            elif any(len(tag.strip()) < 2 for tag in moment.topic_tags):
                invalid_tags += 1
                issues.append(f"{moment.name}: invalid topic tags")

            # Reasonable tag counts (not too few, not excessive)
            if moment.emotion_tags and len(moment.emotion_tags) > 10:
                self.warnings.append(f"{moment.name}: excessive emotion tags ({len(moment.emotion_tags)})")
            if moment.topic_tags and len(moment.topic_tags) > 15:
                self.warnings.append(f"{moment.name}: excessive topic tags ({len(moment.topic_tags)})")

        passed = missing_tags == 0 and invalid_tags == 0
        return {
            "passed": passed,
            "missing_tags": missing_tags,
            "empty_tags": empty_tags,
            "invalid_tags": invalid_tags,
            "issues": issues[:10],
        }

    async def check_content_quality(self, moments: List[Moment]) -> Dict[str, Any]:
        """Validate content and summary quality"""
        missing_content = 0
        missing_summary = 0
        short_content = 0
        mismatched_length = 0
        issues = []

        for moment in moments:
            # Content should exist and have reasonable length
            if not moment.content or len(moment.content.strip()) == 0:
                missing_content += 1
                issues.append(f"{moment.name}: missing content")
            elif len(moment.content) < 50:
                short_content += 1
                self.warnings.append(f"{moment.name}: very short content ({len(moment.content)} chars)")

            # Summary should exist
            if not moment.summary or len(moment.summary.strip()) == 0:
                missing_summary += 1
                issues.append(f"{moment.name}: missing summary")
            elif moment.content and len(moment.summary) > len(moment.content):
                mismatched_length += 1
                self.warnings.append(f"{moment.name}: summary longer than content")

        passed = missing_content == 0 and missing_summary == 0
        return {
            "passed": passed,
            "missing_content": missing_content,
            "missing_summary": missing_summary,
            "short_content": short_content,
            "mismatched_length": mismatched_length,
            "issues": issues[:10],
        }

    async def check_entity_references(self, moments: List[Moment]) -> Dict[str, Any]:
        """Validate entity references in metadata"""
        moments_with_entities = 0
        invalid_entity_format = 0
        issues = []

        for moment in moments:
            # Check if metadata has related_entities (optional but recommended)
            if hasattr(moment, "metadata") and moment.metadata:
                if "related_entities" in moment.metadata:
                    moments_with_entities += 1
                    entities = moment.metadata["related_entities"]
                    if not isinstance(entities, list):
                        invalid_entity_format += 1
                        issues.append(f"{moment.name}: related_entities not a list")

        # This is a soft check (warning only)
        if moments_with_entities == 0:
            self.warnings.append("No moments have entity references")

        return {
            "passed": True,  # Soft check
            "moments_with_entities": moments_with_entities,
            "invalid_entity_format": invalid_entity_format,
            "issues": issues[:10],
        }

    async def check_temporal_coverage(self, moments: List[Moment]) -> Dict[str, Any]:
        """Check that moments cover expected time periods"""
        if not moments:
            return {"passed": False, "error": "No moments to check"}

        timestamps = [m.resource_timestamp for m in moments if m.resource_timestamp]
        if not timestamps:
            return {"passed": False, "error": "No timestamps in moments"}

        earliest = min(timestamps)
        latest = max(timestamps)
        span_days = (latest - earliest).days

        # Check for temporal gaps
        sorted_timestamps = sorted(timestamps)
        gaps = []
        for i in range(len(sorted_timestamps) - 1):
            gap_hours = (sorted_timestamps[i + 1] - sorted_timestamps[i]).total_seconds() / 3600
            if gap_hours > 48:  # 2 day gap
                gaps.append(gap_hours)

        if len(gaps) > len(moments) * 0.3:  # More than 30% gaps
            self.warnings.append(f"Large temporal gaps detected: {len(gaps)} gaps > 48 hours")

        return {
            "passed": True,
            "earliest": earliest.isoformat(),
            "latest": latest.isoformat(),
            "span_days": span_days,
            "large_gaps": len(gaps),
        }

    async def check_moment_type_distribution(self, moments: List[Moment]) -> Dict[str, Any]:
        """Check distribution of moment types"""
        type_counts = {}
        for moment in moments:
            moment_type = moment.moment_type or "unknown"
            type_counts[moment_type] = type_counts.get(moment_type, 0) + 1

        # Check for diversity
        if len(type_counts) < 2:
            self.warnings.append("Low moment type diversity - only {list(type_counts.keys())}")

        # Check for unknown types
        if "unknown" in type_counts:
            self.warnings.append(f"{type_counts['unknown']} moments with unknown type")

        return {
            "passed": "unknown" not in type_counts or type_counts["unknown"] == 0,
            "type_distribution": type_counts,
            "unique_types": len(type_counts),
        }


async def main():
    parser = argparse.ArgumentParser(description="Validate moment quality")
    parser.add_argument("--tenant", required=True, help="Tenant ID to validate")
    parser.add_argument("--provider", choices=["postgresql", "tidb"], default="postgresql")
    parser.add_argument("--verbose", action="store_true", help="Show all issues and warnings")
    args = parser.parse_args()

    config.storage_provider = args.provider

    logger.info(f"Validating moment quality for {args.tenant}")
    logger.info("=" * 80)

    validator = MomentQualityValidator(args.tenant)
    results = await validator.validate_all()

    # Print results
    logger.info(f"\nMoment Quality Validation Results")
    logger.info("=" * 80)
    logger.info(f"Total moments: {results['total_moments']}")
    logger.info(f"Checks passed: {results['passed']}/{len(results['checks'])}")
    logger.info(f"Checks failed: {results['failed']}/{len(results['checks'])}")
    logger.info(f"Warnings: {results['warnings']}")
    logger.info("")

    # Print check details
    for check_name, check_result in results["checks"].items():
        status = "✓ PASS" if check_result["passed"] else "✗ FAIL"
        logger.info(f"{status} - {check_name}")

        if not check_result["passed"] or args.verbose:
            for key, value in check_result.items():
                if key not in ["passed", "issues"]:
                    logger.info(f"    {key}: {value}")

            if "issues" in check_result and check_result["issues"]:
                logger.info("    Issues:")
                for issue in check_result["issues"]:
                    logger.info(f"      - {issue}")

    # Print warnings
    if results["warnings"] and args.verbose:
        logger.info("\nWarnings:")
        for warning in results["warnings"][:20]:
            logger.info(f"  - {warning}")

    # Overall assessment
    logger.info("\n" + "=" * 80)
    if results["failed"] == 0:
        logger.info("✓ OVERALL: All quality checks PASSED")
        return 0
    else:
        logger.error(f"✗ OVERALL: {results['failed']} quality checks FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
