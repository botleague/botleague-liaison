
# Set SHOULD_RECORD=true to record changed-files.json
import math
import statistics
from os.path import join
from random import random

from botleague_helpers.db import get_db
from box import Box
from loguru import logger as log

import constants
from bot_eval import get_eval_db_key
from handlers.confirm_handler import process_confirm
from handlers.results_handler import add_eval_data_to_results, process_results, \
    score_within_confidence_interval
from handlers.pr_handler import PrProcessorMock
from models.eval_data import INVALID_DB_KEY_STATE_MESSAGE, get_eval_data
from responses.pr_responses import ErrorPrResponse, EvalStartedPrResponse

from botleague_helpers.config import activate_test_mode, blconfig

from tests.mockable import Mockable
from utils import get_liaison_db_store, dbox, generate_rand_alphanumeric

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
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    db.set(db_key, eval_data)
    try:
        error, results, eval_data, gist, _ = process_results(payload, db)
    except RuntimeError as e:
        assert INVALID_DB_KEY_STATE_MESSAGE == str(e)
    else:
        raise RuntimeError('Expected exception')


def test_results_handler():
    payload = Mockable.read_test_box('results_success.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert not error
    assert 'finished' in results
    assert 'started' in results
    assert results.started < results.finished
    assert results.username == 'crizcraig'
    assert results.botname == 'forward-agent'
    assert results.problem == 'deepdrive/domain_randomization'


def test_results_handler_server_error():
    payload = Mockable.read_test_box('results_error.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert error
    assert error.http_status_code == 500
    assert 'finished' in results
    assert 'started' in results
    assert results.started < results.finished
    assert results.username == 'crizcraig'
    assert results.botname == 'forward-agent'
    assert results.problem == 'deepdrive/domain_randomization'


def test_results_handler_not_confirmed():
    payload = Mockable.read_test_box('results_success.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert error
    assert error.http_status_code == 400
    assert 'finished' in results


def test_results_handler_already_complete():
    payload = Mockable.read_test_box('results_success.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert error
    assert error.http_status_code == 400
    assert 'finished' in results


def test_confirm_handler():
    payload = Mockable.read_test_box('request.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = Mockable.read_test_box('eval_data.json')
    db.set(db_key, eval_data)
    error, resp = process_confirm(payload, db)
    eval_data = get_eval_data(payload.eval_key, db)
    assert not error
    assert resp.confirmed
    assert eval_data.status == constants.EVAL_STATUS_CONFIRMED


def test_score_within_confidence_interval():
    bot_eval = dbox()
    bot_eval.prob_def.acceptable_score_deviation = 100

    bot_eval.results.score = 300
    past_bot_scores = get_past_bot_scores([10, 100])

    # Max score here is 270, so should fail
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)

    # Min score here is -160, so should fail
    bot_eval.results.score = -200
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)

    # Let's pass
    bot_eval.results.score = 200
    assert score_within_confidence_interval(bot_eval, past_bot_scores)
    bot_eval.results.score = -100
    assert score_within_confidence_interval(bot_eval, past_bot_scores)

    # Get more confident and fail
    past_bot_scores = get_past_bot_scores([100, 100, 100])
    bot_eval.results.score = -100
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)

    # Test first run
    past_bot_scores = get_past_bot_scores([])
    assert score_within_confidence_interval(bot_eval, past_bot_scores)

    # Don't fail if bot score is nan
    past_bot_scores = get_past_bot_scores([math.nan])
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)

    # Fail fuzz
    bot_eval.prob_def.acceptable_score_deviation = 0.4
    if fuzz_score_within_ci(bot_eval):
        raise RuntimeError(
            f'Fuzz fail failed bot_eval {bot_eval.to_json(indent=2)}')

    # Pass fuzz
    bot_eval.prob_def.acceptable_score_deviation = 0.6
    if not fuzz_score_within_ci(bot_eval):
        raise RuntimeError(
            f'Fuzz failed bot_eval {bot_eval.to_json(indent=2)}')

def fuzz_score_within_ci(bot_eval):
    for _ in range(30):
        past_bot_scores = get_past_bot_scores(
            [random() for _ in range(10 ** 3)])
        bot_eval.results.score = random()
        if not score_within_confidence_interval(bot_eval, past_bot_scores):
            return False
    else:
        return True


def get_past_bot_scores(past_scores):
    past_bot_scores = dbox()
    def get_score(s):
        return Box(score=s, eval_key=generate_rand_alphanumeric(12))
    past_bot_scores.scores = [get_score(s) for s in past_scores]
    past_bot_scores.mean = statistics.mean(past_scores) if past_scores else None
    return past_bot_scores


def bot_eval_helper():
    """
     Uses test method name for DATA directory in tests/data/<name>
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


