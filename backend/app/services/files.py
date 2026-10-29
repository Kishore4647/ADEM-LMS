import io
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError


def validate_upload(data: bytes, extension: str):
    """Validate private resource uploads before retaining their source file."""
    if not data:
        raise ValueError("The selected file is empty.")
    if extension in {".docx", ".xlsx"}:
        required = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
        try:
            with ZipFile(io.BytesIO(data)) as archive:
                if required not in archive.namelist():
                    raise ValueError("The Office document is missing its main content.")
                if sum(item.file_size for item in archive.infolist()) > 40_000_000:
                    raise ValueError("Expanded document exceeds 40 MB.")
                if archive.testzip() is not None:
                    raise ValueError("The Office document is corrupt.")
        except BadZipFile:
            raise ValueError("The Office document is not a valid DOCX/XLSX file.")
    if extension in {".png", ".jpg", ".jpeg"}:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 25_000_000:
                    raise ValueError("Image dimensions exceed 25 megapixels.")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValueError("The image is corrupt or unsupported.")
