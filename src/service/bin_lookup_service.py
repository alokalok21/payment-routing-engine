"""BIN lookup — thin service wrapper over the repository."""

from typing import Optional

from src.model.bin_info import BinInfo
from src.repository import bin_repository


def lookup_bin(bin_value: str) -> Optional[BinInfo]:
    return bin_repository.lookup_bin(bin_value)
