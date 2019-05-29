import random
import time
import uuid
from typing import List

import constants as c
import github
import requests
from botleague_helpers.key_value_store import SimpleKeyValueStore
from github import Repository
from responses import ErrorResponse, StartedResponse
from util import get_from_github


class BotEval:
    botname: str
    changed_filenames: List[str]
    user_or_org: str
    base_repo: Repository
    head_repo: Repository
    pr: dict
    seed: int

    def __init__(self, botname, changed_filenames, user_or_org, base_repo,
                 head_repo, pull_request):
        self.botname = botname
        self.changed_filenames = changed_filenames
        self.user_or_org = user_or_org
        self.base_repo = base_repo
        self.head_repo = head_repo
        self.pr = pull_request
        self.seed = random.choice(range(1, 10 ** 6))

    def eval(self):
        # Validate bot.json
        bot_def_filenames = []
        bot_readme_filenames = []
        for filename in self.changed_filenames:
            if filename.endswith(c.BOT_DEFINITION_FILENAME):
                bot_def_filenames.append(filename)
            elif filename.endswith(c.README_FILENAME):
                bot_readme_filenames.append(filename)

        # Do evaluations
        if bot_def_filenames:
            if len(bot_def_filenames) > 1:
                return ErrorResponse('Only one bot per pull request allowed')
            else:
                ret = self.eval_bot(bot_def_filenames[0])

                if isinstance(ret, ErrorResponse):
                    return ret

        # TODO: Copy the docker image over to GCR
        # TODO: Add botname to results.json
        # TODO: Add username to results.json
        # TODO: Handle cases where only readme changes

    def eval_bot(self, bot_def_filename):
        bot_def = get_from_github(self.head_repo, bot_def_filename)
        source_commit = bot_def['source_commit']

        github_prefix = 'https://github.com/'

        if not source_commit.startswith(github_prefix):
            return ErrorResponse('source_commit does not start with ' +
                                 github_prefix)

        # Validate that user_or_org matches source_commit and json_commit.
        source_commit_user = source_commit[
                             len(github_prefix):].split('/')[0]

        # TODO: Get the botname from the JSON commit path. It does not have to match
        #   the source_commit, i.e. deepdrive agents.

        # TODO: Move bot readme to botleague (not in the source repo),
        #   as some bots may just bot docker containers.
        if source_commit_user.lower() != self.user_or_org.lower():
            return ErrorResponse('Bot directory does not match user or org name'
                                 'on source repo, aborting')
        problem_ids = bot_def['problems']
        prob_responses = self.eval_bots_problems(problem_ids, bot_def)
        return prob_responses

    def eval_bots_problems(self, problem_ids, bot_def):
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
                self.trigger_eval(bot_def, problem_def, problem_id, responses)

    def trigger_eval(self, bot_def, problem_def, problem_id, responses):
        endpoint = problem_def['endpoint']
        eval_key = uuid.uuid4().hex
        pull_number = self.pr['number']
        pull_url = self.pr['url']
        pull_request_updated_at = self.pr['updated_at']
        merge_commit_sha = self.pr['merge_commit_sha']
        head_commit = self.pr['head']['sha']
        base_commit = self.pr['base']['sha']
        head_full_name = self.pr['head']['repo']['full_name']
        base_full_name = self.pr['base']['repo']['full_name']
        now = time.time()
        eval_data = dict(eval_key=eval_key,
                         seed=self.seed,
                         problem_id=problem_id,
                         botname=self.botname,
                         username=self.user_or_org,
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
            # Yay, we did not timeout!
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


    def handle_results(results):
        # TODO: Test locally generated results.json by transforming it to required
        #   format - pull eval info using eval_key
        #   Add:
        #   - username
        #   - botname
        #   - problem
        #   - "status": "success",
        #   - "utc_timestamp": 86600000,
        #   - "json_commit": "https://github.com/deepdrive/agent-zoo/commit/3a0e6af15c5ee05b62c6705d40aece250112a57d"
        #   - "source_commit": "https://github.com/crizCraig/forward-agent/commit/defc93d95944099d3e61cda6542bb4ffe7a28abf"
        #   -

        pass