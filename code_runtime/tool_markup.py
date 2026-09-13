"""Recognize observed unquoted provider control envelopes; never parse or execute them."""
import re

OPEN = '<｜｜DSML｜｜ calls>'
CLOSE = '</｜｜DSML｜｜ calls>'


def ranges(content):
    if not isinstance(content, str):
        return []
    found, offset, skip_until, fence = [], 0, 0, None
    for line in content.splitlines(keepends=True):
        start = offset
        offset += len(line)
        if start < skip_until:
            continue
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not line[marker.end():].strip():
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]))
            continue
        leading = len(line) - len(line.lstrip(' '))
        if leading > 3 or not line[leading:].startswith(OPEN):
            continue  # quoted/indented code and inline mentions are ordinary text
        begin = start + leading
        end = content.find(CLOSE, begin + len(OPEN))
        if end < 0:
            continue
        end += len(CLOSE)
        tail_end = content.find('\n', end)
        if content[end:len(content) if tail_end < 0 else tail_end].strip():
            continue
        if '<｜｜DSML｜｜ invoke ' in content[begin:end]:
            found.append((begin, end))
            skip_until = end
    return found


def is_unexecuted(content):
    return bool(ranges(content))


def public_text(content):
    for start, end in reversed(ranges(content)):
        content = content[:start] + content[end:]
    return content.strip()
