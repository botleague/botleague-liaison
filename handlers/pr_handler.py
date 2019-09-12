from io import BytesIO
from os.path import join
from typing import List, Union, Tuple

from dulwich import porcelain
from dulwich.repo import Repo
from loguru import logger as log

import github.Repository
import github.Organization

from box import Box

from bot_eval import process_changed_bot
from botleague_helpers.config import blconfig, get_test_name_from_callstack

from constants import ON_GAE
from problem_ci import process_changed_problem
from responses.pr_responses import ErrorPrResponse, StartedPrResponse, \
    RegenPrResponse, IgnorePrResponse, PrResponse, EvalStartedPrResponse, \
    EvalErrorPrResponse
import constants
from tests.mockable import Mockable
from tests.test_constants import CHANGED_FILES_FILENAME
from utils import read_json, trigger_leaderboard_generation, \
    get_liaison_db_store

class PrProcessorBase:
    base_repo: github.Repository = None
    head_repo: github.Repository = None
    pull_number: int = -1
    pr_event: Box
    changed_files: List[Box] = None
    _github_client: github.Github = None
    local_debug = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Support multiple inheritance
        self.is_mock = isinstance(self, Mockable)

    def process_changes(self) -> \
            Tuple[Union[PrResponse, List[PrResponse]], str]:
        pull_request = self.pr_event.pull_request
        head = pull_request.head
        head_repo_name = head.repo.full_name
        self.head_repo = self.get_repo(head_repo_name)
        base_repo_name = pull_request.base.repo.full_name
        self.base_repo = self.get_repo(base_repo_name)
        self.pull_number = pull_request.number
        self.local_debug = pr_is_local_debug(pull_request)

        # Get all the changed files in a pull request
        self.changed_files: List[Box] = self.get_changed_files()

        (base_dirs,
         botname_dirs,
         changed_filenames,
         changed_filetypes,
         changed_problem_definitions,
         user_org_dirs,
         err) = group_changed_files(self.changed_files)

        should_gen = False
        commit_sha = self.pr_event.pull_request.head.sha

        resp, should_gen = self.dispatch(
            base_dirs, botname_dirs, changed_filenames, changed_filetypes,
            self.changed_files, err, pull_request, should_gen, user_org_dirs,
            changed_problem_definitions)
        if should_gen:
            trigger_leaderboard_generation()

        status = self.create_status(resp, commit_sha, self.github_client,
                                    base_repo_name)
        return resp, status

    @staticmethod
    def get_ci_resp(resp) -> Tuple[str, str]:
        if isinstance(resp, PrResponse):
            msg = resp.msg
            if isinstance(resp, ErrorPrResponse):
                status = constants.CI_STATUS_ERROR
            elif isinstance(resp, StartedPrResponse):
                status = constants.CI_STATUS_PENDING
            elif isinstance(resp, RegenPrResponse):
                status = constants.CI_STATUS_SUCCESS
            elif isinstance(resp, IgnorePrResponse):
                status = constants.CI_STATUS_SUCCESS
            else:
                raise RuntimeError('Unexpected response type')
        elif isinstance(resp, list):
            # We've fanned out a number of eval requests 1->N due to
            # multiple problems listed in the problem list.
            # Ensure they've all succeeded.
            msg = '\n'.join([r.msg for r in resp])
            if any(isinstance(r, EvalErrorPrResponse) for r in resp):
                status = constants.CI_STATUS_ERROR
            elif all(isinstance(r, EvalStartedPrResponse) for r in resp):
                status = constants.CI_STATUS_PENDING
            else:
                raise RuntimeError('Unexpected type for eval response')
        else:
            raise RuntimeError('Unexpected response format')
        return status, msg

    def dispatch(self, base_dirs, botname_dirs, changed_filenames,
                 changed_filetypes, changed_files,
                 err, pull_request, should_gen,
                 user_dirs, changed_problem_definitions) -> \
            Tuple[Union[PrResponse, List[PrResponse]], bool]:
        if err is not None:
            resp = err
        elif base_dirs == [constants.BOTS_DIR]:
            resp, should_gen = process_changed_bot(
                base_repo=self.base_repo,
                botname_dirs=botname_dirs,
                changed_filenames=changed_filenames,
                changed_files=changed_files,
                head_repo=self.head_repo,
                pull_request=pull_request,
                user_dirs=user_dirs,
                changed_filetypes=changed_filetypes,
                from_mock=self.is_mock,
                github_client=self.github_client,
                local_debug=self.local_debug,)
        elif base_dirs == [constants.PROBLEMS_DIR]:
            # If this is an existing problem, trigger a problem rerun
            # If it's a new problem, just return should_gen
            resp, should_gen = process_changed_problem(
                changed_problem_definitions,
                base_repo=self.base_repo,
                changed_filenames=changed_filenames,
                changed_files=changed_files,
                head_repo=self.head_repo,
                pull_request=pull_request,
                user_dirs=user_dirs,
                changed_filetypes=changed_filetypes,
                from_mock=self.is_mock,
                github_client=self.github_client,
                local_debug=self.local_debug,)
        elif constants.BOTS_DIR in base_dirs or \
                constants.PROBLEMS_DIR in base_dirs:
            # Fail pull request, either a bot or problem,
            # not both can be changed in a single pull request
            resp = ErrorPrResponse(
                'Either a bot or problem, not both, can be changed '
                'in a single pull request')
        elif 'json' in changed_filetypes:
            # Fail pull request. Unexpected files, json files should
            # only be changed in the context of a bot or problem.
            resp = ErrorPrResponse('Unexpected files, json files should '
                                 'only be changed in the context of a bot or '
                                 'problem.')
        else:
            # Allow the pull request, likely a docs / license, etc... change
            resp = IgnorePrResponse('No leaderboard changes detected')
        return resp, should_gen

    @staticmethod
    def create_status(resp, commit_sha, github_client, repo_name):
        raise NotImplementedError()

    @staticmethod
    def get_repo(repo_name):
        raise NotImplementedError()

    def get_changed_files(self) -> List[Box]:
        raise NotImplementedError()

    @property
    def github_client(self):
        raise NotImplementedError()


def pull_botleague():
    porcelain.pull(
        constants.BOTLEAGUE_REPO_ROOT,
        remote_location='https://github.com/botleague/botleague',
        refspecs=b'refs/heads/master',)


class PrProcessor(PrProcessorBase):
    def __init__(self, pr_event):
        if get_test_name_from_callstack():
            raise RuntimeError('Should not be using this class in tests!')
        super().__init__()
        self.pr_event = pr_event
        pull_botleague()

    def get_changed_files(self) -> List[Box]:
        # See tests/data/bot_eval/changed_files.json
        if self.changed_files is None:
            ret = list(self.base_repo.get_pull(self.pull_number).get_files())
            ret = [Box(r.raw_data) for r in ret]
            self.changed_files = ret
        return self.changed_files

    def get_repo(self, repo_name):
        return self.github_client.get_repo(repo_name)

    def create_status(self, resp, commit_sha, github_client, repo_name):
        status, msg = self.get_ci_resp(resp)
        repo = github_client.get_repo(repo_name)
        commit = repo.get_commit(sha=commit_sha)

        # status can be error, failure, pending, or success

        status = commit.create_status(
            status,
            description=msg,
            # target_url='https://botleague.io/users/username/botname/this-evaluation',
            context='Botleague')
        log.success(f'Created status on pull request '
                    f'{Box(status.raw_data).to_json(indent=2, default=str)}')
        return status

    @property
    def github_client(self):
        if PrProcessor._github_client is None:
            # Lazy load class variable. Note this doesn't affect the base class
            PrProcessor._github_client = github.Github(blconfig.github_token)
        return PrProcessor._github_client


class PrProcessorMock(PrProcessorBase, Mockable):
    def __init__(self):
        super().__init__()
        self.pr_event = self.get_pr_event()

    def get_changed_files(self):
        files = read_json(self.get_test_filename(CHANGED_FILES_FILENAME))
        ret = [Box(f) for f in files]
        return ret

    @staticmethod
    def get_repo(repo_name):
        return None

    @staticmethod
    def create_status(resp, commit_sha, github_client, repo_name):
        return None

    @property
    def github_client(self):
        return None


def get_pr_processor(pr_event=None) -> PrProcessorBase:
    if blconfig.is_test:
        # This is a guard rail, you should just use the mock constructor in
        # tests
        ret = PrProcessorMock()
    else:
        ret = PrProcessor(pr_event)
    return ret


def group_changed_files(changed_files: List[Box]):
    base_dirs = set()
    user_org_dirs = set()
    botname_dirs = set()
    problem_dirs = set()
    changed_filenames = []
    changed_filetypes = set()
    changed_problem_definitions = set()
    err = None
    for changed_file in changed_files:
        filename = changed_file.filename
        changed_filenames.append(filename)
        path_parts = filename.split('/')
        base_dir = path_parts[0]
        err = None
        if base_dir == constants.BOTS_DIR:
            if len(path_parts) != 4:
                # Expect something like
                #   ['bots', user_or_org, botname, 'bot.json']
                err = ErrorPrResponse('Malformed bot submission')
                break
            elif path_parts[-1] not in constants.ALLOWED_BOT_FILENAMES:
                err = ErrorPrResponse('%s not an allowed bot file name' %
                                      path_parts[-1])
                break
            elif changed_file.status == 'renamed':
                # Verify that botnames and usernames have not been changed
                # We do this to avoid complicated migrations in the
                # leaderboard data. If someone changes their GitHub name,
                # they will get a new user for now.
                err = ErrorPrResponse('Renaming bots currently not supported')
                break
            else:
                user_org_dirs.add(path_parts[1])
                botname_dirs.add(path_parts[2])
        elif base_dir == constants.PROBLEMS_DIR:
            if len(path_parts) != 4:
                # Expect something like
                #   ['problems', user_or_org, problem_name, 'problem.json']
                err = ErrorPrResponse('Malformed problem submission')
                break
            elif path_parts[-1] not in constants.ALLOWED_PROBLEM_FILENAMES:
                err = ErrorPrResponse('%s not an allowed bot file name' %
                                      path_parts[-1])
                break
            elif changed_file.status == 'renamed':
                err = ErrorPrResponse(constants.RENAME_PROBLEM_ERROR_MSG)
                break
            else:
                add_changed_problem(changed_problem_definitions, changed_file)
                user_org_dirs.add(path_parts[1])
                problem_dirs.add(path_parts[2])
        base_dirs.add(base_dir)
        filetype = filename.split('.')[-1]
        changed_filetypes.add(filetype)
    base_dirs = list(base_dirs)
    pre_ret = (base_dirs, botname_dirs, changed_filenames,
               changed_filetypes, changed_problem_definitions,
               user_org_dirs, err)

    ret = []
    for item in pre_ret:
        if isinstance(item, set):
            ret.append(list(item))
        else:
            ret.append(item)
    return ret


def add_changed_problem(changed_problem_definitions, changed_file):
    modified = changed_file.status == 'modified'
    is_prob_def = changed_file.filename.endswith(
        constants.PROBLEM_DEFINITION_FILENAME)
    if modified and is_prob_def:
        changed_problem_definitions.add(changed_file.filename)


if __name__ == '__main__':
    pull_botleague()


def pr_is_local_debug(pull_request):
    return ON_GAE and pull_request.body == 'LOCAL_DEBUG'

