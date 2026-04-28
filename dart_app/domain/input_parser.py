from __future__ import annotations

import re

def parse_input_line(line):
    line = line.strip()
    if not line:
        return None
    parts = re.split(r"\s+", line, maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0]

def is_security_code(text):
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", text.strip(), re.I))

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
