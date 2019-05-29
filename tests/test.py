import os
from os.path import join, basename, expanduser, exists

from tests.test_constants import DATA_DIR

os.environ['SHOULD_USE_FIRESTORE'] = 'false'
os.environ['SHOULD_MOCK_GITHUB'] = 'true'
os.environ['IS_TEST'] = 'true'

import constants as c
from pr_processor import get_pr_processor
from box import Box
from responses import ErrorResponse


def test_move_plus_modify():
    pr_processor = get_pr_processor()
    resp = pr_processor.process_changes()
    assert isinstance(resp, ErrorResponse)
    assert resp.msg == c.RENAME_PROBLEM_ERROR_MSG

