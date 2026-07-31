import re
from pathlib import Path

# Search for status enum values and constants
source_files = list(Path("code/src").rglob("*.py"))

# Find status-like patterns
status_patterns = {}

for f in source_files:
    try:
        content = f.read_text(encoding="utf-8")
    except Exception:
        continue

    # Find patterns like: status = 'value' or 'status': 'value' or == 'value'
    matches = re.findall(
        r'(?:status|state|class|type)\s*[=:]\s*["\']([a-z_]+)["\']', content
    )
    for m in matches:
        if m not in status_patterns:
            status_patterns[m] = set()
        status_patterns[m].add(f.name)

    # Find enum-like assignments
    matches2 = re.findall(
        r'^\s+[A-Z_]+\s*=\s*["\']([a-z_]+)["\']', content, re.MULTILINE
    )
    for m in matches2:
        if m not in status_patterns:
            status_patterns[m] = set()
        status_patterns[m].add(f.name)

# Print sorted
for sv in sorted(status_patterns.keys()):
    files = sorted(status_patterns[sv])
    print(f"{sv}: {', '.join(files)}")
