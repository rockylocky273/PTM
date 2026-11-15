"""Módulo V0.1 de adquisición NASA EOSDIS, NOAA y NASA PDS."""

from .catalog import DATASETS, get_dataset

__all__ = ["DATASETS", "get_dataset"]
