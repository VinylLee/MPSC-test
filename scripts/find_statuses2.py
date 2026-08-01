import re
from pathlib import Path

# Find all status-related constants in key files
files_to_check = [
    "code/src/mpsc/models.py",
    "code/src/mpsc/testing/oracle.py",
    "code/src/mpsc/mutation/corpus.py",
    "code/src/mpsc/results_evidence.py",
    "code/src/mpsc/doctor.py",
    "code/src/mpsc/cli.py",
]

for filepath in files_to_check:
    p = Path(filepath)
    if not p.exists():
        continue
    content = p.read_text(encoding="utf-8")

    # Find string literals that look like status values (snake_case with 2+ parts)
    matches = re.findall(r'"([a-z]+(?:_[a-z]+)+)"', content)
    unique_matches = sorted(set(matches))

    if unique_matches:
        print(f"\n{filepath}:")
        for m in unique_matches:
            print(f"  - {m}")
