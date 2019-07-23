import time
from typing import Tuple, Optional

import github
from botleague_helpers.config import get_test_name_from_callstack, blconfig
from botleague_helpers.key_value_store import get_key_value_store, \
    SimpleKeyValueStore
from box import Box
from github import Github, PullRequestMergeStatus, GithubException
import github.Gist

from bot_eval import get_eval_db_key
import constants
from models.eval_data import get_eval_data, save_eval_data
import logging as log

from responses.error import Error
from utils import trigger_leaderboard_generation

log.basicConfig(level=log.INFO)


def handle_results_request(request):
    """
    Handles results POSTS from problem evaluators at the end of evaluation
    """
    data = Box(request.json)
    kv = get_key_value_store()
    error, results, eval_data = process_results(data, kv)
    eval_data.status = constants.EVAL_STATUS_COMPLETE
    save_eval_data(eval_data, kv)

    if not error:
        error = merge_pull_request(eval_data.pull_request)

    if error:
        results.error = error

    return results, error


def merge_pull_request(pull_request: Box) -> Error:
    error = Error()
    if blconfig.is_test or get_test_name_from_callstack():
        log.info('Skipping pr merge in test')
    else:
        github_client = Github(blconfig.github_token)
        repo = github_client.get_repo(pull_request.base_full_name)
        pr = repo.get_pull(pull_request.number)
        try:
            merge_status = pr.merge('Automatically merged by Botleague')
            if not merge_status.merged:
                error.message = merge_status.message
                error.http_status_code = 400
        except GithubException as e:
            error.message = str(e)
            error.http_status_code = e.status

    return error


def post_results_to_gist(kv, results) -> Optional[github.Gist.Gist]:
    if blconfig.is_test or get_test_name_from_callstack():
        log.info('DETECTED TEST MODE: Not uploading results.')
        ret = None
    else:
        github_client = Github(
            kv.get(constants.BOTLEAGUE_RESULTS_GITHUB_TOKEN_NAME))
        ret = github_client.get_user().create_gist(
            public=True,
            files={'results.json': github.InputFileContent(
                results.to_json(indent=2))},
            description='Automatically uploaded by botleague liaison')
    return ret


def process_results(result_payload: Box,
                    kv: SimpleKeyValueStore) -> Tuple[Box, Box, Box]:
    eval_key = result_payload.get('eval_key', '')
    results = result_payload.get('results', Box())
    results.finished = time.time()
    error = Box(default_box=True)
    eval_data = Box()
    if not eval_key:
        error.http_status_code = 400
        error.msg = 'eval_key must be in JSON data payload'
    else:
        eval_data = get_eval_data(eval_key, kv)
        if not eval_data:
            error.http_status_code = 400
            error.msg = 'Could not find evaluation with that key'
        elif eval_data.status == constants.EVAL_STATUS_STARTED:
            error.http_status_code = 400
            error.msg = 'This evaluation has not been confirmed'
        elif eval_data.status == constants.EVAL_STATUS_COMPLETE:
            error.http_status_code = 400
            error.msg = 'This evaluation has already been processed'
        elif eval_data.status == constants.EVAL_STATUS_CONFIRMED:
            if 'error' in result_payload:
                error.http_status_code = 500
                error.msg = result_payload.error
            elif 'results' not in result_payload:
                error.http_status_code = 400
                error.msg = 'No "results" found in request'
            add_eval_data_to_results(eval_data, results)
        else:
            error.http_status_code = 400
            error.msg = 'Eval data status unknown %s' % eval_data.status

    return error, results, eval_data


def add_eval_data_to_results(eval_data: Box, results: Box):
    results.username = eval_data.username
    results.botname = eval_data.botname
    results.problem = eval_data.problem_id
    results.started = eval_data.started
    results.league_commit_sha = eval_data.league_commit_sha
    results.source_commit = eval_data.source_commit
    results.seed = eval_data.seed
    results.utc_timestamp = time.time()
