"""Deterministic, source-level compatibility layer for MuSC operators.

This is not the MuSC binary or an exact port. It provides one explicit
local interpretation for each listed operator so future experiments do not
depend on misleading scanner-only status flags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OPERATOR_SETS = {
    "mytoken": ("ROR", "ASR", "SDL", "VTR", "GVC", "AVR"),
    "rubixi": ("ROR", "LOR", "ASR", "SDL", "FVC", "GVC", "AVR"),
    "bectoken": (
        "ROR",
        "COR",
        "LOR",
        "ASR",
        "SDL",
        "RVR",
        "FVC",
        "GVC",
        "AVR",
        "RSD",
        "FSC",
        "VTR",
        "MFR",
    ),
    "gnosissafeproxy": (
        "ROR",
        "ASR",
        "SDL",
        "RVR",
        "FVC",
        "FSC",
        "AVR",
        "RSD",
        "PKD",
        "DLR",
    ),
    "personal_bank": (
        "ROR",
        "COR",
        "LOR",
        "ASR",
        "SDL",
        "FVC",
        "GVC",
        "AVR",
        "FSC",
        "PKD",
        "EUR",
    ),
}


@dataclass(frozen=True)
class CompatibleOperator:
    operator_id: str
    name: str
    interpretation: str


@dataclass(frozen=True)
class MutationCandidate:
    operator_id: str
    candidate_id: str
    line: int
    column: int
    original: str
    replacement: str


OPERATORS = {
    "ROR": CompatibleOperator(
        "ROR", "Relational Operator Replacement", "replace one relation token"
    ),
    "LOR": CompatibleOperator(
        "LOR",
        "Logical Operator Replacement",
        "delete one unary logical negation; distinct from COR",
    ),
    "COR": CompatibleOperator(
        "COR", "Conditional Operator Replacement", "swap && and ||"
    ),
    "ASR": CompatibleOperator(
        "ASR", "Assignment Short-cut Operator Replacement", "swap +=/-= or *=//="
    ),
    "SDL": CompatibleOperator(
        "SDL", "Statement Deletion", "comment one single-line statement"
    ),
    "RSD": CompatibleOperator(
        "RSD", "Require Statement Deletion", "comment one single-line require"
    ),
    "RVR": CompatibleOperator(
        "RVR", "Return Value Replacement", "swap boolean or zero/one return"
    ),
    "VTR": CompatibleOperator(
        "VTR", "Variable Type Keyword Replacement", "narrow or change integer type"
    ),
    "DLR": CompatibleOperator(
        "DLR", "Data Location Keyword Replacement", "cycle memory/storage/calldata"
    ),
    "EUR": CompatibleOperator(
        "EUR", "Ether Unit Replacement", "cycle wei/szabo/finney/ether"
    ),
    "FVC": CompatibleOperator(
        "FVC", "Function Visibility Keyword Change", "cycle visibility keyword"
    ),
    "AVR": CompatibleOperator(
        "AVR",
        "Address Variable Replacement",
        "cycle Solidity or inline-assembly caller identities",
    ),
    "GVC": CompatibleOperator(
        "GVC", "Global Variable Change", "cycle numeric global variables"
    ),
    "FSC": CompatibleOperator(
        "FSC", "Function State Keyword Change", "cycle view/pure/constant"
    ),
    "MFR": CompatibleOperator(
        "MFR",
        "Mathematical Functions Replacement",
        "swap addmod/mulmod or SafeMath-style mul/div calls",
    ),
    "PKD": CompatibleOperator(
        "PKD", "Payable Keyword Deletion", "delete one payable keyword"
    ),
}


REPLACEMENTS = {
    "ROR": {
        ">=": ">",
        "<=": "<",
        "==": "!=",
        "!=": "==",
        ">": ">=",
        "<": "<=",
    },
    "LOR": {"!": ""},
    "COR": {"&&": "||", "||": "&&"},
    "ASR": {"+=": "-=", "-=": "+=", "*=": "/=", "/=": "*="},
    "RVR": {"true": "false", "false": "true", "0": "1", "1": "0"},
    "VTR": {"uint256": "uint8", "uint": "int", "int256": "int8"},
    "DLR": {"memory": "storage", "storage": "memory", "calldata": "memory"},
    "EUR": {"wei": "szabo", "szabo": "finney", "finney": "ether", "ether": "wei"},
    "FVC": {
        "public": "private",
        "private": "internal",
        "internal": "public",
        "external": "public",
    },
    "AVR": {
        "msg.sender": "tx.origin",
        "tx.origin": "msg.sender",
        "block.coinbase": "msg.sender",
        "caller()": "origin()",
        "origin()": "caller()",
    },
    "GVC": {
        "block.timestamp": "block.number",
        "block.number": "msg.value",
        "msg.value": "block.timestamp",
        "now": "block.number",
    },
    "FSC": {"view": "pure", "pure": "view", "constant": "pure"},
    "MFR": {
        "addmod": "mulmod",
        "mulmod": "addmod",
        ".mul(": ".div(",
        ".div(": ".mul(",
    },
    "PKD": {"payable": ""},
}


PATTERNS = {
    "ROR": re.compile(r">=|<=|==|!=|(?<![<>=!])>(?!=)|(?<![<>=!])<(?!=)"),
    "LOR": re.compile(r"(?<![=!])!(?!=)"),
    "COR": re.compile(r"&&|\|\|"),
    "ASR": re.compile(r"\+=|-=|\*=|/="),
    "RVR": re.compile(r"(?<=\breturn\s)(?:true|false|0|1)(?=\s*;)"),
    "VTR": re.compile(r"\b(?:uint256|int256|uint)\b"),
    "DLR": re.compile(r"\b(?:memory|storage|calldata)\b"),
    "EUR": re.compile(r"\b(?:wei|szabo|finney|ether)\b"),
    "FVC": re.compile(r"\b(?:public|private|internal|external)\b"),
    "AVR": re.compile(
        r"\b(?:msg\.sender|tx\.origin|block\.coinbase)\b|"
        r"\b(?:caller|origin)\(\)"
    ),
    "GVC": re.compile(r"\b(?:block\.timestamp|block\.number|msg\.value|now)\b"),
    "FSC": re.compile(r"\b(?:view|pure|constant)\b"),
    "MFR": re.compile(r"\b(?:addmod|mulmod)\b|\.(?:mul|div)\("),
    "PKD": re.compile(r"\bpayable\b"),
}


def _code_before_comment(line: str) -> str:
    return line.split("//", 1)[0]


def _candidate(
    operator_id: str,
    index: int,
    line_number: int,
    column: int,
    original: str,
    replacement: str,
) -> MutationCandidate:
    return MutationCandidate(
        operator_id=operator_id,
        candidate_id=f"{operator_id}-S{index:04d}-V01",
        line=line_number,
        column=column,
        original=original,
        replacement=replacement,
    )


def find_candidates(source: str, operator_id: str) -> list[MutationCandidate]:
    """Find deterministic single-edit candidates for one compatibility operator."""

    if operator_id not in OPERATORS:
        raise KeyError(f"Unknown compatibility operator {operator_id!r}")
    candidates: list[MutationCandidate] = []
    for line_number, line in enumerate(source.splitlines(), 1):
        code = _code_before_comment(line)
        if operator_id in {"SDL", "RSD"}:
            stripped = code.strip()
            is_statement = (
                bool(stripped)
                and stripped.endswith(";")
                and not stripped.startswith(("pragma ", "import ", "event ", "using "))
            )
            if operator_id == "RSD":
                is_statement = is_statement and stripped.startswith("require(")
            if is_statement:
                indentation = code[: len(code) - len(code.lstrip())]
                candidates.append(
                    _candidate(
                        operator_id,
                        len(candidates) + 1,
                        line_number,
                        len(indentation),
                        code[len(indentation) :],
                        f"// MPSC-COMPAT-{operator_id} {code[len(indentation) :]}",
                    )
                )
            continue

        pattern = PATTERNS[operator_id]
        for match in pattern.finditer(code):
            original = match.group(0)
            replacement = REPLACEMENTS[operator_id][original]
            candidates.append(
                _candidate(
                    operator_id,
                    len(candidates) + 1,
                    line_number,
                    match.start(),
                    original,
                    replacement,
                )
            )
    return candidates


def apply_candidate(source: str, candidate: MutationCandidate) -> str:
    """Apply exactly one previously discovered candidate."""

    lines = source.splitlines(keepends=True)
    if not 1 <= candidate.line <= len(lines):
        raise ValueError("Candidate line is outside the source")
    line = lines[candidate.line - 1]
    start = candidate.column
    end = start + len(candidate.original)
    if line[start:end] != candidate.original:
        raise ValueError("Candidate no longer matches source")
    lines[candidate.line - 1] = line[:start] + candidate.replacement + line[end:]
    return "".join(lines)
