"""Pull the text out of a ReportLab PDF with the standard library only.

CI installs only requirements.txt (no pdfplumber), so PDF render tests use
this instead of skipping. It inflates each content stream and joins the
string operands of the text-showing operators, which is enough to assert
which labels and amounts a ReportLab document prints, and in what order.
"""
import base64
import re
import zlib

_STREAM = re.compile(rb"/Filter\s*(\[[^\]]*\]|/\w+)[^>]*>>\s*stream\r?\n(.*?)endstream", re.S)
_TEXT = re.compile(rb"\((?:[^()\\]|\\.)*\)\s*Tj|\[(?:[^\]\\]|\\.)*\]\s*TJ")
_STRING = re.compile(rb"\(((?:[^()\\]|\\.)*)\)")
_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _unescape(raw: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt in _ESCAPES:
                out += _ESCAPES[nxt]
                i += 2
                continue
            octal = re.match(rb"[0-7]{1,3}", raw[i + 1:i + 4])
            if octal:
                out.append(int(octal.group(0), 8) & 0xFF)
                i += 1 + len(octal.group(0))
                continue
            out += nxt
            i += 2
            continue
        out += ch
        i += 1
    return bytes(out)


def _streams(pdf_bytes: bytes):
    for match in _STREAM.finditer(pdf_bytes):
        filters, data = match.group(1), match.group(2).strip()
        try:
            if b"ASCII85Decode" in filters:
                data = base64.a85decode(data.removesuffix(b"~>"), adobe=False)
            if b"FlateDecode" in filters:
                data = zlib.decompress(data)
        except (ValueError, zlib.error):
            continue
        yield data


def pdf_text(pdf_bytes: bytes) -> str:
    """Every shown string, one per line, in drawing order."""
    pieces = []
    for stream in _streams(pdf_bytes):
        for op in _TEXT.finditer(stream):
            chunk = b"".join(_unescape(s) for s in _STRING.findall(op.group(0)))
            # ReportLab draws the minus sign (U+2212) in the Symbol font,
            # where it is byte 0x2D; WinAnsi text decodes as cp1252.
            pieces.append(chunk.decode("cp1252", errors="replace"))
    return "\n".join(pieces)
