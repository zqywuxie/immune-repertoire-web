"""
PDF Extractor Service for the Immune Repertoire Analysis Web Application.
Handles extraction of images from PDF files and organization by sample.
Requirements: 8.6, 8.7, 8.8, 8.9, 8.10, 8.11
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from PIL import Image
import io

from exceptions import FileParseError


@dataclass
class ExtractionResult:
    """Result of PDF image extraction."""
    success: bool
    samples: Dict[str, int]  # sample_name -> image_count
    total_images: int
    output_path: str
    errors: List[str]


class PDFExtractorService:
    """
    Service for extracting images from PDF files.
    Supports automatic sample detection and organization.
    Requirements: 8.6, 8.7, 8.8, 8.9
    """
    
    # Common sample name patterns in PDFs
    SAMPLE_PATTERNS = [
        r'Sample[_\s-]*(\w+)',
        r'样本[_\s-]*(\w+)',
        r'Patient[_\s-]*(\w+)',
        r'Subject[_\s-]*(\w+)',
        r'ID[_\s-]*(\w+)',
    ]
    
    @classmethod
    def extract_images(
        cls,
        pdf_path: str,
        output_path: str,
        sample_mapping: Optional[Dict[int, str]] = None
    ) -> ExtractionResult:
        """
        Extract images from PDF and save to output path organized by sample.
        
        Requirements: 8.6, 8.7, 8.8, 8.9
        
        Args:
            pdf_path: Path to the PDF file
            output_path: Directory where images will be saved
            sample_mapping: Optional mapping of page numbers to sample names
                          If None, will attempt to auto-detect samples
            
        Returns:
            ExtractionResult with extraction details
            
        Raises:
            FileParseError: If PDF cannot be read or processed
        """
        if not PYMUPDF_AVAILABLE and not PDFPLUMBER_AVAILABLE:
            raise FileParseError(
                message="PDF processing libraries not available. Install PyMuPDF or pdfplumber.",
                details={'required_packages': ['PyMuPDF', 'pdfplumber']}
            )
        
        # Validate PDF file exists
        if not os.path.exists(pdf_path):
            raise FileParseError(
                message=f"PDF file not found: {pdf_path}",
                details={'pdf_path': pdf_path}
            )
        
        # Create output directory
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        errors = []
        samples = {}
        total_images = 0
        
        try:
            # Use PyMuPDF if available (faster and more reliable)
            if PYMUPDF_AVAILABLE:
                result = cls._extract_with_pymupdf(
                    pdf_path, output_dir, sample_mapping
                )
            else:
                result = cls._extract_with_pdfplumber(
                    pdf_path, output_dir, sample_mapping
                )
            
            return result
            
        except Exception as e:
            raise FileParseError(
                message=f"Failed to extract images from PDF: {str(e)}",
                details={
                    'pdf_path': pdf_path,
                    'error_type': type(e).__name__
                }
            )
    
    @classmethod
    def _extract_with_pymupdf(
        cls,
        pdf_path: str,
        output_dir: Path,
        sample_mapping: Optional[Dict[int, str]]
    ) -> ExtractionResult:
        """Extract images using PyMuPDF."""
        doc = fitz.open(pdf_path)
        samples = {}
        total_images = 0
        errors = []
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Determine sample name for this page
                if sample_mapping and page_num in sample_mapping:
                    sample_name = sample_mapping[page_num]
                else:
                    # Try to detect sample name from page text
                    sample_name = cls._detect_sample_from_text(page.get_text())
                    if not sample_name:
                        sample_name = f"Page_{page_num + 1}"
                
                # Create sample directory
                sample_dir = output_dir / sample_name
                sample_dir.mkdir(parents=True, exist_ok=True)
                
                # Extract images from page
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Save image
                        image_filename = f"{sample_name}_page{page_num + 1}_img{img_index + 1}.{image_ext}"
                        image_path = sample_dir / image_filename
                        
                        with open(image_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        
                        # Update counters
                        samples[sample_name] = samples.get(sample_name, 0) + 1
                        total_images += 1
                        
                    except Exception as e:
                        errors.append(f"Failed to extract image {img_index} from page {page_num + 1}: {str(e)}")
            
            return ExtractionResult(
                success=len(errors) == 0 or total_images > 0,
                samples=samples,
                total_images=total_images,
                output_path=str(output_dir),
                errors=errors
            )
            
        finally:
            doc.close()
    
    @classmethod
    def _extract_with_pdfplumber(
        cls,
        pdf_path: str,
        output_dir: Path,
        sample_mapping: Optional[Dict[int, str]]
    ) -> ExtractionResult:
        """Extract images using pdfplumber (fallback method)."""
        samples = {}
        total_images = 0
        errors = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Determine sample name
                if sample_mapping and page_num in sample_mapping:
                    sample_name = sample_mapping[page_num]
                else:
                    sample_name = cls._detect_sample_from_text(page.extract_text() or "")
                    if not sample_name:
                        sample_name = f"Page_{page_num + 1}"
                
                # Create sample directory
                sample_dir = output_dir / sample_name
                sample_dir.mkdir(parents=True, exist_ok=True)
                
                # Extract images
                images = page.images
                
                for img_index, img in enumerate(images):
                    try:
                        # pdfplumber doesn't directly extract image bytes
                        # This is a simplified version - may need enhancement
                        image_filename = f"{sample_name}_page{page_num + 1}_img{img_index + 1}.png"
                        image_path = sample_dir / image_filename
                        
                        # Note: pdfplumber image extraction is limited
                        # This is a placeholder - actual implementation may vary
                        errors.append(f"pdfplumber has limited image extraction support for page {page_num + 1}")
                        
                    except Exception as e:
                        errors.append(f"Failed to extract image {img_index} from page {page_num + 1}: {str(e)}")
        
        return ExtractionResult(
            success=len(errors) == 0 or total_images > 0,
            samples=samples,
            total_images=total_images,
            output_path=str(output_dir),
            errors=errors
        )
    
    @classmethod
    def detect_samples(cls, pdf_path: str) -> List[str]:
        """
        Automatically detect sample identifiers from PDF.
        
        Requirements: 8.8
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of detected sample names
            
        Raises:
            FileParseError: If PDF cannot be read
        """
        if not PYMUPDF_AVAILABLE and not PDFPLUMBER_AVAILABLE:
            raise FileParseError(
                message="PDF processing libraries not available",
                details={'required_packages': ['PyMuPDF', 'pdfplumber']}
            )
        
        if not os.path.exists(pdf_path):
            raise FileParseError(
                message=f"PDF file not found: {pdf_path}",
                details={'pdf_path': pdf_path}
            )
        
        samples = set()
        
        try:
            if PYMUPDF_AVAILABLE:
                doc = fitz.open(pdf_path)
                try:
                    for page in doc:
                        text = page.get_text()
                        sample_name = cls._detect_sample_from_text(text)
                        if sample_name:
                            samples.add(sample_name)
                finally:
                    doc.close()
            else:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text() or ""
                        sample_name = cls._detect_sample_from_text(text)
                        if sample_name:
                            samples.add(sample_name)
            
            return sorted(list(samples))
            
        except Exception as e:
            raise FileParseError(
                message=f"Failed to detect samples from PDF: {str(e)}",
                details={
                    'pdf_path': pdf_path,
                    'error_type': type(e).__name__
                }
            )
    
    @classmethod
    def _detect_sample_from_text(cls, text: str) -> Optional[str]:
        """
        Detect sample name from text using pattern matching.
        
        Args:
            text: Text to search for sample names
            
        Returns:
            Detected sample name or None
        """
        if not text:
            return None
        
        # Try each pattern
        for pattern in cls.SAMPLE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    @classmethod
    def get_pdf_info(cls, pdf_path: str) -> Dict:
        """
        Get basic information about a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with PDF information
        """
        if not PYMUPDF_AVAILABLE and not PDFPLUMBER_AVAILABLE:
            raise FileParseError(
                message="PDF processing libraries not available",
                details={'required_packages': ['PyMuPDF', 'pdfplumber']}
            )
        
        if not os.path.exists(pdf_path):
            raise FileParseError(
                message=f"PDF file not found: {pdf_path}",
                details={'pdf_path': pdf_path}
            )
        
        try:
            if PYMUPDF_AVAILABLE:
                doc = fitz.open(pdf_path)
                try:
                    info = {
                        'page_count': len(doc),
                        'metadata': doc.metadata,
                        'file_size': os.path.getsize(pdf_path)
                    }
                    return info
                finally:
                    doc.close()
            else:
                with pdfplumber.open(pdf_path) as pdf:
                    return {
                        'page_count': len(pdf.pages),
                        'metadata': pdf.metadata,
                        'file_size': os.path.getsize(pdf_path)
                    }
                    
        except Exception as e:
            raise FileParseError(
                message=f"Failed to get PDF info: {str(e)}",
                details={
                    'pdf_path': pdf_path,
                    'error_type': type(e).__name__
                }
            )
