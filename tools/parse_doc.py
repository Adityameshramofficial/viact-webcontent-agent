"""Extract plain text from .txt, .pdf, or .docx files."""
import argparse
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")


def parse_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def parse_pdf(path: str) -> str:
    try:
        import PyPDF2
        text = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)
    except ImportError:
        raise RuntimeError("pypdf2 not installed — run: pip install pypdf2")


def parse_docx(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        raise RuntimeError("python-docx not installed — run: pip install python-docx")


def parse(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        text = parse_txt(path)
    elif ext == ".pdf":
        text = parse_pdf(path)
    elif ext == ".docx":
        text = parse_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {ext} (supported: .txt, .pdf, .docx)")

    return {"filename": os.path.basename(path), "text": text[:8000]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract text from a document")
    parser.add_argument("--file", required=True, help="Path to .txt, .pdf, or .docx file")
    args = parser.parse_args()

    try:
        data = parse(args.file)
        print(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
