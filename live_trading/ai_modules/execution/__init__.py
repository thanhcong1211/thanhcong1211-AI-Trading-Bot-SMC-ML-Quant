"""Execution AI Module"""
try:
    from .execution_ai import ExecutionAI
except ImportError:
    ExecutionAI = None

__all__ = ['ExecutionAI']
