"""Unit tests for text utilities."""

import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

from p8fs_node.models.content import ContentMetadata, ContentType
from p8fs_node.utils.text import FileUtils, MetadataExtractor, TextChunker


class TestTextChunker:
    """Test TextChunker utility class."""
    
    def test_chunk_by_characters_basic(self):
        """Test basic text chunking."""
        text = "This is a test. This is another sentence. And a third one."
        chunks = TextChunker.chunk_by_characters(text, chunk_size=20, overlap=5)
        
        assert len(chunks) > 1
        assert all(len(chunk) <= 20 for chunk in chunks)
        assert chunks[0] == "This is a test."  # Breaks at sentence boundary
    
    def test_chunk_by_characters_empty(self):
        """Test chunking empty text."""
        chunks = TextChunker.chunk_by_characters("", chunk_size=100, overlap=10)
        assert chunks == []
    
    def test_chunk_by_characters_single_chunk(self):
        """Test text that fits in single chunk."""
        text = "Short text"
        chunks = TextChunker.chunk_by_characters(text, chunk_size=100, overlap=10)
        
        assert len(chunks) == 1
        assert chunks[0] == "Short text"
    
    def test_chunk_by_characters_paragraph_boundary(self):
        """Test chunking at paragraph boundaries."""
        text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph."
        chunks = TextChunker.chunk_by_characters(text, chunk_size=30, overlap=5)
        
        # Should prefer paragraph boundaries
        assert chunks[0] == "First paragraph here."
        assert chunks[1] == "Second paragraph here."
    
    def test_chunk_by_characters_sentence_boundary(self):
        """Test chunking at sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = TextChunker.chunk_by_characters(text, chunk_size=35, overlap=5)
        
        # Should break at sentence boundaries when possible
        assert ". " not in chunks[0][:-2]  # No sentence break in middle
    
    def test_chunk_by_characters_word_boundary(self):
        """Test chunking at word boundaries."""
        text = "This is a very long word: supercalifragilisticexpialidocious and more text"
        chunks = TextChunker.chunk_by_characters(text, chunk_size=30, overlap=5)
        
        # Should try to break at word boundaries
        assert chunks[0].endswith(" ") or chunks[0][-1].isalpha()
    
    def test_chunk_by_characters_overlap(self):
        """Test chunk overlap functionality."""
        text = "Sentence one. Sentence two. Sentence three. Sentence four."
        chunks = TextChunker.chunk_by_characters(text, chunk_size=25, overlap=10)
        
        # Check that chunks have overlap
        for i in range(len(chunks) - 1):
            # Next chunk should start with part of previous chunk
            assert len(chunks[i]) > 10  # Has content for overlap
    
    def test_chunk_by_characters_delimiter_priority(self):
        """Test delimiter priority in chunking."""
        text = "Para1\n\nPara2; clause1, clause2. Sentence."
        chunks = TextChunker.chunk_by_characters(text, chunk_size=15, overlap=3)
        
        # Should prefer paragraph break over other delimiters
        assert chunks[0].strip() == "Para1"
    
    def test_chunk_by_characters_no_good_break(self):
        """Test chunking when no good break point exists."""
        text = "a" * 100  # Long string without breaks
        chunks = TextChunker.chunk_by_characters(text, chunk_size=30, overlap=5)
        
        # Should still chunk even without good break points
        assert len(chunks) > 1
        assert all(len(chunk) <= 30 for chunk in chunks)
    
    def test_chunk_by_characters_strip_whitespace(self):
        """Test that chunks are stripped of whitespace."""
        text = "  Text with spaces  \n\n  More text  "
        chunks = TextChunker.chunk_by_characters(text, chunk_size=20, overlap=5)
        
        # All chunks should be stripped
        assert all(chunk == chunk.strip() for chunk in chunks)
        assert all(chunk for chunk in chunks)  # No empty chunks


class TestFileUtils:
    """Test FileUtils utility class."""
    
    def test_get_file_hash(self):
        """Test file hash calculation."""
        content = b"Test file content"
        expected_hash = hashlib.sha256(content).hexdigest()
        
        with patch('builtins.open', mock_open(read_data=content)):
            result = FileUtils.get_file_hash(Path("test.txt"))
        
        assert result == expected_hash
    
    def test_get_file_hash_large_file(self):
        """Test file hash calculation for large files."""
        # Simulate reading in chunks
        chunks = [b"chunk1", b"chunk2", b"chunk3", b""]
        mock_file = mock_open()()
        mock_file.read.side_effect = chunks
        
        with patch('builtins.open', return_value=mock_file):
            result = FileUtils.get_file_hash(Path("large.txt"))
        
        # Verify hash is calculated from all chunks
        expected_hash = hashlib.sha256(b"chunk1chunk2chunk3").hexdigest()
        assert result == expected_hash
    
    def test_get_file_stats(self):
        """Test file statistics extraction."""
        # Mock file stats
        mock_stat = MagicMock()
        mock_stat.st_size = 1024
        mock_stat.st_ctime = 1640995200.0  # 2022-01-01 00:00:00
        mock_stat.st_mtime = 1641081600.0  # 2022-01-02 00:00:00
        
        with patch('pathlib.Path.stat', return_value=mock_stat):
            with patch.object(FileUtils, 'get_file_hash', return_value="testhash"):
                stats = FileUtils.get_file_stats(Path("/path/to/test.txt"))
        
        assert stats["size"] == 1024
        assert stats["name"] == "test.txt"
        assert stats["stem"] == "test"
        assert stats["suffix"] == ".txt"
        assert stats["hash"] == "testhash"
        assert isinstance(stats["created"], datetime)
        assert isinstance(stats["modified"], datetime)
    
    @patch('p8fs_node.utils.text.chardet')
    def test_detect_encoding_with_chardet(self, mock_chardet):
        """Test encoding detection with chardet available."""
        mock_chardet.detect.return_value = {"encoding": "utf-8", "confidence": 0.99}
        
        with patch('builtins.open', mock_open(read_data=b"Test content")):
            encoding = FileUtils.detect_encoding(Path("test.txt"))
        
        assert encoding == "utf-8"
        mock_chardet.detect.assert_called_once()
    
    @patch('p8fs_node.utils.text.chardet')
    def test_detect_encoding_chardet_none(self, mock_chardet):
        """Test encoding detection when chardet returns None."""
        mock_chardet.detect.return_value = {"encoding": None}
        
        with patch('builtins.open', mock_open(read_data=b"Test content")):
            encoding = FileUtils.detect_encoding(Path("test.txt"))
        
        assert encoding == "utf-8"  # Falls back to default
    
    def test_detect_encoding_without_chardet(self):
        """Test encoding detection without chardet."""
        # Simulate chardet import error
        with patch('p8fs_node.utils.text.chardet', side_effect=ImportError):
            # Mock successful UTF-8 read
            mock_file = mock_open(read_data="Test content")
            
            with patch('builtins.open', mock_file):
                encoding = FileUtils.detect_encoding(Path("test.txt"))
            
            assert encoding == "utf-8"
    
    def test_detect_encoding_fallback_encodings(self):
        """Test encoding detection fallback through multiple encodings."""
        def mock_open_side_effect(file, encoding=None, *args, **kwargs):
            if encoding == "utf-8":
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "test error")
            elif encoding == "utf-16":
                raise UnicodeDecodeError("utf-16", b"", 0, 1, "test error")
            elif encoding == "latin-1":
                # Latin-1 succeeds
                mock_file = MagicMock()
                mock_file.read.return_value = "Test"
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=None)
                return mock_file
            
        with patch('p8fs_node.utils.text.chardet', side_effect=ImportError):
            with patch('builtins.open', side_effect=mock_open_side_effect):
                encoding = FileUtils.detect_encoding(Path("test.txt"))
        
        assert encoding == "latin-1"
    
    def test_detect_encoding_all_fail(self):
        """Test encoding detection when all encodings fail."""
        with patch('p8fs_node.utils.text.chardet', side_effect=ImportError):
            with patch('builtins.open', side_effect=UnicodeDecodeError("test", b"", 0, 1, "error")):
                encoding = FileUtils.detect_encoding(Path("test.txt"))
        
        assert encoding == "utf-8"  # Default fallback


class TestMetadataExtractor:
    """Test MetadataExtractor utility class."""
    
    def test_create_base_metadata_basic(self):
        """Test basic metadata creation."""
        # Mock file stats
        with patch.object(FileUtils, 'get_file_stats') as mock_stats:
            mock_stats.return_value = {
                "stem": "document",
                "size": 2048,
                "created": datetime(2023, 1, 1),
                "modified": datetime(2023, 1, 2),
                "hash": "filehash123",
                "name": "document.txt",
                "suffix": ".txt"
            }
            
            metadata = MetadataExtractor.create_base_metadata(
                Path("document.txt"),
                "test_provider",
                ContentType.TEXT
            )
        
        assert isinstance(metadata, ContentMetadata)
        assert metadata.title == "document"
        assert metadata.file_size == 2048
        assert metadata.created_date == datetime(2023, 1, 1)
        assert metadata.modified_date == datetime(2023, 1, 2)
        assert metadata.extraction_method == "test_provider"
        assert metadata.properties["file_hash"] == "filehash123"
        assert metadata.properties["original_filename"] == "document.txt"
        assert metadata.properties["file_extension"] == ".txt"
    
    def test_create_base_metadata_with_chunks(self):
        """Test metadata creation with chunks for word count."""
        # Mock chunks
        chunks = [
            MagicMock(content="First chunk with five words"),
            MagicMock(content="Second chunk here"),
            MagicMock(content="Third")
        ]
        
        with patch.object(FileUtils, 'get_file_stats') as mock_stats:
            mock_stats.return_value = {
                "stem": "test",
                "size": 1024,
                "created": datetime.now(),
                "modified": datetime.now(),
                "hash": "hash",
                "name": "test.txt",
                "suffix": ".txt"
            }
            
            metadata = MetadataExtractor.create_base_metadata(
                Path("test.txt"),
                "provider",
                ContentType.TEXT,
                chunks=chunks
            )
        
        assert metadata.word_count == 9  # Total words in all chunks
    
    def test_create_base_metadata_no_chunks(self):
        """Test metadata creation without chunks."""
        with patch.object(FileUtils, 'get_file_stats') as mock_stats:
            mock_stats.return_value = {
                "stem": "test",
                "size": 512,
                "created": datetime.now(),
                "modified": datetime.now(),
                "hash": "hash",
                "name": "test.txt",
                "suffix": ".txt"
            }
            
            metadata = MetadataExtractor.create_base_metadata(
                Path("test.txt"),
                "provider",
                ContentType.TEXT,
                chunks=None
            )
        
        assert metadata.word_count is None  # No word count without chunks
    
    def test_create_base_metadata_empty_chunks(self):
        """Test metadata creation with empty chunks."""
        chunks = []
        
        with patch.object(FileUtils, 'get_file_stats') as mock_stats:
            mock_stats.return_value = {
                "stem": "test",
                "size": 0,
                "created": datetime.now(),
                "modified": datetime.now(),
                "hash": "hash",
                "name": "test.txt",
                "suffix": ".txt"
            }
            
            metadata = MetadataExtractor.create_base_metadata(
                Path("test.txt"),
                "provider",
                ContentType.TEXT,
                chunks=chunks
            )
        
        assert metadata.word_count is None  # No word count for empty chunks