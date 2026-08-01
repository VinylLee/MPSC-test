"""MR module for MPSC"""

from .binding import BindingIssue, BindingValidationResult, validate_binding
from .distance import compute_difference_score, compute_jaccard_distance
from .model import (
    InputRelation,
    KillVector,
    MetamorphicRelation,
    MRInstance,
    MROptimizationResult,
    MRTemplate,
    MutableParameter,
    OutputRelation,
    ParameterType,
    TestCasePair,
)
from .optimizer import compute_mutation_score, optimize_mr_category, optimize_mr_set

__all__ = [
    "InputRelation",
    "KillVector",
    "MROptimizationResult",
    "MetamorphicRelation",
    "MutableParameter",
    "OutputRelation",
    "ParameterType",
    "MRInstance",
    "MRTemplate",
    "TestCasePair",
    "compute_difference_score",
    "BindingIssue",
    "BindingValidationResult",
    "validate_binding",
    "compute_jaccard_distance",
    "compute_mutation_score",
    "optimize_mr_category",
    "optimize_mr_set",
]
