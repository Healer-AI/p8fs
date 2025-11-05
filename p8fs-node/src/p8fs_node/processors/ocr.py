"""OCR processor for image content extraction (premium mode only)."""

import logging
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class OCRProcessor:
    """
    OCR processor for extracting text from images.
    
    Only enabled in premium mode to control costs and usage.
    """
    
    @classmethod
    def is_enabled(cls, **options: Any) -> bool:
        """Check if OCR processing is enabled."""
        from p8fs_cluster.config.settings import config
        
        # Check both option and global config
        premium_mode = options.get("premium_mode", False)
        global_premium = getattr(config, 'premium_mode_enabled', False)
        
        return premium_mode or global_premium
    
    @classmethod
    async def extract_text_from_images(
        cls,
        image_paths: List[Path],
        **options: Any
    ) -> str:
        """
        Extract text and semantic content from images using OCR or OpenAI Vision.
        
        Args:
            image_paths: List of image file paths
            **options: Processing options including premium_mode
                - premium_mode: bool - Enable premium OpenAI Vision features
                - max_images: int - Maximum images to process (default: 10)
                - min_resolution: int - Minimum resolution threshold (default: 300)
                - analysis_type: str - "text", "structured", or "semantic" (default: "text")
        
        Returns:
            Extracted text from all images combined
        """
        if not cls.is_enabled(**options):
            logger.info("OCR processing disabled - premium mode required")
            return ""
        
        if not image_paths:
            return ""
        
        # Filter images by resolution and limit count
        filtered_images = cls._filter_images_by_resolution(
            image_paths, 
            min_resolution=options.get("min_resolution", 300),
            max_count=options.get("max_images", 10)
        )
        
        if not filtered_images:
            logger.info("No images meet resolution threshold for OCR processing")
            return ""
        
        logger.info(f"OCR processing {len(filtered_images)} images (premium mode) - up to {options.get('max_images', 10)} images ≥{options.get('min_resolution', 300)}² pixels")
        
        extracted_texts = []
        
        for image_path in filtered_images:
            try:
                # Use OpenAI Vision for premium mode, fallback to traditional OCR
                if options.get("use_openai_vision", True):
                    text = await cls._extract_with_openai_vision(image_path, **options)
                else:
                    text = await cls._extract_text_from_single_image(image_path, **options)
                
                if text.strip():
                    extracted_texts.append(f"## Image: {image_path.name}\n\n{text}")
            except Exception as e:
                logger.error(f"OCR failed for {image_path}: {e}")
                extracted_texts.append(f"## Image: {image_path.name}\n\n*OCR processing failed*")
        
        return "\n\n".join(extracted_texts)
    
    @classmethod
    async def _extract_text_from_single_image(
        cls,
        image_path: Path,
        **options: Any
    ) -> str:
        """Extract text from a single image using available OCR libraries."""
        
        # Try different OCR approaches in order of preference
        ocr_methods = [
            cls._try_easyocr,
            cls._try_pytesseract, 
            cls._try_paddleocr,
        ]
        
        for method in ocr_methods:
            try:
                result = await method(image_path, **options)
                if result and result.strip():
                    logger.debug(f"OCR successful with {method.__name__} for {image_path}")
                    return result
            except Exception as e:
                logger.debug(f"OCR method {method.__name__} failed: {e}")
                continue
        
        logger.warning(f"All OCR methods failed for {image_path}")
        return ""
    
    @classmethod
    async def _try_easyocr(cls, image_path: Path, **options: Any) -> str:
        """Try EasyOCR (best for multilingual)."""
        try:
            import easyocr
            
            # Create reader with specified languages
            languages = options.get("ocr_languages", ["en"])
            reader = easyocr.Reader(languages, gpu=options.get("use_gpu", False))
            
            # Extract text
            results = reader.readtext(str(image_path))
            
            # Combine text results
            text_parts = []
            for (bbox, text, confidence) in results:
                if confidence > options.get("min_confidence", 0.5):
                    text_parts.append(text)
            
            return " ".join(text_parts)
            
        except ImportError:
            raise ImportError("EasyOCR not available")
    
    @classmethod
    async def _try_pytesseract(cls, image_path: Path, **options: Any) -> str:
        """Try Tesseract OCR (most common)."""
        try:
            import pytesseract
            from PIL import Image
            
            # Configure tesseract
            config = options.get("tesseract_config", "--oem 3 --psm 6")
            lang = options.get("tesseract_lang", "eng")
            
            # Extract text
            with Image.open(image_path) as img:
                text = pytesseract.image_to_string(img, lang=lang, config=config)
            
            return text.strip()
            
        except ImportError:
            raise ImportError("pytesseract not available")
    
    @classmethod  
    async def _try_paddleocr(cls, image_path: Path, **options: Any) -> str:
        """Try PaddleOCR (good for complex layouts)."""
        try:
            from paddleocr import PaddleOCR
            
            # Initialize OCR
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang=options.get("paddle_lang", "en"),
                use_gpu=options.get("use_gpu", False)
            )
            
            # Extract text
            results = ocr.ocr(str(image_path), cls=True)
            
            # Combine text results
            text_parts = []
            for line in results[0]:
                if line[1][1] > options.get("min_confidence", 0.5):
                    text_parts.append(line[1][0])
            
            return " ".join(text_parts)
            
        except ImportError:
            raise ImportError("PaddleOCR not available")
    
    @classmethod
    def _filter_images_by_resolution(
        cls,
        image_paths: List[Path],
        min_resolution: int = 300,
        max_count: int = 10
    ) -> List[Path]:
        """Filter images by resolution and limit count."""
        filtered = []
        
        for image_path in image_paths:
            try:
                from PIL import Image
                with Image.open(image_path) as img:
                    if img.width >= min_resolution and img.height >= min_resolution:
                        filtered.append(image_path)
                        if len(filtered) >= max_count:
                            break
            except Exception as e:
                logger.debug(f"Could not check resolution for {image_path}: {e}")
                # Include anyway if we can't check
                filtered.append(image_path)
                if len(filtered) >= max_count:
                    break
        
        return filtered
    
    @classmethod
    async def _extract_with_openai_vision(
        cls,
        image_path: Path,
        **options: Any
    ) -> str:
        """
        Extract semantic content from image using OpenAI Vision API.
        
        This uses OpenAI's GPT-4 Vision to analyze images for text, structure,
        and semantic content based on the analysis type.
        """
        import base64
        import httpx
        from p8fs_cluster.config.settings import config
        
        # Get OpenAI API key
        api_key = getattr(config, 'openai_api_key', None) or getattr(config, 'llm_api_key', None)
        if not api_key:
            raise ValueError("OpenAI API key required for vision processing")
        
        # Encode image to base64
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Determine analysis prompt based on type
        analysis_type = options.get("analysis_type", "text")
        
        if analysis_type == "structured":
            prompt = """
            Analyze this image and extract any structured content including:
            - Tables and their data
            - Forms and field values  
            - Lists and hierarchical information
            - Charts and their data points
            - Any structured text layout
            
            Format the output as clear, well-structured markdown.
            """
        elif analysis_type == "semantic":
            prompt = """
            Analyze this image and provide:
            - All visible text (OCR)
            - Description of visual elements and their purpose
            - Context and meaning of the content
            - Sentiment or tone if applicable
            - Key themes or topics
            
            Format as markdown with clear sections.
            """
        else:  # Default "text"
            prompt = """
            Extract all visible text from this image.
            Preserve the original layout and structure as much as possible.
            If there are tables, format them as markdown tables.
            If there are headers or sections, use appropriate markdown formatting.
            """
        
        # Make request to OpenAI Vision API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",  # Use GPT-4 with vision
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt.strip()},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_data}",
                                        "detail": options.get("detail_level", "high")
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": options.get("max_tokens", 1500)
                }
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI Vision API error: {response.status_code} - {response.text}")
                raise Exception(f"OpenAI Vision API failed: {response.status_code}")
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
    
    @classmethod
    def get_premium_message(cls) -> str:
        """Get message explaining OCR premium requirement."""
        return """
# OCR Processing Unavailable

OCR (Optical Character Recognition) for extracting text from images requires premium mode.

To enable OCR processing:
1. Set `premium_mode=True` in your processing options, or
2. Enable `P8FS_PREMIUM_MODE_ENABLED=true` in your environment

**Premium Features**:
- OpenAI Vision API for semantic content analysis
- Traditional OCR fallback (EasyOCR, Tesseract, PaddleOCR)
- Processes up to 10 images ≥300² pixels by default
- Supports text extraction, structured data, and sentiment analysis

**Note**: OCR processing may incur additional computational costs.
"""