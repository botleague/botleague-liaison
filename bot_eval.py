import random
import uuid

import constants as c
import requests
from botleague_helpers.key_value_store import SimpleKeyValueStore
from responses import ErrorResponse, StartedResponse
from util import get_from_github


def bot_eval(changed_filenames, user_or_org, base_repo, head_repo):
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
        ret = eval_bots(base_repo, bot_def_filenames, head_repo, user_or_org)

        if isinstance(ret, ErrorResponse):
            return ret

    # TODO: Copy the docker image over to GCR
    # TODO: Add botname to results.json
    # TODO: Add username to results.json
    # TODO: Validate that user_or_org matches source_commit
    #   and json_commit.
    # TODO: Handle cases where only readme changes
    pass


def eval_bots(base_repo, bot_def_filenames, head_repo, user_or_org):
    seed = random.choice(range(1, 10 ** 6))
    for bot_filename in bot_def_filenames:
        bot_def = get_from_github(head_repo, bot_filename)
        source_commit = bot_def['source_commit']
        github_prefix = 'https://github.com/'
        if not source_commit.startswith(github_prefix):
            return ErrorResponse('source_commit does not start with ' +
                                 github_prefix)
        source_commit_user = source_commit[
                             len(github_prefix):].split('/')[0]
        if source_commit_user != user_or_org:
            return ErrorResponse('User did not create commit, aborting')
        problem_ids = bot_def['problems']
        eval_problems(base_repo, problem_ids, seed)


def eval_problems(base_repo, problem_ids, seed):
    for problem_id in problem_ids:
        problem_def_url = '%s/%s/%s' % (base_repo.full_name, problem_id,
                                        c.PROBLEM_DEFINITION_FILENAME)
        # Ensure the problem exists
        problem_def = get_from_github(base_repo, problem_def_url)
        if not problem_def:
            # Problem does not exist
            # TODO: Fail pull request
            pass
        else:
            # Trigger the eval at the problem endpoint
            endpoint = problem_def['endpoint']
            eval_key = uuid.uuid4().hex
            eval_data = dict(eval_key=eval_key, seed=seed)
            requests.post(endpoint, json=eval_data)