import os
import sys

import pytest
from fastapi import HTTPException


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from learner_context import DEFAULT_USER_ID, require_user_id, resolve_user_id


def test_read_compatibility_identity_does_not_create_a_real_learner():
    assert resolve_user_id(None) == DEFAULT_USER_ID
    assert resolve_user_id("u1") == "u1"


@pytest.mark.parametrize("value", [None, "", "  ", DEFAULT_USER_ID])
def test_formal_learner_identity_rejects_missing_or_shared_values(value):
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(value)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "learner_identity_required"


def test_formal_learner_identity_accepts_stable_value():
    assert require_user_id(" learner-u1 ") == "learner-u1"
