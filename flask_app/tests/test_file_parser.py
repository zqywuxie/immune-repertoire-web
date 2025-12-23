"""
Tests for the FileParserService.
Requirements: 1.1, 1.2, 1.3, 11.1
"""
import gzip
import pytest
from services.file_parser import FileParserService
from exceptions import FileFormatInvalidError, FileParseError


class TestFileExtensionValidation:
    """Tests for file extension validation. Requirements: 1.1"""
    
    def test_csv_extension_valid(self):
        """Test that .csv extension is accepted."""
        assert FileParserService.validate_extension('data.csv') is True
    
    def test_xlsx_extension_valid(self):
        """Test that .xlsx extension is accepted."""
        assert FileParserService.validate_extension('data.xlsx') is True
    
    def test_csv_gz_extension_valid(self):
        """Test that .csv.gz extension is accepted."""
        assert FileParserService.validate_extension('data.csv.gz') is True
    
    def test_uppercase_extension_valid(self):
        """Test that uppercase extensions are accepted."""
        assert FileParserService.validate_extension('data.CSV') is True
        assert FileParserService.validate_extension('data.XLSX') is True
    
    def test_invalid_extension_rejected(self):
        """Test that invalid extensions are rejected."""
        assert FileParserService.validate_extension('data.txt') is False
        assert FileParserService.validate_extension('data.json') is False
        assert FileParserService.validate_extension('data.doc') is False


class TestGetExtension:
    """Tests for get_extension method."""
    
    def test_get_csv_extension(self):
        """Test getting .csv extension."""
        assert FileParserService.get_extension('data.csv') == '.csv'
    
    def test_get_xlsx_extension(self):
        """Test getting .xlsx extension."""
        assert FileParserService.get_extension('data.xlsx') == '.xlsx'
    
    def test_get_csv_gz_extension(self):
        """Test getting .csv.gz compound extension."""
        assert FileParserService.get_extension('data.csv.gz') == '.csv.gz'


class TestGetMimeType:
    """Tests for MIME type detection."""
    
    def test_csv_mime_type(self):
        """Test CSV MIME type."""
        assert FileParserService.get_mime_type('data.csv') == 'text/csv'
    
    def test_xlsx_mime_type(self):
        """Test Excel MIME type."""
        mime = FileParserService.get_mime_type('data.xlsx')
        assert 'spreadsheet' in mime
    
    def test_csv_gz_mime_type(self):
        """Test gzip MIME type."""
        assert FileParserService.get_mime_type('data.csv.gz') == 'application/gzip'


class TestParseFile:
    """Tests for file parsing. Requirements: 1.2, 11.1"""
    
    def test_parse_csv_file(self, sample_csv_content):
        """Test parsing CSV file content."""
        df, columns, row_count = FileParserService.parse_file(
            sample_csv_content, 'test.csv'
        )
        assert columns == ['sample', 'cdr3', 'reads', 'copy']
        assert row_count == 3
    
    def test_parse_invalid_extension_raises_error(self):
        """Test that invalid extension raises FileFormatInvalidError."""
        with pytest.raises(FileFormatInvalidError) as exc_info:
            FileParserService.parse_file(b"data", 'test.txt')
        assert 'FILE_FORMAT_INVALID' in str(exc_info.value.error_code)
    
    def test_parse_invalid_gzip_raises_error(self):
        """Test that invalid gzip content raises FileParseError."""
        # Content that claims to be gzip but isn't
        invalid_content = b"not a gzip file"
        with pytest.raises(FileParseError):
            FileParserService.parse_file(invalid_content, 'test.csv.gz')
    
    def test_parse_gzip_csv(self, sample_csv_content):
        """Test parsing gzip-compressed CSV."""
        compressed = gzip.compress(sample_csv_content)
        df, columns, row_count = FileParserService.parse_file(
            compressed, 'test.csv.gz'
        )
        assert columns == ['sample', 'cdr3', 'reads', 'copy']
        assert row_count == 3


class TestGetSampleData:
    """Tests for sample data extraction."""
    
    def test_get_sample_data(self, sample_csv_content):
        """Test getting sample data from DataFrame."""
        df, _, _ = FileParserService.parse_file(sample_csv_content, 'test.csv')
        sample = FileParserService.get_sample_data(df, n_rows=2)
        assert len(sample) == 2
        assert 'sample' in sample[0]
        assert 'cdr3' in sample[0]


class TestReadCsvOrGzip:
    """Tests for read_csv_or_gzip method. Requirements: 4.1, 4.2, 4.4"""
    
    def test_read_csv_file(self, sample_csv_file):
        """Test reading a CSV file from filepath."""
        df = FileParserService.read_csv_or_gzip(sample_csv_file)
        assert list(df.columns) == ['sample', 'cdr3', 'reads', 'copy']
        assert len(df) == 3
    
    def test_read_gzip_file(self, sample_csv_content, tmp_path):
        """Test reading a gzip-compressed CSV file from filepath."""
        # Create a gzip file
        gzip_path = tmp_path / "test.csv.gz"
        with gzip.open(gzip_path, 'wb') as f:
            f.write(sample_csv_content)
        
        df = FileParserService.read_csv_or_gzip(str(gzip_path))
        assert list(df.columns) == ['sample', 'cdr3', 'reads', 'copy']
        assert len(df) == 3
    
    def test_csv_and_gzip_produce_same_result(self, sample_csv_content, tmp_path):
        """Test that CSV and GZIP versions produce identical DataFrames. Requirements: 4.4"""
        # Create CSV file
        csv_path = tmp_path / "test.csv"
        csv_path.write_bytes(sample_csv_content)
        
        # Create GZIP file
        gzip_path = tmp_path / "test.csv.gz"
        with gzip.open(gzip_path, 'wb') as f:
            f.write(sample_csv_content)
        
        df_csv = FileParserService.read_csv_or_gzip(str(csv_path))
        df_gzip = FileParserService.read_csv_or_gzip(str(gzip_path))
        
        # DataFrames should be identical
        assert df_csv.equals(df_gzip)
    
    def test_read_nonexistent_file_raises_error(self):
        """Test that reading a nonexistent file raises FileParseError."""
        with pytest.raises(FileParseError) as exc_info:
            FileParserService.read_csv_or_gzip('/nonexistent/path/file.csv')
        assert 'not found' in str(exc_info.value.message).lower()
    
    def test_read_unsupported_format_raises_error(self, tmp_path):
        """Test that reading an unsupported format raises FileFormatInvalidError."""
        xlsx_path = tmp_path / "test.xlsx"
        xlsx_path.write_bytes(b"dummy content")
        
        with pytest.raises(FileFormatInvalidError):
            FileParserService.read_csv_or_gzip(str(xlsx_path))


class TestParseFilename:
    """Tests for parse_filename method. Requirements: 4.3"""
    
    def test_parse_csv_with_chain(self):
        """Test parsing CSV filename with chain name."""
        result = FileParserService.parse_filename("Sample1IGH.csv")
        assert result['sample_name'] == 'Sample1'
        assert result['chain_name'] == 'IGH'
        assert result['format'] == '.csv'
    
    def test_parse_csv_gz_with_chain(self):
        """Test parsing CSV.GZ filename with chain name."""
        result = FileParserService.parse_filename("Patient_A_IGK.csv.gz")
        assert result['sample_name'] == 'Patient_A'
        assert result['chain_name'] == 'IGK'
        assert result['format'] == '.csv.gz'
    
    def test_parse_csv_without_chain(self):
        """Test parsing CSV filename without chain name."""
        result = FileParserService.parse_filename("data_file.csv")
        assert result['sample_name'] == 'data_file'
        assert result['chain_name'] == ''
        assert result['format'] == '.csv'
    
    def test_parse_with_underscore_separator(self):
        """Test parsing filename with underscore before chain."""
        result = FileParserService.parse_filename("Sample_1_IGL.csv")
        assert result['sample_name'] == 'Sample_1'
        assert result['chain_name'] == 'IGL'
        assert result['format'] == '.csv'
    
    def test_parse_with_hyphen_separator(self):
        """Test parsing filename with hyphen before chain."""
        result = FileParserService.parse_filename("Sample-1-TRA.csv.gz")
        assert result['sample_name'] == 'Sample-1'
        assert result['chain_name'] == 'TRA'
        assert result['format'] == '.csv.gz'
    
    def test_parse_lowercase_chain(self):
        """Test that lowercase chain names are normalized to uppercase."""
        result = FileParserService.parse_filename("Sample1igh.csv")
        assert result['chain_name'] == 'IGH'
    
    def test_parse_all_known_chains(self):
        """Test parsing all known chain names."""
        chains = ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']
        for chain in chains:
            result = FileParserService.parse_filename(f"Sample_{chain}.csv")
            assert result['chain_name'] == chain
    
    def test_csv_and_gzip_same_sample_chain(self):
        """Test that CSV and GZIP versions extract same sample and chain. Requirements: 4.3"""
        csv_result = FileParserService.parse_filename("Sample1IGH.csv")
        gzip_result = FileParserService.parse_filename("Sample1IGH.csv.gz")
        
        assert csv_result['sample_name'] == gzip_result['sample_name']
        assert csv_result['chain_name'] == gzip_result['chain_name']
        assert csv_result['format'] == '.csv'
        assert gzip_result['format'] == '.csv.gz'
