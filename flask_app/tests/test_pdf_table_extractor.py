"""
Tests for PDF Table Extractor Service
"""
import pytest
import os
from services.pdf_table_extractor import PDFTableExtractor


class TestPDFTableExtractor:
    """Test PDF table extraction functionality"""
    
    def test_initialization(self):
        """Test that PDFTableExtractor initializes correctly"""
        extractor = PDFTableExtractor()
        assert extractor is not None
        assert 'pdfplumber' in extractor.supported_methods
        assert 'tabula' in extractor.supported_methods
    
    def test_detect_tables_invalid_file(self):
        """Test detection with non-existent file"""
        extractor = PDFTableExtractor()
        result = extractor.detect_tables('nonexistent.pdf')
        
        assert result['success'] is False
        assert 'error' in result
        assert 'PDF文件不存在' in result['error']
    
    def test_detect_tables_invalid_method(self):
        """Test detection with invalid method"""
        extractor = PDFTableExtractor()
        result = extractor.detect_tables('test.pdf', method='invalid_method')
        
        assert result['success'] is False
        assert 'error' in result
        assert '不支持的提取方法' in result['error']
    
    def test_extract_tables_invalid_file(self):
        """Test extraction with non-existent file"""
        extractor = PDFTableExtractor()
        result = extractor.extract_tables('nonexistent.pdf')
        
        assert result['success'] is False
        assert 'error' in result
        assert 'PDF文件不存在' in result['error']
    
    def test_preview_table_invalid_file(self):
        """Test preview with non-existent file"""
        extractor = PDFTableExtractor()
        result = extractor.preview_table('nonexistent.pdf', page=1)
        
        assert result['success'] is False
        assert 'error' in result
        assert 'PDF文件不存在' in result['error']
    
    def test_extract_table_to_csv_invalid_file(self):
        """Test CSV export with non-existent file"""
        extractor = PDFTableExtractor()
        result = extractor.extract_table_to_csv(
            'nonexistent.pdf',
            'output.csv',
            page=1
        )
        
        assert result['success'] is False
        assert 'error' in result
        assert 'PDF文件不存在' in result['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
