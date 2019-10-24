
# Set SHOULD_RECORD=true to record changed-files.json
import statistics

import math
from os.path import join
from random import random

from box import Box

import constants
from bot_eval import get_eval_db_key
from handlers.confirm_handler import process_confirm
from handlers.results_handler import add_eval_data_to_results, process_results, \
    score_within_confidence_interval, get_past_bot_scores, get_scores_db, \
    get_scores_id
from handlers.pr_handler import PrProcessorMock, handle_pr_request
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
    eval_data = get_test_eval_data()
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
    eval_data = get_test_eval_data()
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert not error
    assert 'finished' in results
    assert 'started' in results
    assert results.started < results.finished
    assert results.username == 'crizcraig'
    assert results.botname == 'forward-agent'
    assert results.problem == 'deepdrive/domain_randomization'


def get_test_eval_data():
    ret = Mockable.read_test_box('eval_data.json')
    ret.botleague_liaison_host = constants.HOST
    return ret


def test_results_handler_server_error():
    payload = Mockable.read_test_box('results_error.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = get_test_eval_data()
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
    eval_data = get_test_eval_data()
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert error
    assert error.http_status_code == 400
    assert 'finished' in results


def test_results_handler_already_complete():
    payload = Mockable.read_test_box('results_success.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = get_test_eval_data()
    db.set(db_key, eval_data)
    error, results, eval_data, gist, _ = process_results(payload, db)
    assert error
    assert error.http_status_code == 400
    assert 'finished' in results


def test_confirm_handler():
    payload = Mockable.read_test_box('request.json')
    db = get_liaison_db_store()
    db_key = get_eval_db_key(payload.eval_key)
    eval_data = get_test_eval_data()
    db.set(db_key, eval_data)
    error, resp = process_confirm(payload, db)
    eval_data = get_eval_data(payload.eval_key, db)
    assert not error
    assert resp.confirmed
    assert eval_data.status == constants.EVAL_STATUS_CONFIRMED


def test_score_within_confidence_interval():
    bot_eval = dbox(username='__testuser', botname='__testbot')
    bot_eval.problem_def.acceptable_score_deviation = 100

    bot_eval.results.score = 300
    past_bot_scores = get_past_bot_scores_test([10, 100], bot_eval)

    # Max score here is 270, so should fail
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)[0]

    # Min score here is -160, so should fail
    bot_eval.results.score = -200
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)[0]

    # Let's pass
    bot_eval.results.score = 200
    assert score_within_confidence_interval(bot_eval, past_bot_scores)[0]
    bot_eval.results.score = -100
    assert score_within_confidence_interval(bot_eval, past_bot_scores)[0]

    # Get more confident and fail
    past_bot_scores = get_past_bot_scores_test([100, 100, 100], bot_eval)
    bot_eval.results.score = -100
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)[0]

    # Test first run
    past_bot_scores = get_past_bot_scores_test([], bot_eval)
    assert score_within_confidence_interval(bot_eval, past_bot_scores)[0]

    # Don't fail if bot score is nan
    past_bot_scores = get_past_bot_scores_test([math.nan], bot_eval)
    assert not score_within_confidence_interval(bot_eval, past_bot_scores)[0]

    # Fail fuzz
    bot_eval.problem_def.acceptable_score_deviation = 0.4
    if fuzz_score_within_ci(bot_eval):
        raise RuntimeError(
            f'Fuzz fail failed bot_eval {bot_eval.to_json(indent=2)}')

    # Pass fuzz
    bot_eval.problem_def.acceptable_score_deviation = 0.6
    if not fuzz_score_within_ci(bot_eval):
        raise RuntimeError(
            f'Fuzz failed bot_eval {bot_eval.to_json(indent=2)}')

def fuzz_score_within_ci(bot_eval):
    for _ in range(30):
        past_bot_scores = get_past_bot_scores_test(
            [random() for _ in range(10 ** 3)], bot_eval)
        bot_eval.results.score = random()
        if not score_within_confidence_interval(bot_eval, past_bot_scores)[0]:
            return False
    else:
        return True


def bot_eval_helper():
    """
     Uses test method name for DATA directory in tests/data/<name>
    """
    pr_processor = PrProcessorMock()
    responses, status = pr_processor.process_changes()
    assert len(responses) == 1
    resp = responses[0]
    # noinspection PyUnresolvedReferences
    eval_data = resp.eval_data
    assert isinstance(resp, EvalStartedPrResponse)
    username = eval_data.username
    botname = eval_data.botname
    results = Mockable.read_test_box(join(constants.BOTS_DIR, username, botname,
                                          'results.json'))
    results.eval_key = eval_data.eval_key
    add_eval_data_to_results(eval_data, results)
    # TODO: assert much more here


def test_problem_ci_sim_build():
    pr_event = Mockable.read_test_box('pr_event.json')
    resp, status = handle_pr_request(pr_event)
    assert resp
    assert status is None  # No PR status gets created in test


def get_past_bot_scores_test(past_scores: list, bot_eval: Box):
    if not past_scores:
        get_scores_db().set(get_scores_id(bot_eval), {})
    else:
        past_bot_scores = dbox()

        def get_score(s):
            return Box(score=s, eval_key=generate_rand_alphanumeric(12))

        past_bot_scores.scores = [get_score(s) for s in past_scores]
        past_bot_scores.mean = statistics.mean(
            past_scores) if past_scores else None

        get_scores_db().set(get_scores_id(bot_eval), past_bot_scores)
    ret = get_past_bot_scores(bot_eval)
    return ret
