"""Extended mutation operators: FVC, AVR, FSC"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MutationSite:
    line: int
    column: int
    original_text: str
    context: str
    node_type: str


class FVCGenerator:
    """FVC: Function Visibility Keyword Change

    Changes function visibility: public <-> private <-> internal <-> external
    """

    operator_id = "FVC"

    VISIBILITY_KEYWORDS = ["public", "private", "internal", "external"]

    def find_sites(self, source: str) -> list[MutationSite]:
        sites = []
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            # Match function declarations with visibility keywords
            match = re.search(
                r"\bfunction\b.*\b(public|private|internal|external)\b", line
            )
            if match:
                sites.append(
                    MutationSite(
                        line=i,
                        column=match.start(1),
                        original_text=match.group(1),
                        context=line.strip()[:80],
                        node_type="function_visibility",
                    )
                )
            # Functions without explicit visibility (implicit public in old Solidity)
            elif re.search(r"\bfunction\b", line) and not any(
                kw in line for kw in self.VISIBILITY_KEYWORDS
            ):
                sites.append(
                    MutationSite(
                        line=i,
                        column=line.find("function"),
                        original_text="(implicit public)",
                        context=line.strip()[:80],
                        node_type="function_implicit_visibility",
                    )
                )
        return sites

    def generate(self, source: str, site: MutationSite) -> list[tuple[str, str, str]]:
        """Generate mutants: (mutant_id_suffix, original, mutated)"""
        mutants = []
        lines = source.split("\n")
        line = lines[site.line - 1]

        if site.original_text == "(implicit public)":
            # Add explicit visibility
            mutated = line.replace("function", "function ", 1)
            if " " in mutated:
                mutated = mutated.replace(" ", " ", 1)
            mutants.append(("V01", line.strip(), mutated.strip()))
        else:
            # Change to other visibility keywords
            for kw in self.VISIBILITY_KEYWORDS:
                if kw != site.original_text:
                    mutated = line.replace(site.original_text, kw, 1)
                    mutants.append(
                        (
                            f"V{self.VISIBILITY_KEYWORDS.index(kw) + 1:02d}",
                            line.strip(),
                            mutated.strip(),
                        )
                    )
                    break  # Just one variant per site

        return mutants


class AVRGenerator:
    """AVR: Address Variable Replacement

    Replaces address variables: msg.sender <-> tx.origin <-> block.coinbase
    """

    operator_id = "AVR"

    ADDRESS_VARS = ["msg.sender", "tx.origin", "block.coinbase"]

    def find_sites(self, source: str) -> list[MutationSite]:
        sites = []
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            for var in self.ADDRESS_VARS:
                if var in line:
                    sites.append(
                        MutationSite(
                            line=i,
                            column=line.find(var),
                            original_text=var,
                            context=line.strip()[:80],
                            node_type="address_variable",
                        )
                    )
        return sites

    def generate(self, source: str, site: MutationSite) -> list[tuple[str, str, str]]:
        mutants = []
        lines = source.split("\n")
        line = lines[site.line - 1]

        for var in self.ADDRESS_VARS:
            if var != site.original_text:
                mutated = line.replace(site.original_text, var, 1)
                mutants.append(
                    (
                        f"V{self.ADDRESS_VARS.index(var) + 1:02d}",
                        line.strip(),
                        mutated.strip(),
                    )
                )
                break  # Just one variant per site

        return mutants


class FSCGenerator:
    """FSC: Function State Keyword Change

    Changes function state mutability: view <-> pure <-> constant
    """

    operator_id = "FSC"

    STATE_KEYWORDS = ["view", "pure", "constant"]

    def find_sites(self, source: str) -> list[MutationSite]:
        sites = []
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            for kw in self.STATE_KEYWORDS:
                if kw in line and re.search(r"\bfunction\b", line):
                    sites.append(
                        MutationSite(
                            line=i,
                            column=line.find(kw),
                            original_text=kw,
                            context=line.strip()[:80],
                            node_type="function_state",
                        )
                    )
        return sites

    def generate(self, source: str, site: MutationSite) -> list[tuple[str, str, str]]:
        mutants = []
        lines = source.split("\n")
        line = lines[site.line - 1]

        for kw in self.STATE_KEYWORDS:
            if kw != site.original_text:
                mutated = line.replace(site.original_text, kw, 1)
                mutants.append(
                    (
                        f"V{self.STATE_KEYWORDS.index(kw) + 1:02d}",
                        line.strip(),
                        mutated.strip(),
                    )
                )
                break

        return mutants


# Registry of extended generators
EXTENDED_GENERATORS = {
    "FVC": FVCGenerator(),
    "AVR": AVRGenerator(),
    "FSC": FSCGenerator(),
}
