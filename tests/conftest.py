from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def claude_export() -> Path:
    return FIXTURES / "claude" / "conversations.json"
