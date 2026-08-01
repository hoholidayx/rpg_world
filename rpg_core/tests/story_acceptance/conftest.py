from __future__ import annotations

from copy import deepcopy

import pytest

from rpg_mcp.tests.test_runtime import _pack


@pytest.fixture
def story_pack_value() -> dict:
    return deepcopy(_pack())
