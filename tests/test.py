
# Set SHOULD_RECORD=true to record changed-files.json

import constants
from pr_processor import PrProcessorMock
from responses import ErrorResponse, StartedResponse


def test_move_plus_modify():
    pr_processor = PrProcessorMock()
    resp = pr_processor.process_changes()
    assert isinstance(resp, ErrorResponse)
    assert resp.msg == constants.RENAME_PROBLEM_ERROR_MSG


def test_start_bot_eval():
    pr_processor = PrProcessorMock()
    resp = pr_processor.process_changes()
    assert isinstance(resp, StartedResponse)
    assert resp.msg == constants.RENAME_PROBLEM_ERROR_MSG


def record_pr_event():
    pass
