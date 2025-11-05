"""Text processing utilities."""

import hashlib
import re
from pathlib import Path
from typing import Any, List


class TextChunker:
    """Utility class for text chunking operations."""

    @staticmethod
    def chunk_by_characters(
        text: str, chunk_size: int = 2048, overlap: int = 200
    ) -> list[str]:
        """
        Chunk text using semchunk for semantic chunking.

        Args:
            text: Text to chunk
            chunk_size: Target size of each chunk (in words)
            overlap: Ignored - semchunk handles this better

        Returns:
            List of text chunks
        """
        if not text:
            return []

        from semchunk import chunk
        
        # Use word-based token counter for semantic chunks
        def word_counter(text: str) -> int:
            return len(text.split())
        
        # Use semchunk with word-based chunking
        chunks = chunk(
            text, 
            chunk_size=500,  # 500 words per chunk
            token_counter=word_counter, 
            memoize=True,
            overlap=None  # No overlap to reduce chunk count
        )
        
        return chunks

    @staticmethod
    def chunk_by_sentences(text: str, max_sentences: int = 5) -> List[str]:
        """Chunk text by sentence boundaries."""
        if not text:
            return []
        
        # Split into sentences using regex
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if not sentences:
            return []
        
        chunks = []
        current_chunk = []
        
        for sentence in sentences:
            current_chunk.append(sentence)
            if len(current_chunk) >= max_sentences:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
        
        # Add remaining sentences
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common OCR artifacts
    text = re.sub(r'[^\w\s\.\!\?\,\;\:\-\(\)\[\]\{\}\"\'\/\\]', '', text)
    
    # Normalize line breaks
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()


def extract_metadata_from_text(text: str) -> dict:
    """Extract basic metadata from text content."""
    if not text:
        return {
            "word_count": 0,
            "char_count": 0,
            "sentence_count": 0,
            "paragraph_count": 0,
        }
    
    # Word count
    words = text.split()
    word_count = len(words)
    
    # Character count
    char_count = len(text)
    
    # Sentence count (approximate)
    sentences = re.split(r'[.!?]+', text)
    sentence_count = len([s for s in sentences if s.strip()])
    
    # Paragraph count
    paragraphs = text.split('\n\n')
    paragraph_count = len([p for p in paragraphs if p.strip()])
    
    return {
        "word_count": word_count,
        "char_count": char_count,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
    }


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length while preserving word boundaries."""
    if len(text) <= max_length:
        return text
    
    if max_length <= len(suffix):
        return suffix[:max_length]
    
    # Find the last space within the limit
    truncate_at = max_length - len(suffix)
    last_space = text.rfind(' ', 0, truncate_at)
    
    if last_space == -1:
        # No space found, just cut at character limit
        return text[:truncate_at] + suffix
    else:
        return text[:last_space] + suffix


class FileUtils:
    """Utility class for file operations."""

    @staticmethod
    def get_file_hash(file_path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    @staticmethod
    def get_file_stats(file_path: Path) -> dict[str, Any]:
        """Get basic file statistics."""
        from datetime import datetime
        
        stat = file_path.stat()
        return {
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "name": file_path.name,
            "stem": file_path.stem,
            "suffix": file_path.suffix.lower(),
            "hash": FileUtils.get_file_hash(file_path),
        }

    @staticmethod
    def detect_encoding(file_path: Path) -> str:
        """Detect text file encoding."""
        try:
            import chardet

            with open(file_path, "rb") as f:
                raw_data = f.read(10000)  # Read first 10KB
                result = chardet.detect(raw_data)
                return result.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            # Fallback to common encodings
            encodings = ["utf-8", "utf-16", "latin-1", "cp1252"]
            for encoding in encodings:
                try:
                    with open(file_path, encoding=encoding) as f:
                        f.read(1000)  # Try to read some content
                    return encoding
                except UnicodeDecodeError:
                    continue
            return "utf-8"  # Default fallback


class MetadataExtractor:
    """Utility class for common metadata extraction."""

    @staticmethod
    def create_base_metadata(
        file_path: Path,
        extraction_method: str,
        content_type,  # Can be ContentType enum or string
        chunks: list = None,
    ) -> dict[str, Any]:
        """Create base metadata from file and chunks."""
        from p8fs_node.models.content import ContentMetadata
        
        stats = FileUtils.get_file_stats(file_path)

        # Calculate word count from chunks if available
        word_count = 0
        if chunks:
            for chunk in chunks:
                word_count += len(chunk.content.split())

        return ContentMetadata(
            title=stats["stem"],  # Use filename as title by default
            file_path=str(file_path),
            file_size=stats["size"],
            created_date=stats["created"],
            modified_date=stats["modified"],
            extraction_method=extraction_method,
            content_type=content_type,
            word_count=word_count if word_count > 0 else None,
            properties={
                "original_filename": stats["name"],
                "file_extension": stats["suffix"],
            },
        )