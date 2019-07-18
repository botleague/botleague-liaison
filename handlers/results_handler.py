import time

from botleague_helpers.key_value_store import get_key_value_store, \
    SimpleKeyValueStore
from box import Box

from bot_eval import get_eval_db_key
import constants
from models.eval_data import get_eval_data


def handle_results_request(request):
    """
    Handles results POSTS from problem evaluators at the end of evaluation
    """
    data = Box(request.json)
    kv = get_key_value_store()
    error, results = process_results(data, kv)

    if error.msg:
        request.response.status = error.http_status_code
        results.error = error
    else:
        request.response.status = 200

    return results

    # TODO: Post results to gist
    # TODO: Set status on eval_data to complete


def process_results(result_payload: Box, kv: SimpleKeyValueStore):
    eval_key = result_payload.get('eval_key', '')
    results = result_payload.get('results', Box())
    results.finished = time.time()
    error = Box(default_box=True)
    if not eval_key:
        error.http_status_code = 400
        error.msg = 'eval_key must be in JSON data payload'
    else:
        eval_data = get_eval_data(eval_key, kv)
        if not eval_data:
            error.http_status_code = 400
            error.msg = 'Could not find evaluation with that key'
        elif not eval_data.status == constants.EVAL_STATUS_STARTED:
            error.http_status_code = 400
            error.msg = 'This evaluation has already been processed'
        else:
            if 'error' in result_payload:
                error.http_status_code = 500
                error.msg = result_payload.error
            elif 'results' not in result_payload:
                error.http_status_code = 400
                error.msg = 'No "results" found in request'
            add_eval_data_to_results(eval_data, results)

    return error, results


def add_eval_data_to_results(eval_data: Box, results: Box):
    results.username = eval_data.username
    results.botname = eval_data.botname
    results.problem_id = eval_data.problem_id
    results.started = eval_data.started
    results.league_commit_sha = eval_data.league_commit_sha
    results.source_commit = eval_data.source_commit
    results.seed = eval_data.seed
