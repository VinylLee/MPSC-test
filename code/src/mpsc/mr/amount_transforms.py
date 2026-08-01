"""Amount transforms for MR6 - implements TeX-defined transformations"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

UINT256_MAX = 2**256 - 1


@dataclass
class TransformContext:
    source_amount: int
    sender_balance: int
    receiver_balance: int = 0


@dataclass
class TransformResult:
    value: int | None
    valid: bool
    reason: str | None = None
    metadata: dict[str, Any] | None = None


class AmountTransform:
    """Base class for amount transformations"""

    def apply(self, ctx: TransformContext) -> TransformResult:
        raise NotImplementedError


class SubtractFromConstant(AmountTransform):
    """x_f = constant - x_s (MR6.1, MR6.4)"""

    def __init__(self, constant: int):
        self.constant = constant

    def apply(self, ctx: TransformContext) -> TransformResult:
        x_s = ctx.source_amount
        x_f = self.constant - x_s
        if x_f < 0:
            return TransformResult(
                value=None, valid=False, reason=f"followup amount {x_f} < 0"
            )
        if x_f > UINT256_MAX:
            return TransformResult(
                value=None, valid=False, reason="followup amount > uint256 max"
            )
        return TransformResult(
            value=x_f,
            valid=True,
            metadata={
                "operation": f"{self.constant} - {x_s}",
                "constant": self.constant,
            },
        )


class AddConstant(AmountTransform):
    """x_f = x_s + constant (MR6.2, MR6.6)"""

    def __init__(self, constant: int):
        self.constant = constant

    def apply(self, ctx: TransformContext) -> TransformResult:
        x_s = ctx.source_amount
        x_f = x_s + self.constant
        if x_f > UINT256_MAX:
            return TransformResult(
                value=None, valid=False, reason="followup amount > uint256 max"
            )
        return TransformResult(
            value=x_f,
            valid=True,
            metadata={
                "operation": f"{x_s} + {self.constant}",
                "constant": self.constant,
            },
        )


class MultiplyByConstant(AmountTransform):
    """x_f = x_s * constant (MR6.3)"""

    def __init__(self, constant: int):
        self.constant = constant

    def apply(self, ctx: TransformContext) -> TransformResult:
        x_s = ctx.source_amount
        x_f = x_s * self.constant
        if x_f > UINT256_MAX:
            return TransformResult(
                value=None, valid=False, reason="followup amount > uint256 max"
            )
        return TransformResult(
            value=x_f,
            valid=True,
            metadata={
                "operation": f"{x_s} * {self.constant}",
                "constant": self.constant,
            },
        )


class PowerMinusSource(AmountTransform):
    """x_f = 2^(8n) - x_s (MR6.4, MR6.5)"""

    def __init__(self, n: int):
        self.n = n
        self.power = 2 ** (8 * n)

    def apply(self, ctx: TransformContext) -> TransformResult:
        x_s = ctx.source_amount
        x_f = self.power - x_s
        if x_f < 0:
            return TransformResult(
                value=None, valid=False, reason=f"followup amount {x_f} < 0"
            )
        if x_f > UINT256_MAX:
            return TransformResult(
                value=None, valid=False, reason="followup amount > uint256 max"
            )
        return TransformResult(
            value=x_f,
            valid=True,
            metadata={
                "operation": f"2^{8 * self.n} - {x_s}",
                "n": self.n,
                "power": self.power,
            },
        )


class PowerPlusSource(AmountTransform):
    """x_f = 2^(8n) + x_s (MR6.6, MR6.7)"""

    def __init__(self, n: int):
        self.n = n
        self.power = 2 ** (8 * n)

    def apply(self, ctx: TransformContext) -> TransformResult:
        x_s = ctx.source_amount
        x_f = self.power + x_s
        if x_f > UINT256_MAX:
            return TransformResult(
                value=None, valid=False, reason="followup amount > uint256 max"
            )
        return TransformResult(
            value=x_f,
            valid=True,
            metadata={
                "operation": f"2^{8 * self.n} + {x_s}",
                "n": self.n,
                "power": self.power,
            },
        )


# Registry of MR6 transforms
MR6_TRANSFORMS = {
    "MR6.1": SubtractFromConstant(1000),
    "MR6.2": AddConstant(1000),
    "MR6.3": MultiplyByConstant(1000),
    "MR6.4": PowerMinusSource(1),  # 2^8 - x_s
    "MR6.5": PowerMinusSource(2),  # 2^16 - x_s (n=2)
    "MR6.6": PowerPlusSource(1),  # 2^8 + x_s
    "MR6.7": PowerPlusSource(2),  # 2^16 + x_s (n=2)
}
