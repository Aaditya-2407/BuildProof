from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.main import job_status


def test_lost_job_message_is_mode_neutral():
    with pytest.raises(HTTPException) as raised:
        asyncio.run(job_status("f" * 32))
    assert raised.value.status_code == 404
    assert "submit this analysis again" in raised.value.detail
