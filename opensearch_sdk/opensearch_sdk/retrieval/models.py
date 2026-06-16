"""
Rerank Models Module

Forward module: re-exports from project's lib directory to maintain backward compatibility.
All implementations now come from lib/models.py (psycopg2 package).
"""

# Import from project's lib directory using absolute import
from psycopg2.models import (
    BaseRerankModel,
    DashScopeModel,
    DummyRerankModel,
)

__all__ = [
    "BaseRerankModel",
    "DashScopeModel",
    "DummyRerankModel",
]
