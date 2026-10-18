"""Pull readable text out of call-document uploads."""

import io
import re
import zipfile
from xml.etree import ElementTree

_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT_EXTENSIONS = {"txt", "md", "csv", "text", "json"}


def extract_document_text(filename, payload):
    name = str(filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
    title = name.rsplit(".", 1)[0][:160] or "Untitled document"
    data = payload or b""
    if extension in _TEXT_EXTENSIONS:
        text = data.decode("utf-8", errors="replace")
    elif extension == "docx":
        text = _docx_text(data)
    elif extension == "doc":
        text = _legacy_doc_text(data)
    elif extension == "pdf":
        text = _pdf_text(data)
    else:
        raise ValueError("Upload a PDF, Word document, or text file.")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("No readable text was found in that file.")
    return text, title


def _docx_text(data):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        document = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ValueError("That Word document could not be read.") from exc
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("That Word document could not be read.") from exc
    paragraphs = []
    for paragraph in root.iter(f"{_WORD}p"):
        line = "".join(node.text or "" for node in paragraph.iter(f"{_WORD}t")).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _legacy_doc_text(data):
    chunks = []
    index = 0
    size = len(data)
    while index < size - 1:
        if data[index + 1] == 0 and 32 <= data[index] < 127:
            start = index
            characters = []
            while index < size - 1 and data[index + 1] == 0 and 32 <= data[index] < 127:
                characters.append(chr(data[index]))
                index += 2
            if len(characters) >= 8:
                chunks.append("".join(characters))
            elif index == start:
                index += 1
        else:
            index += 1
    return "\n".join(chunks)


def _pdf_text(data):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("PDF upload is not available on this server.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("That PDF could not be read.") from exc
    pages = []
    for page in reader.pages[:40]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages)
