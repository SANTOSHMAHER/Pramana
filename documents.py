import io
import re
import shutil
import subprocess
import tempfile
import uuid
import warnings
import zipfile
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from PIL import Image, ImageOps
from pptx import Presentation
from pypdf import PdfReader
import pytesseract
import xlrd

MAX_EXTRACTED_CHARACTERS = 1_000_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000
MAX_SPREADSHEET_CELLS = 200_000
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}


class DocumentError(ValueError):
    """Raised when an uploaded document cannot be safely extracted."""


def _normalize_text(value):
    return re.sub(r"\s+", " ", value).strip()


def _validate_archive(filename, payload):
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise DocumentError(f"'{filename}' is not a valid Office document.") from error
    uncompressed_size = sum(member.file_size for member in members)
    if (
        len(members) > MAX_ARCHIVE_MEMBERS
        or uncompressed_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES
        or any(
            member.file_size > 1024 * 1024
            and member.compress_size
            and member.file_size / member.compress_size > 200
            for member in members
        )
    ):
        raise DocumentError(
            f"'{filename}' exceeds the safe Office-document expansion limits."
        )


def _extract_legacy_ppt(payload, filename):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise DocumentError(
            "Legacy .ppt files require LibreOffice. Install it or upload .pptx instead."
        )
    with tempfile.TemporaryDirectory(prefix="pramana-ppt-") as temp_dir:
        source = Path(temp_dir) / f"{uuid.uuid4().hex}.ppt"
        source.write_bytes(payload)
        try:
            subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    temp_dir,
                    str(source),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DocumentError(
                f"Could not convert legacy presentation '{filename}': {error}"
            ) from error
        converted = source.with_suffix(".txt")
        if not converted.is_file():
            raise DocumentError(
                f"LibreOffice did not extract text from '{filename}'."
            )
        return converted.read_text(encoding="utf-8", errors="replace")


def extract_units(filename, payload):
    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentError(f"Unsupported file type: {suffix or '(no extension)'}")
    try:
        if suffix == ".pdf":
            reader = PdfReader(io.BytesIO(payload), strict=True)
            if len(reader.pages) > 1000:
                raise DocumentError(
                    f"'{filename}' exceeds the 1,000-page PDF limit."
                )
            units = [
                (f"page {number}", page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)
            ]
        elif suffix == ".docx":
            _validate_archive(filename, payload)
            document = Document(io.BytesIO(payload))
            paragraphs = [paragraph.text for paragraph in document.paragraphs]
            paragraphs.extend(
                " | ".join(cell.text for row in table.rows for cell in row.cells)
                for table in document.tables
            )
            units = [("document", "\n".join(paragraphs))]
        elif suffix in {".txt", ".md"}:
            try:
                text = payload.decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise DocumentError(
                    f"'{filename}' must be a UTF-8 encoded text file."
                ) from error
            units = [("document", text)]
        elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(payload)) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    if image.width * image.height > 40_000_000:
                        raise DocumentError(
                            f"'{filename}' exceeds the 40-megapixel image limit."
                        )
                    text = pytesseract.image_to_string(image, timeout=30)
            units = [("image OCR", text)]
        elif suffix == ".pptx":
            _validate_archive(filename, payload)
            presentation = Presentation(io.BytesIO(payload))
            if len(presentation.slides) > 1000:
                raise DocumentError(
                    f"'{filename}' exceeds the 1,000-slide presentation limit."
                )
            units = []
            for number, slide in enumerate(presentation.slides, start=1):
                shape_text = []
                for shape in slide.shapes:
                    if (
                        getattr(shape, "has_text_frame", False)
                        and shape.text.strip()
                    ):
                        shape_text.append(shape.text)
                    elif getattr(shape, "has_table", False):
                        shape_text.append(
                            "\n".join(
                                " | ".join(cell.text for cell in row.cells)
                                for row in shape.table.rows
                            )
                        )
                text = "\n".join(shape_text)
                units.append((f"slide {number}", text))
        elif suffix == ".ppt":
            units = [("presentation", _extract_legacy_ppt(payload, filename))]
        elif suffix == ".xlsx":
            _validate_archive(filename, payload)
            workbook = load_workbook(
                io.BytesIO(payload), read_only=True, data_only=True
            )
            if any(
                sheet.max_row * sheet.max_column > MAX_SPREADSHEET_CELLS
                for sheet in workbook.worksheets
            ):
                workbook.close()
                raise DocumentError(
                    f"'{filename}' exceeds the per-sheet cell limit."
                )
            units = [
                (
                    f"sheet {sheet.title}",
                    "\n".join(
                        " | ".join(
                            str(value)
                            for value in row
                            if value is not None
                        )
                        for row in sheet.iter_rows(values_only=True)
                    ),
                )
                for sheet in workbook.worksheets
            ]
            workbook.close()
        else:
            workbook = xlrd.open_workbook(file_contents=payload)
            if any(
                sheet.nrows * sheet.ncols > MAX_SPREADSHEET_CELLS
                for sheet in workbook.sheets()
            ):
                raise DocumentError(
                    f"'{filename}' exceeds the per-sheet cell limit."
                )
            units = [
                (
                    f"sheet {sheet.name}",
                    "\n".join(
                        " | ".join(
                            str(sheet.cell_value(row, col))
                            for col in range(sheet.ncols)
                            if sheet.cell_value(row, col) not in ("", None)
                        )
                        for row in range(sheet.nrows)
                    ),
                )
                for sheet in workbook.sheets()
            ]
    except DocumentError:
        raise
    except Exception as error:
        raise DocumentError(f"Could not read '{filename}': {error}") from error

    text_size = sum(len(text) for _, text in units)
    if text_size > MAX_EXTRACTED_CHARACTERS:
        raise DocumentError(
            f"Extracted text from '{filename}' exceeds the "
            f"{MAX_EXTRACTED_CHARACTERS:,}-character limit."
        )
    return [
        (location, _normalize_text(text))
        for location, text in units
        if _normalize_text(text)
    ]


def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks
