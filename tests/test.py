
# Set SHOULD_RECORD=true to record changed-files.json
from os.path import join

from botleague_helpers.key_value_store import get_key_value_store

import constants
from bot_eval import get_eval_db_key
from handlers.confirm_handler import process_confirm
from handlers.results_handler import add_eval_data_to_results, process_results
from handlers.pr_handler import PrProcessorMock
from models.eval_data import INVALID_DB_KEY_STATE_MESSAGE, get_eval_data
from responses.pr_responses import ErrorPrResponse, EvalStartedPrResponse

from botleague_helpers.config import activate_test_mode, blconfig

from tests.mockable import Mockable

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


def test_db_invalid_key_handler():
    payload = Mockable.read_test_box('request.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    try:
        error, results = process_results(payload, kv)
    except RuntimeError as e:
        assert INVALID_DB_KEY_STATE_MESSAGE == str(e)
    else:
        raise RuntimeError('Expected exception')


def test_results_handler():
    payload = Mockable.read_test_box('results_success.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    error, results = process_results(payload, kv)
    assert not error
    assert 'finished' in results
    assert 'started' in results
    assert results.started < results.finished
    assert results.username == 'crizcraig'
    assert results.botname == 'forward-agent'
    assert results.problem_id == 'deepdrive/domain_randomization'


def test_results_handler_server_error():
    payload = Mockable.read_test_box('results_error.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    error, results = process_results(payload, kv)
    assert error
    assert error.http_status_code == 500
    assert 'finished' in results
    assert 'started' in results
    assert results.started < results.finished
    assert results.username == 'crizcraig'
    assert results.botname == 'forward-agent'
    assert results.problem_id == 'deepdrive/domain_randomization'


def test_results_handler_not_confirmed():
    payload = Mockable.read_test_box('results_success.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    error, results = process_results(payload, kv)
    assert error
    assert error.http_status_code == 400
    assert 'finished' in results


def test_results_handler_already_complete():
    payload = Mockable.read_test_box('results_success.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    error, results = process_results(payload, kv)
    assert error
    assert error.http_status_code == 400
    assert 'finished' in results


def test_confirm_handler():
    payload = Mockable.read_test_box('request.json')
    kv = get_key_value_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    kv.set(db_key, eval_data)
    error, resp = process_confirm(payload, kv)
    eval_data = get_eval_data(payload.eval_key, kv)
    assert not error
    assert resp.confirmed
    assert eval_data.status == constants.EVAL_STATUS_CONFIRMED


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


