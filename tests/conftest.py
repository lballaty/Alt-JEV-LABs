"""Shared fixtures. The v2 dataset is generated once per session into a temp directory (synthetic, seed 42)."""

import shutil
from pathlib import Path

import pytest

from data.generator_v2 import write_dataset


@pytest.fixture(scope="session")
def v2_master(tmp_path_factory) -> Path:
    """Pristine generated dataset. Tests must copy it (``v2_dir``) before touching files."""
    out = tmp_path_factory.mktemp("cohort_v2_master")
    write_dataset(out, seed=42)
    return out


@pytest.fixture
def v2_dir(v2_master: Path, tmp_path: Path) -> Path:
    """A private, mutable copy of the generated dataset."""
    dest = tmp_path / "cohort_v2"
    shutil.copytree(v2_master, dest)
    return dest
