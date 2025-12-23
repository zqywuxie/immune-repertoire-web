"""
PDF Data and Image Extractor Module
从PDF报告中提取表格数据和图片

Requirements: 9.1-9.6, 12.1-12.6
"""

import re
import io
import base64
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import PDF libraries
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed. PDF table extraction will not be available.")

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    logger.warning("PyMuPDF not installed. PDF image extraction will not be available.")


class PDFExtractorError(Exception):
    """PDF提取错误基类"""
    pass


class PDFFileNotFoundError(PDFExtractorError):
    """PDF文件未找到"""
    pass


class PDFParseError(PDFExtractorError):
    """PDF解析错误"""
    pass


class PDFImageExtractionError(PDFExtractorError):
    """PDF图片提取错误"""
    pass


class PDFExtractor:
    """
    PDF数据和图片提取器
    
    功能:
    - 从PDF中提取B细胞同型分布表格数据
    - 批量提取多个PDF的表格数据
    - 列出PDF中所有图片及其索引
    - 按索引提取图片
    - 批量从多个PDF提取图片
    
    Requirements: 9.1-9.6, 12.1-12.6
    """
    
    # 默认提取的图片索引（第16张和最后一张）
    DEFAULT_IMAGE_INDICES = [16, -1]
    
    # B细胞同型列表
    ISOTYPES = ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"]
    
    def __init__(self, pdf_path: Optional[str] = None):
        """
        初始化PDF提取器
        
        Args:
            pdf_path: PDF文件路径（可选，也可以在方法调用时指定）
        """
        self.pdf_path = pdf_path
        self._validate_dependencies()
    
    def _validate_dependencies(self):
        """验证依赖库是否可用"""
        if not HAS_PDFPLUMBER and not HAS_PYMUPDF:
            logger.warning(
                "Neither pdfplumber nor PyMuPDF is installed. "
                "PDF extraction functionality will be limited."
            )
    
    @staticmethod
    def is_pdf_file(filepath: str) -> bool:
        """
        检查文件是否为PDF格式
        
        Requirements: 9.1
        
        Args:
            filepath: 文件路径
            
        Returns:
            是否为PDF文件
        """
        if not filepath:
            return False
        return filepath.lower().endswith('.pdf')
    
    def _get_pdf_path(self, pdf_path: Optional[str] = None) -> str:
        """获取PDF路径，优先使用参数，否则使用实例属性"""
        path = pdf_path or self.pdf_path
        if not path:
            raise PDFExtractorError("No PDF path specified")
        return path
    
    def _validate_pdf_exists(self, pdf_path: str) -> None:
        """验证PDF文件是否存在"""
        if not Path(pdf_path).exists():
            raise PDFFileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # =========================================================================
    # 表格数据提取 - Requirements: 9.1-9.6
    # =========================================================================
    
    def extract_isotype_table(
        self,
        pdf_path: Optional[str] = None
    ) -> Optional[Dict[str, List[float]]]:
        """
        从PDF中提取B细胞同型分布表格
        
        Requirements: 9.2, 9.3
        
        Args:
            pdf_path: PDF文件路径（可选）
            
        Returns:
            字典格式: {expression: [values], unique_cdr3: [values]}
            如果提取失败返回None
        """
        if not HAS_PDFPLUMBER:
            raise PDFExtractorError(
                "pdfplumber is not installed. "
                "Install it with: pip install pdfplumber"
            )
        
        path = self._get_pdf_path(pdf_path)
        self._validate_pdf_exists(path)
        
        try:
            with pdfplumber.open(path) as pdf:
                # 方法1: 精确匹配
                result = self._extract_isotype_exact_match(pdf)
                if result:
                    return result
                
                # 方法2: 模糊匹配
                result = self._extract_isotype_fuzzy_match(pdf)
                if result:
                    return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting isotype table from {path}: {e}")
            raise PDFParseError(f"Failed to extract isotype table: {str(e)}")
    
    def _extract_isotype_exact_match(self, pdf) -> Optional[Dict[str, List[float]]]:
        """精确匹配方式提取同型数据"""
        for page in pdf.pages:
            text = page.extract_text() or ""
            
            # 查找包含B细胞同型分布的部分
            if "B cell Isotype Distribution" in text or "Isotype Distribution" in text:
                tables = page.extract_tables()
                
                for table in tables:
                    if not table or len(table) == 0:
                        continue
                    
                    header_row = table[0]
                    
                    # 查找同型列
                    isotype_cols = []
                    for col in header_row:
                        if col and any(
                            iso in str(col) 
                            for iso in ["IgM", "IgD", "IgA", "IgG", "IgE"]
                        ):
                            isotype_cols.append(col)
                    
                    if len(isotype_cols) >= 5:
                        # 查找Expression %和Unique CDR3 %行
                        expression_row = None
                        cdr3_row = None
                        
                        for row in table[1:]:
                            if row and len(row) > 0:
                                row_text = " ".join([str(cell) for cell in row if cell])
                                if "Expression" in row_text and "%" in row_text:
                                    expression_row = row
                                elif "Unique" in row_text and "CDR3" in row_text:
                                    cdr3_row = row
                        
                        if expression_row and cdr3_row:
                            expression_values = self._extract_percentages(expression_row)
                            cdr3_values = self._extract_percentages(cdr3_row)
                            
                            if len(expression_values) >= 5 and len(cdr3_values) >= 5:
                                return {
                                    "expression": expression_values[:6],
                                    "unique_cdr3": cdr3_values[:6]
                                }
        
        return None
    
    def _extract_isotype_fuzzy_match(self, pdf) -> Optional[Dict[str, List[float]]]:
        """模糊匹配方式提取同型数据"""
        for page in pdf.pages:
            tables = page.extract_tables()
            
            for table in tables:
                if not table or len(table) <= 2:
                    continue
                
                # 将表格转换为文本进行分析
                table_text = []
                for row in table:
                    table_text.append(
                        " ".join([str(cell) for cell in row if cell])
                    )
                
                full_text = " ".join(table_text).lower()
                
                # 检查是否可能是同型表格
                if any(iso.lower() in full_text for iso in ["igm", "igd", "iga", "igg"]) \
                   and "%" in full_text:
                    
                    expression_values = []
                    cdr3_values = []
                    
                    for row_text in table_text:
                        if "expression" in row_text.lower():
                            percentages = re.findall(r"(\d+\.?\d*)%", row_text)
                            expression_values = [float(p) for p in percentages]
                        elif "unique" in row_text.lower() and "cdr3" in row_text.lower():
                            percentages = re.findall(r"(\d+\.?\d*)%", row_text)
                            cdr3_values = [float(p) for p in percentages]
                    
                    if len(expression_values) >= 5 and len(cdr3_values) >= 5:
                        return {
                            "expression": expression_values[:6],
                            "unique_cdr3": cdr3_values[:6]
                        }
        
        return None
    
    def _extract_percentages(self, row: List) -> List[float]:
        """从行数据中提取百分比值"""
        values = []
        for cell in row:
            if cell and "%" in str(cell):
                match = re.search(r"(\d+\.?\d*)", str(cell))
                if match:
                    values.append(float(match.group(1)))
        return values

    
    def batch_extract_tables(
        self,
        pdf_paths: List[str]
    ) -> Dict[str, Any]:
        """
        批量提取多个PDF的表格数据
        
        Requirements: 9.6
        
        Args:
            pdf_paths: PDF文件路径列表
            
        Returns:
            字典格式: {
                extracted_data: {filename: {expression, unique_cdr3}},
                failed_files: [filenames],
                error_messages: {filename: error_message}
            }
        """
        extracted_data = {}
        failed_files = []
        error_messages = {}
        
        for pdf_path in pdf_paths:
            filename = Path(pdf_path).name
            
            try:
                data = self.extract_isotype_table(pdf_path)
                if data:
                    extracted_data[filename] = data
                    logger.info(f"Successfully extracted data from {filename}")
                else:
                    failed_files.append(filename)
                    error_messages[filename] = "No isotype table found in PDF"
                    logger.warning(f"No data extracted from {filename}")
                    
            except PDFFileNotFoundError as e:
                failed_files.append(filename)
                error_messages[filename] = str(e)
                logger.error(f"File not found: {filename}")
                
            except PDFParseError as e:
                failed_files.append(filename)
                error_messages[filename] = str(e)
                logger.error(f"Parse error for {filename}: {e}")
                
            except Exception as e:
                failed_files.append(filename)
                error_messages[filename] = f"Unexpected error: {str(e)}"
                logger.error(f"Unexpected error processing {filename}: {e}")
        
        return {
            "extracted_data": extracted_data,
            "failed_files": failed_files,
            "error_messages": error_messages
        }
    
    # =========================================================================
    # 图片提取 - Requirements: 12.1-12.6
    # =========================================================================
    
    def list_images(
        self,
        pdf_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        列出PDF中所有图片及其索引
        
        Requirements: 12.1
        
        Args:
            pdf_path: PDF文件路径（可选）
            
        Returns:
            列表格式: [{index, width, height, page_number, thumbnail}]
        """
        if not HAS_PYMUPDF:
            raise PDFExtractorError(
                "PyMuPDF is not installed. "
                "Install it with: pip install PyMuPDF"
            )
        
        path = self._get_pdf_path(pdf_path)
        self._validate_pdf_exists(path)
        
        images = []
        
        try:
            doc = fitz.open(path)
            image_index = 0
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                
                for img_info in image_list:
                    xref = img_info[0]
                    
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        
                        # 生成缩略图
                        thumbnail = self._create_thumbnail(image_bytes, max_size=100)
                        
                        images.append({
                            "index": image_index,
                            "width": width,
                            "height": height,
                            "page_number": page_num + 1,
                            "thumbnail": thumbnail,
                            "xref": xref
                        })
                        
                        image_index += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to process image at index {image_index}: {e}")
                        image_index += 1
            
            doc.close()
            return images
            
        except Exception as e:
            logger.error(f"Error listing images from {path}: {e}")
            raise PDFImageExtractionError(f"Failed to list images: {str(e)}")
    
    def _create_thumbnail(
        self,
        image_bytes: bytes,
        max_size: int = 100
    ) -> str:
        """创建图片缩略图并返回base64编码"""
        try:
            from PIL import Image
            
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((max_size, max_size))
            
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            logger.warning(f"Failed to create thumbnail: {e}")
            return ""
    
    def extract_images_by_index(
        self,
        indices: List[int],
        pdf_path: Optional[str] = None
    ) -> List[Tuple[int, bytes]]:
        """
        按索引提取图片
        
        Requirements: 12.4
        
        Args:
            indices: 要提取的图片索引列表（支持负索引，-1表示最后一张）
            pdf_path: PDF文件路径（可选）
            
        Returns:
            列表格式: [(index, image_bytes)]
        """
        if not HAS_PYMUPDF:
            raise PDFExtractorError(
                "PyMuPDF is not installed. "
                "Install it with: pip install PyMuPDF"
            )
        
        path = self._get_pdf_path(pdf_path)
        self._validate_pdf_exists(path)
        
        # 先获取所有图片信息
        all_images = self._get_all_image_xrefs(path)
        total_images = len(all_images)
        
        if total_images == 0:
            return []
        
        # 处理负索引
        resolved_indices = []
        for idx in indices:
            if idx < 0:
                resolved_idx = total_images + idx
            else:
                resolved_idx = idx
            
            if 0 <= resolved_idx < total_images:
                resolved_indices.append((idx, resolved_idx))
        
        # 提取图片
        extracted = []
        
        try:
            doc = fitz.open(path)
            
            for original_idx, resolved_idx in resolved_indices:
                try:
                    xref = all_images[resolved_idx]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    extracted.append((original_idx, image_bytes))
                    
                except Exception as e:
                    logger.warning(f"Failed to extract image at index {original_idx}: {e}")
            
            doc.close()
            return extracted
            
        except Exception as e:
            logger.error(f"Error extracting images from {path}: {e}")
            raise PDFImageExtractionError(f"Failed to extract images: {str(e)}")
    
    def _get_all_image_xrefs(self, pdf_path: str) -> List[int]:
        """获取PDF中所有图片的xref列表"""
        xrefs = []
        
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            for img_info in image_list:
                xrefs.append(img_info[0])
        doc.close()
        
        return xrefs
    
    def extract_images_with_default_indices(
        self,
        pdf_path: Optional[str] = None
    ) -> List[Tuple[int, bytes]]:
        """
        使用默认索引提取图片
        
        Requirements: 12.3
        
        默认提取第16张和最后一张图片
        
        Args:
            pdf_path: PDF文件路径（可选）
            
        Returns:
            列表格式: [(index, image_bytes)]
        """
        return self.extract_images_by_index(
            self.DEFAULT_IMAGE_INDICES,
            pdf_path
        )
    
    def batch_extract_images(
        self,
        pdf_paths: List[str],
        indices: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        批量从多个PDF提取图片
        
        Requirements: 12.6
        
        Args:
            pdf_paths: PDF文件路径列表
            indices: 要提取的图片索引列表（可选，默认使用DEFAULT_IMAGE_INDICES）
            
        Returns:
            字典格式: {
                extracted_images: {filename: [(index, image_base64)]},
                failed_files: [filenames],
                error_messages: {filename: error_message}
            }
        """
        if indices is None:
            indices = self.DEFAULT_IMAGE_INDICES
        
        extracted_images = {}
        failed_files = []
        error_messages = {}
        
        for pdf_path in pdf_paths:
            filename = Path(pdf_path).name
            
            try:
                images = self.extract_images_by_index(indices, pdf_path)
                
                # 将图片转换为base64
                images_base64 = []
                for idx, img_bytes in images:
                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    images_base64.append((idx, img_base64))
                
                extracted_images[filename] = images_base64
                logger.info(f"Successfully extracted {len(images)} images from {filename}")
                
            except PDFFileNotFoundError as e:
                failed_files.append(filename)
                error_messages[filename] = str(e)
                logger.error(f"File not found: {filename}")
                
            except PDFImageExtractionError as e:
                failed_files.append(filename)
                error_messages[filename] = str(e)
                logger.error(f"Image extraction error for {filename}: {e}")
                
            except Exception as e:
                failed_files.append(filename)
                error_messages[filename] = f"Unexpected error: {str(e)}"
                logger.error(f"Unexpected error processing {filename}: {e}")
        
        return {
            "extracted_images": extracted_images,
            "failed_files": failed_files,
            "error_messages": error_messages
        }
    
    # =========================================================================
    # 数据表格生成
    # =========================================================================
    
    def get_data_table(
        self,
        extracted_data: Dict[str, Dict[str, List[float]]]
    ) -> Dict[str, Any]:
        """
        将提取的数据转换为可复制的表格格式
        
        Args:
            extracted_data: 提取的数据 {filename: {expression, unique_cdr3}}
            
        Returns:
            包含headers, rows, tab_separated的字典
        """
        # 构建表头
        headers = ["Sample"]
        for isotype in self.ISOTYPES:
            headers.append(f"{isotype}_Expression")
            headers.append(f"{isotype}_Unique_CDR3")
        
        # 构建数据行
        rows = []
        for filename, data in extracted_data.items():
            # 从文件名提取样本名（去掉.pdf后缀）
            sample_name = Path(filename).stem
            row = [sample_name]
            
            expression = data.get("expression", [])
            unique_cdr3 = data.get("unique_cdr3", [])
            
            for i in range(len(self.ISOTYPES)):
                expr_val = expression[i] if i < len(expression) else None
                cdr3_val = unique_cdr3[i] if i < len(unique_cdr3) else None
                
                row.append(f"{expr_val:.2f}%" if expr_val is not None else "")
                row.append(f"{cdr3_val:.2f}%" if cdr3_val is not None else "")
            
            rows.append(row)
        
        # 生成制表符分隔格式
        tab_separated = self._to_tab_separated(headers, rows)
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": tab_separated
        }
    
    def _to_tab_separated(
        self,
        headers: List[str],
        rows: List[List[Any]]
    ) -> str:
        """将表格数据转换为制表符分隔格式"""
        lines = ["\t".join(str(h) for h in headers)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
