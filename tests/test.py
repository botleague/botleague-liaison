
# Set SHOULD_RECORD=true to record changed-files.json

import constants
from pr_processor import PrProcessorMock
from responses import ErrorResponse, StartedResponse, EvalStartedResponse

from botleague_helpers.config import activate_test_mode, blconfig

activate_test_mode()  # So don't import this module from non-test code!

# Being paranoid
assert blconfig.is_test


def test_move_plus_modify():
    pr_processor = PrProcessorMock()
    resp, status = pr_processor.process_changes()
    assert isinstance(resp, ErrorResponse)
    assert resp.msg == constants.RENAME_PROBLEM_ERROR_MSG
    # TODO: assert much more here


def test_bot_eval():
    pr_processor = PrProcessorMock()
    resp, status = pr_processor.process_changes()
    assert isinstance(resp[0], EvalStartedResponse)
    # TODO: assert much more here



def test_asdf():
    pass

