
# Set SHOULD_RECORD=true to record changed-files.json
from os.path import join

import constants
from bot_eval import handle_results
from pr_processor import PrProcessorMock
from responses import ErrorResponse, StartedResponse, EvalStartedResponse

from botleague_helpers.config import activate_test_mode, blconfig, \
    get_test_name_from_callstack

from tests.mockable import Mockable
from tests.test_constants import DATA_DIR
from utils import read_json

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
    responses, status = pr_processor.process_changes()
    assert len(responses) == 1
    resp = responses[0]
    eval_data = resp.eval_data
    assert isinstance(resp, EvalStartedResponse)
    test_name = get_test_name_from_callstack()
    username = eval_data.username
    botname = eval_data.botname
    results = Mockable.read_test_box(join(constants.BOTS_DIR, username, botname,
                                          'results.json'))
    results.eval_key = eval_data.eval_key
    handle_results(eval_data, results, 'success')


    # TODO: assert much more here


