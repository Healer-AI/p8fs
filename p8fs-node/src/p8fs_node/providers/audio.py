"""Audio content provider implementation."""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from p8fs_cluster.logging import get_logger
from p8fs_node.models.content import ContentChunk, ContentMetadata, ContentType
from p8fs_node.providers.base import ContentProvider
from p8fs_node.providers.mixins import BaseProviderMixin, MediaProviderMixin

logger = get_logger(__name__)

# Check for audio processing libraries availability (lazy import)
TORCH_AVAILABLE = None

def _check_torch_available():
    """Check if torch/torchaudio are available without importing."""
    try:
        import torch
        import torchaudio
        return True
    except ImportError:
        return False

try:
    from pydub import AudioSegment

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("PyDub not available - audio processing will be limited")


class AudioContentProvider(MediaProviderMixin, BaseProviderMixin, ContentProvider):
    """Content provider for audio files."""

    def __init__(self):
        super().__init__()
        # Use centralized configuration for API key
        from p8fs_cluster.config.settings import config
        self.openai_api_key = config.openai_api_key
        self.temp_files = []
    
    async def _process_whole_file(self, audio_path: Path) -> list[ContentChunk]:
        """Process the whole audio file at once for better performance."""
        import time
        start_time = time.time()
        
        try:
            # Get file duration if possible
            duration_seconds = None
            if PYDUB_AVAILABLE:
                try:
                    audio = AudioSegment.from_file(str(audio_path))
                    duration_seconds = len(audio) / 1000.0
                    logger.debug(f"Audio duration: {duration_seconds:.1f}s")
                except Exception as e:
                    logger.warning(f"Could not get audio duration: {e}")
            
            # Transcribe whole file
            logger.info("Transcribing entire audio file...")
            transcription = await self._transcribe_segment(str(audio_path))
            
            transcription_time = time.time() - start_time
            logger.info(f"✓ Transcription completed in {transcription_time:.1f}s")
            
            # Create chunks from transcription
            # Split by sentences or fixed word count
            chunks = []
            if transcription and transcription != "[Transcription requires OpenAI API key]":
                sentences = self._split_into_sentences(transcription)
                
                # Group sentences into chunks of reasonable size
                current_chunk = []
                current_word_count = 0
                target_words = 150  # Target chunk size in words
                
                for sentence in sentences:
                    sentence_words = len(sentence.split())
                    
                    if current_word_count + sentence_words > target_words and current_chunk:
                        # Create chunk
                        chunk_text = ' '.join(current_chunk)
                        chunk_id = f"audio-chunk{len(chunks) + 1}"
                        
                        chunk = ContentChunk(
                            id=chunk_id,
                            content=chunk_text,
                            chunk_type="transcription",
                            position=len(chunks),
                            metadata={
                                "word_count": current_word_count,
                                "confidence": 0.9,
                                "processing_method": "whole_file"
                            }
                        )
                        chunks.append(chunk)
                        
                        # Start new chunk
                        current_chunk = [sentence]
                        current_word_count = sentence_words
                    else:
                        current_chunk.append(sentence)
                        current_word_count += sentence_words
                
                # Add final chunk
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    chunk_id = f"audio-chunk{len(chunks) + 1}"
                    
                    chunk = ContentChunk(
                        id=chunk_id,
                        content=chunk_text,
                        chunk_type="transcription",
                        position=len(chunks),
                        metadata={
                            "word_count": current_word_count,
                            "confidence": 0.9,
                            "processing_method": "whole_file",
                            "duration": duration_seconds
                        }
                    )
                    chunks.append(chunk)
            else:
                # No transcription available
                chunks.append(ContentChunk(
                    id="audio-chunk1",
                    content=transcription or "[No transcription available]",
                    chunk_type="transcription",
                    position=0,
                    metadata={"confidence": 0.0, "error": "No API key or transcription failed"}
                ))
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error in whole file processing: {e}")
            raise
    
    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        import re
        # Simple sentence splitting - can be improved with NLTK if available
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    @property
    def supported_types(self) -> list[ContentType]:
        """Return list of supported content types."""
        return [ContentType.AUDIO]

    @property
    def provider_name(self) -> str:
        """Return the name of the provider."""
        return "audio_provider"

    async def extract_text(self, content_path: str | Path) -> str:
        """
        Extract raw text content from audio file via transcription.
        
        Args:
            content_path: Path to the audio file
            
        Returns:
            Raw text transcription of the entire audio file
        """
        try:
            chunks = await self.to_markdown_chunks(content_path)
            return "\n".join(chunk.content for chunk in chunks)
        except Exception as e:
            logger.error(f"Error extracting text from audio {content_path}: {e}")
            return f"[Audio transcription failed: {str(e)}]"

    async def to_markdown_chunks(
        self, content_path: str | Path, extended: bool = False, **options: Any
    ) -> list[ContentChunk]:
        """
        Convert audio content to markdown chunks via transcription.

        Args:
            content_path: Path to the audio file
            extended: Whether to include extended processing (speaker diarization, sentiment)
            **options: Additional processing options
                - vad_threshold: float - Voice activity detection threshold (0.0-1.0)
                - energy_threshold: float - Energy threshold for VAD in dB
                - chunk_max_duration: float - Maximum duration for a chunk in seconds
                - chunk_min_duration: float - Minimum duration for a chunk in seconds
                - merge_threshold: float - Merge segments with gaps smaller than this

        Returns:
            List of content chunks in markdown format
        """
        logger.info(f"Processing audio: {content_path} (extended={extended})")
        
        # Check if we have OpenAI API key for transcription
        if self.openai_api_key:
            logger.info("Will use OpenAI Whisper API for transcription")
        else:
            logger.warning("⚠️  No OpenAI API key found - transcription will be disabled")

        content_path = Path(content_path)
        chunks = []

        try:
            # Detect speech segments
            vad_threshold = options.get("vad_threshold", 0.5)
            energy_threshold = options.get("energy_threshold", -35)
            speech_segments = await self._detect_speech_segments(
                str(content_path), vad_threshold, energy_threshold
            )

            # Process speech segments
            max_duration = options.get("chunk_max_duration", 30.0)
            min_duration = options.get("chunk_min_duration", 0.5)
            merge_threshold = options.get("merge_threshold", 3.0)

            processed_segments = self._process_speech_segments(
                speech_segments, max_duration, min_duration, merge_threshold
            )

            # Extract and transcribe segments
            chunks = await self._process_audio_segments(
                content_path, processed_segments
            )

            logger.info(f"Extracted {len(chunks)} chunks from audio")
            
            # Log API usage info if we used OpenAI
            if self.openai_api_key and chunks:
                # Count successful transcriptions
                transcribed = sum(1 for c in chunks if c.metadata.get('confidence', 0) > 0)
                total_duration = sum(c.metadata.get('duration', 0) for c in chunks)
                # Whisper API costs $0.006 per minute
                estimated_cost = (total_duration / 60) * 0.006
                logger.info(f"OpenAI Whisper: {transcribed} segments transcribed ({total_duration:.1f}s total)")

        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            # Don't create error content chunks - let the error propagate
            # The file processor will catch this and use proper error logging
            raise e
        finally:
            self._cleanup_temp_files()

        return chunks

    async def to_metadata(
        self,
        content_path: str | Path,
        markdown_chunks: list[ContentChunk] | None = None,
    ) -> ContentMetadata:
        """
        Extract metadata from audio file.

        Args:
            content_path: Path to the audio file
            markdown_chunks: Pre-processed chunks (optional)

        Returns:
            Extracted metadata
        """
        logger.info(f"Extracting audio metadata: {content_path}")

        path = Path(content_path)
        metadata_dict = {
            "title": path.stem,
            "file_path": str(path),
            "file_size": path.stat().st_size if path.exists() else None,
            "content_type": ContentType.AUDIO,
            "extraction_method": self.provider_name,
            "confidence_score": 0.85,
            "properties": {"file_type": "audio"},
        }

        # Detect MIME type from extension
        extension = path.suffix.lower()
        mime_mapping = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".wma": "audio/x-ms-wma",
        }
        metadata_dict["mime_type"] = mime_mapping.get(extension, "audio/unknown")

        # Extract audio properties if PyDub is available
        if PYDUB_AVAILABLE:
            try:
                audio = AudioSegment.from_file(str(content_path))
                duration_seconds = len(audio) / 1000.0

                metadata_dict["properties"].update(
                    {
                        "duration": duration_seconds,
                        "sample_rate": audio.frame_rate,
                        "channels": audio.channels,
                        "frame_count": audio.frame_count(),
                    }
                )
            except Exception as e:
                logger.warning(f"Error extracting audio properties: {e}")

        # Calculate word count from transcription chunks
        if markdown_chunks:
            total_words = sum(len(chunk.content.split()) for chunk in markdown_chunks)
            metadata_dict["word_count"] = total_words

            # Extract total duration from chunk metadata
            max_end_time = 0
            for chunk in markdown_chunks:
                if chunk.metadata and "end_time" in chunk.metadata:
                    max_end_time = max(max_end_time, chunk.metadata["end_time"])

            if max_end_time > 0:
                metadata_dict["properties"]["transcribed_duration"] = max_end_time

        return ContentMetadata(**metadata_dict)

    async def to_embeddings(self, markdown_chunk: ContentChunk) -> list[float]:
        """
        Generate embeddings for a transcribed audio chunk.

        Args:
            markdown_chunk: The chunk to generate embeddings for

        Returns:
            Vector embeddings
        """
        logger.debug(f"Generating embeddings for audio chunk: {markdown_chunk.id}")

        # For now, generate mock embeddings based on content hash
        # In production, this would use a real embedding service
        content_hash = hashlib.md5(markdown_chunk.content.encode()).digest()
        # Create 384-dimensional embedding (matching all-MiniLM-L6-v2)
        embedding = list(content_hash * 24)[:384]
        # Normalize to float values
        return [float(b) / 255.0 for b in embedding]

    async def _detect_speech_segments(
        self, audio_path: str, vad_threshold: float = 0.5, energy_threshold: float = -35
    ) -> list[tuple[float, float]]:
        """Detect speech segments in the audio file."""
        global TORCH_AVAILABLE
        if TORCH_AVAILABLE is None:
            TORCH_AVAILABLE = _check_torch_available()
        
        if TORCH_AVAILABLE:
            try:
                logger.debug("Using Silero-VAD for speech detection")
                segments = await self._silero_vad(audio_path, vad_threshold)
                if segments:
                    return segments
            except Exception as e:
                logger.warning(
                    f"Silero-VAD failed: {e}, falling back to energy-based VAD"
                )

        # Fallback to energy-based VAD
        logger.debug("Using energy-based VAD for speech detection")
        return self._energy_based_vad(audio_path, energy_threshold)

    async def _silero_vad(
        self, audio_path: str, threshold: float = 0.5
    ) -> list[tuple[float, float]]:
        """Use Silero VAD for speech detection."""
        # Lazy import torch dependencies only when actually using Silero
        try:
            import torch
            import torchaudio
        except ImportError:
            raise ImportError("torch and torchaudio are required for Silero VAD")
        
        # Load audio
        waveform, sample_rate = torchaudio.load(audio_path)
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        # Load Silero VAD model
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad", force_reload=False
        )

        (get_speech_timestamps, _, _, _, _) = utils

        # Get speech timestamps
        speech_timestamps = get_speech_timestamps(
            waveform[0],
            model,
            threshold=threshold,
            sampling_rate=sample_rate,
            min_speech_duration_ms=250,
            min_silence_duration_ms=500,
        )

        # Convert to seconds
        segments = [
            (ts["start"] / sample_rate, ts["end"] / sample_rate)
            for ts in speech_timestamps
        ]

        return segments

    def _energy_based_vad(
        self, audio_path: str, threshold_db: float = -35
    ) -> list[tuple[float, float]]:
        """Simple energy-based VAD."""
        if not PYDUB_AVAILABLE:
            # Return whole file as single segment
            return [(0.0, 60.0)]  # Assume 60 second file

        audio = AudioSegment.from_file(audio_path)
        segments = []
        is_speech = False
        segment_start = 0

        # Process in 10ms windows
        window_ms = 10
        for i in range(0, len(audio), window_ms):
            segment = audio[i : i + window_ms]
            energy_db = segment.dBFS

            if energy_db > threshold_db and energy_db != float("-inf"):
                if not is_speech:
                    is_speech = True
                    segment_start = i
            else:
                if is_speech:
                    is_speech = False
                    if i - segment_start >= 250:  # Min 250ms
                        segments.append((segment_start / 1000.0, i / 1000.0))

        # Add final segment if needed
        if is_speech and len(audio) - segment_start >= 250:
            segments.append((segment_start / 1000.0, len(audio) / 1000.0))

        return segments or [(0.0, len(audio) / 1000.0)]

    def _process_speech_segments(
        self,
        segments: list[tuple[float, float]],
        max_duration: float = 30.0,
        min_duration: float = 0.5,
        merge_threshold: float = 3.0,
    ) -> list[tuple[float, float]]:
        """Process segments: merge close ones and split long ones."""
        if not segments:
            return []

        # Sort by start time
        sorted_segments = sorted(segments, key=lambda x: x[0])

        # Merge close segments
        merged = []
        current_start, current_end = sorted_segments[0]

        for start, end in sorted_segments[1:]:
            if start - current_end <= merge_threshold:
                current_end = end
            else:
                merged.append((current_start, current_end))
                current_start, current_end = start, end

        merged.append((current_start, current_end))

        # Split long segments and filter short ones
        final_segments = []
        for start, end in merged:
            duration = end - start

            if duration < min_duration:
                continue

            if duration > max_duration:
                # Split into chunks
                num_chunks = int(duration / max_duration) + 1
                chunk_duration = duration / num_chunks

                for i in range(num_chunks):
                    chunk_start = start + (i * chunk_duration)
                    chunk_end = min(start + ((i + 1) * chunk_duration), end)
                    final_segments.append((chunk_start, chunk_end))
            else:
                final_segments.append((start, end))

        return final_segments

    async def _process_audio_segments(
        self, audio_path: Path, segments: list[tuple[float, float]]
    ) -> list[ContentChunk]:
        """Extract and transcribe audio segments."""
        chunks = []
        
        logger.debug(f"Processing {len(segments)} audio segments for transcription")

        for i, (start_time, end_time) in enumerate(segments):
            chunk_id = f"audio-seg{i + 1}"

            # Extract segment
            if PYDUB_AVAILABLE:
                try:
                    audio = AudioSegment.from_file(str(audio_path))
                    segment = audio[int(start_time * 1000) : int(end_time * 1000)]

                    # Save to temp file for transcription
                    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    self.temp_files.append(temp_file.name)

                    segment.export(temp_file.name, format="wav")

                    # Transcribe
                    logger.debug(f"Transcribing segment {i+1}/{len(segments)} ({end_time - start_time:.1f}s)")
                    transcription = await self._transcribe_segment(temp_file.name)

                    chunk = ContentChunk(
                        id=chunk_id,
                        content=f"[{start_time:.1f}s - {end_time:.1f}s]: {transcription}",
                        chunk_type="transcription",
                        position=i,
                        metadata={
                            "start_time": start_time,
                            "end_time": end_time,
                            "duration": end_time - start_time,
                            "confidence": 0.9 if transcription else 0.0,
                        },
                    )
                    chunks.append(chunk)

                except Exception as e:
                    logger.error(f"Error processing segment {i + 1}: {e}")
                    # Add error chunk
                    chunk = ContentChunk(
                        id=chunk_id,
                        content=f"[{start_time:.1f}s - {end_time:.1f}s]: [Transcription failed]",
                        chunk_type="transcription",
                        position=i,
                        metadata={
                            "start_time": start_time,
                            "end_time": end_time,
                            "error": str(e),
                        },
                    )
                    chunks.append(chunk)
            else:
                # No PyDub, add placeholder
                chunk = ContentChunk(
                    id=chunk_id,
                    content=f"[{start_time:.1f}s - {end_time:.1f}s]: [Audio processing requires PyDub]",
                    chunk_type="transcription",
                    position=i,
                    metadata={"start_time": start_time, "end_time": end_time},
                )
                chunks.append(chunk)

        return chunks

    async def _transcribe_segment(self, audio_path: str) -> str:
        """Transcribe an audio segment."""
        if not self.openai_api_key:
            return "[Transcription requires OpenAI API key]"
        
        import os
        file_size = os.path.getsize(audio_path)
        logger.debug(f"Sending {file_size / 1024:.1f} KB to OpenAI Whisper API")

        try:
            import httpx

            url = "https://api.openai.com/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.openai_api_key}"}

            with open(audio_path, "rb") as audio_file:
                files = {
                    "file": (os.path.basename(audio_path), audio_file, "audio/wav")
                }
                data = {"model": "whisper-1", "response_format": "text"}

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url, headers=headers, files=files, data=data, timeout=60.0
                    )

                if response.status_code == 200:
                    transcription = response.text.strip()
                    logger.debug(f"Received transcription: {len(transcription)} chars")
                    return transcription
                else:
                    error_msg = f"OpenAI Whisper API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            raise Exception(f"Audio transcription failed: {str(e)}")

    def _cleanup_temp_files(self):
        """Clean up temporary files."""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.warning(f"Error cleaning up {file_path}: {e}")

        self.temp_files = []