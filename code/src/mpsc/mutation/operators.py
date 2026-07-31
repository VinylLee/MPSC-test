"""Mutation operators for MPSC"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MutationOperator:
    """A mutation operator that can be applied to source code"""

    operator_id: str
    name: str
    description: str

    def apply(
        self, source: str, line: int, original: str, mutated: str
    ) -> tuple[str, bool]:
        """Apply mutation to source code. Returns (mutated_source, success)"""
        lines = source.split("\n")

        if line < 1 or line > len(lines):
            return source, False

        target_line = lines[line - 1]

        if original not in target_line:
            return source, False

        lines[line - 1] = target_line.replace(original, mutated, 1)
        return "\n".join(lines), True


# Standard operators matching TeX Table 3
OPERATORS = {
    "ROR": MutationOperator(
        "ROR", "Relational Operator Replacement", "Replace relational operators"
    ),
    "SDL": MutationOperator(
        "SDL", "Statement Deletion", "Delete or comment out statements"
    ),
    "RVR": MutationOperator("RVR", "Return Value Replacement", "Replace return values"),
    "ASR": MutationOperator(
        "ASR",
        "Assignment Short-cut Operator Replacement",
        "Replace assignment operators",
    ),
    "LOR": MutationOperator(
        "LOR", "Logical Operator Replacement", "Replace logical operators"
    ),
    "COR": MutationOperator(
        "COR", "Conditional Operator Replacement", "Replace conditional operators"
    ),
}
