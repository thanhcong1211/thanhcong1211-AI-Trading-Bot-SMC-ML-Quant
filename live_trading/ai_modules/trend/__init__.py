"""Trend AI Module"""
try:
    from .trend_matrix_ai import TrendMatrixAI
except ImportError:
    TrendMatrixAI = None

__all__ = ['TrendMatrixAI']
