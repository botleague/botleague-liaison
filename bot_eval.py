import random
import time
import uuid

import constants as c
import requests
from botleague_helpers.key_value_store import SimpleKeyValueStore
from responses import ErrorResponse, StartedResponse
from util import get_from_github


def bot_eval(changed_filenames, user_or_org, base_repo, head_repo,
             pull_request):
    # Validate bot.json
    bot_def_filenames = []
    bot_readme_filenames = []
    for filename in changed_filenames:
        if filename.endswith(c.BOT_DEFINITION_FILENAME):
            bot_def_filenames.append(filename)
        elif filename.endswith(c.README_FILENAME):
            bot_readme_filenames.append(filename)

    # Do evaluations
    if bot_def_filenames:
        if len(bot_def_filenames) > 1:
            return ErrorResponse('Only one bot per pull request allowed')
        else:
            ret = eval_bot(base_repo, bot_def_filenames[0],
                           head_repo, user_or_org, pull_request)

            if isinstance(ret, ErrorResponse):
                return ret

    # TODO: Copy the docker image over to GCR
    # TODO: Add botname to results.json
    # TODO: Add username to results.json
    # TODO: Handle cases where only readme changes
    pass


def eval_bot(base_repo, bot_def_filename, head_repo, user_or_org, pull_request):
    seed = random.choice(range(1, 10 ** 6))
    bot_def = get_from_github(head_repo, bot_def_filename)
    source_commit = bot_def['source_commit']
    github_prefix = 'https://github.com/'

    if not source_commit.startswith(github_prefix):
        return ErrorResponse('source_commit does not start with ' +
                             github_prefix)

    # Validate that user_or_org matches source_commit and json_commit.
    source_commit_user = source_commit[
                         len(github_prefix):].split('/')[0]
    if source_commit_user.lower() != user_or_org.lower():
        return ErrorResponse('Bot directory does not match user or org name'
                             'on source repo, aborting')
    problem_ids = bot_def['problems']
    prob_responses = eval_bots_problems(base_repo, problem_ids, seed, bot_def,
                                        pull_request)
    return prob_responses


def eval_bots_problems(base_repo, problem_ids, seed, bot_def, pull_request):
    responses = []
    for problem_id in problem_ids:
        problem_def_url = '%s/%s/%s' % (c.PROBLEMS_DIR, problem_id,
                                        c.PROBLEM_DEFINITION_FILENAME)
        # Ensure the problem exists
        problem_def = get_from_github(base_repo, problem_def_url)
        if not problem_def:
            # Problem does not exist
            return ErrorResponse('Problem does not exist %s' % problem_id)
        else:
            # Trigger the eval at the problem endpoint
            trigger_eval(bot_def, problem_def, pull_request, responses, seed,
                         problem_id)


def trigger_eval(bot_def, problem_def, pull_request, responses, seed,
                 problem_id):
    endpoint = problem_def['endpoint']
    eval_key = uuid.uuid4().hex
    pull_number = pull_request['number']
    pull_url = pull_request['url']
    pull_request_updated_at = pull_request['updated_at']
    merge_commit_sha = pull_request['merge_commit_sha']
    head_commit = pull_request['head']['sha']
    base_commit = pull_request['base']['sha']
    head_full_name = pull_request['head']['repo']['full_name']
    base_full_name = pull_request['base']['repo']['full_name']
    now = time.time()
    eval_data = dict(eval_key=eval_key,
                     seed=seed,
                     problem_id=problem_id,
                     status=c.EVAL_STATUS_STARTED,
                     created_at=now,
                     pull_request=dict(
                         url=pull_url,
                         number=pull_number,
                         updated_at=pull_request_updated_at,
                         merge_commit_sha=merge_commit_sha,
                         head_commit=head_commit,
                         head_full_name=head_full_name,
                         base_commit=base_commit,
                         base_full_name=base_full_name,
                     ),)
    try:
        resp = requests.post(endpoint, json=eval_data, timeout=10)
    except requests.exceptions.Timeout:
        responses.append(ErrorResponse(
            'Endpoint %s took too long to respond' % endpoint))
    else:
        if resp.status_code != 200:
            responses.append(ErrorResponse(
                'Endpoint %s did not respond with success' % endpoint))
        else:
            kv = SimpleKeyValueStore()
            db_key = '%s_%s' % (c.ONGOING_EVALUATIONS_KEY_PREFIX, eval_key)
            kv.set(db_key, eval_data)
            # TODO: Now we wait for a /confirm and /results request with the
            #   eval_key
            responses.append(StartedResponse('Started evaluation at %s' %
                                             endpoint))
