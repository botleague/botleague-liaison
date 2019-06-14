
# Set SHOULD_RECORD=true to record changed-files.json
from os.path import join

from botleague_helpers.key_value_store import get_key_value_store

import constants
from bot_eval import get_eval_db_key
from results_view import add_eval_data_to_results, process_results
from pr_processor import PrProcessorMock
from pr_responses import ErrorPrResponse, StartedPrResponse, EvalStartedPrResponse

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
    assert isinstance(resp, ErrorPrResponse)
    assert resp.msg == constants.RENAME_PROBLEM_ERROR_MSG
    # TODO: assert much more here


def test_bot_eval():
    bot_eval_helper()


def test_bot_eval_org():
    bot_eval_helper()


def test_bot_eval_missing_source_commit():
    bot_eval_helper()


def test_results_handler():

    payload = Mockable.read_test_box('results_success.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    error, results = process_results(payload, kv)
    assert 'error' not in results
    assert 'finished' in results
    assert 'started' in results
    assert results.started < results.finished
    assert results.username == 'crizcraig'
    assert results.botname == 'forward-agent'
    assert results.problem_id == 'deepdrive/domain_randomization'


def bot_eval_helper():
    """
     Uses test method name to set data dir
    """
    pr_processor = PrProcessorMock()
    responses, status = pr_processor.process_changes()
    assert len(responses) == 1
    resp = responses[0]
    eval_data = resp.eval_data
    assert isinstance(resp, EvalStartedPrResponse)
    username = eval_data.username
    botname = eval_data.botname
    results = Mockable.read_test_box(join(constants.BOTS_DIR, username, botname,
                                          'results.json'))
    results.eval_key = eval_data.eval_key
    add_eval_data_to_results(eval_data, results)


    # TODO: assert much more here


