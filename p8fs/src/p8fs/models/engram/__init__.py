"""Engram models and processor for P8FS.

Engrams are now stored as Resources (see p8fs.models.p8.Resources).
Moments are stored using p8fs.models.p8.Moment.

This module provides the EngramProcessor for processing engram YAML/JSON documents,
and helper models (Person, Speaker) for moment data structures.
"""

from .models import Person, Speaker
from .processor import EngramProcessor

__all__ = [
    "Person",
    "Speaker",
    "EngramProcessor"
]
