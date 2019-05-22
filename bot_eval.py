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
        elif filename.endswith(c.BOT_README_FILENAME):
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
            endpoint = problem_def['endpoint']
            eval_key = uuid.uuid4().hex
            eval_data = dict(eval_key=eval_key, seed=seed)
            requests.post(endpoint, json=eval_data)