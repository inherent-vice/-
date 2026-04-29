from __future__ import annotations

import csv
import re

def parse_input_line(line):
    line = line.strip().lstrip("\ufeff")
    if not line:
        return None
    delimited = _parse_delimited_input_line(line)
    if delimited:
        return delimited
    if _is_header_line(line):
        return None
    parts = re.split(r"\s+", line, maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0]

def is_security_code(text):
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", text.strip(), re.I))

def _is_header_line(line):
    compact = re.sub(r"\s+", "", line)
    return "종목코드" in compact and "종목명" in compact

def _parse_delimited_input_line(line):
    if "\t" in line:
        fields = next(csv.reader([line], delimiter="\t"))
    elif "," in line:
        fields = next(csv.reader([line]))
    else:
        return None
    fields = [field.strip().lstrip("\ufeff") for field in fields]
    if len(fields) < 2:
        return None
    if _is_header_line(" ".join(fields[:2])):
        return None
    if is_security_code(fields[0]) and fields[1]:
        return fields[0], fields[1]
    return None

def parse_input_lines(lines):
    """
    Accept both supported input layouts:
    - one line: KR6HN0008746  하나증권(DLB)2681
    - two lines: KR6HN0008746\n하나증권(DLB)2681
    """
    cleaned = [line.strip() for line in lines if line.strip()]
    out = []
    i = 0
    while i < len(cleaned):
        line = cleaned[i]
        if is_security_code(line) and i + 1 < len(cleaned) and not is_security_code(cleaned[i + 1]):
            out.append((line, cleaned[i + 1]))
            i += 2
            continue
        parsed = parse_input_line(line)
        if parsed:
            out.append(parsed)
        i += 1
    return out
