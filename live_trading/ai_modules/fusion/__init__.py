"""Fusion AI Module"""
try:
    from .fusion_ai import FusionAIUpgraded
except ImportError:
    FusionAIUpgraded = None

__all__ = ['FusionAIUpgraded']
