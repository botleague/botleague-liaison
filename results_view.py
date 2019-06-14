import time

from botleague_helpers.key_value_store import get_key_value_store, \
    SimpleKeyValueStore
from box import Box

from bot_eval import get_eval_db_key


def handle_results_request(request):
    data = Box(request.json)
    kv = get_key_value_store()
    error, results = process_results(data, kv)

    if error.msg:
        request.response.status = error.http_status_code
        results.error = error

    # TODO: Post results to gist


def process_results(result_payload: Box, kv: SimpleKeyValueStore):
    eval_key = result_payload.get('eval_key', '')
    results = result_payload.get('results', Box())
    results.finished = time.time()
    error = Box(default_box=True)
    if not eval_key:
        error.http_status_code = 400
        error.msg = 'eval_key must be in JSON data payload'
    elif 'results' not in result_payload:
        error.http_status_code = 400
        error.msg = 'No "results" found in request'
    else:
        db_key = get_eval_db_key(eval_key)
        # eval_key is secret
        eval_data = Box(kv.get(db_key))
        if not eval_data:
            error.http_status_code = 400
            error.msg = 'Could not find evaluation with that key'
        else:
            add_eval_data_to_results(eval_data, results)

    if 'error' in result_payload:
        error.http_status_code = 500
        error.msg = result_payload.error

    return error, results


def add_eval_data_to_results(eval_data: Box, results: Box):
    """
    Handles results POSTS from problem evaluators at the
    """
    # Get the eval_data using the result.eval_key

    results.username = eval_data.username
    results.botname = eval_data.botname
    results.problem_id = eval_data.problem_id
    results.started = eval_data.started
    results.league_commit_sha = eval_data.league_commit_sha
    results.source_commit = eval_data.source_commit
    results.seed = eval_data.seed
