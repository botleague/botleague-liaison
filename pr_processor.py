from os.path import join
from typing import List, Union, Tuple

import logging as log

import github.Repository
import github.Organization

from box import Box

from bot_eval import process_changed_bot
from botleague_helpers.config import blconfig, get_test_name_from_callstack
from botleague_helpers.key_value_store import SimpleKeyValueStore
from responses import ErrorResponse, StartedResponse, RegenResponse, \
    IgnoreResponse, Response, EvalStartedResponse, EvalErrorResponse
import constants
from tests.mockable import Mockable
from tests.test_constants import CHANGED_FILES_FILENAME
from utils import read_json

log.basicConfig(level=log.INFO)


class PrProcessorBase:
    base_repo: github.Repository = None
    head_repo: github.Repository = None
    pull_number: int = -1
    pr_event: Box
    changed_files: List[Box]
    _github_client: github.Github = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Support multiple inheritance
        self.is_mock = isinstance(self, Mockable)

    def process_changes(self) -> Tuple[Union[Response, List[Response]], str]:
        pull_request = self.pr_event.pull_request
        head = pull_request.head
        head_repo_name = head.repo.full_name
        self.head_repo = self.get_repo(head_repo_name)
        base_repo_name = pull_request.base.repo.full_name
        self.base_repo = self.get_repo(base_repo_name)
        self.pull_number = pull_request.number

        # Get all the changed files in a pull request
        self.changed_files = self.get_changed_files()

        (base_dirs,
         botname_dirs,
         changed_filenames,
         changed_filetypes,
         user_dirs,
         err) = group_changed_files(self.changed_files)

        should_gen = False
        commit_sha = self.pr_event.pull_request.head.sha

        resp, should_gen = self.dispatch(
            base_dirs, botname_dirs, changed_filenames, changed_filetypes,
            err, pull_request, should_gen, user_dirs)
        if should_gen:
            SimpleKeyValueStore().set(blconfig.should_gen_key, True)

        status = self.create_status(resp, commit_sha, self.github_client,
                                    base_repo_name)
        return resp, status

    @staticmethod
    def get_ci_resp(resp) -> Tuple[str, str]:
        if isinstance(resp, Response):
            msg = resp.msg
            if isinstance(resp, ErrorResponse):
                status = constants.CI_STATUS_ERROR
            elif isinstance(resp, StartedResponse):
                status = constants.CI_STATUS_PENDING
            elif isinstance(resp, RegenResponse):
                status = constants.CI_STATUS_SUCCESS
            elif isinstance(resp, IgnoreResponse):
                status = constants.CI_STATUS_SUCCESS
            else:
                raise RuntimeError('Unexpected response type')
        elif isinstance(resp, list):
            # We've fanned out a number of eval requests 1->N,
            # Ensure they've all succeeded.
            msg = '\n'.join([r.msg for r in resp])
            if any(isinstance(r, EvalErrorResponse) for r in resp):
                status = constants.CI_STATUS_ERROR
            elif all(isinstance(r, EvalStartedResponse) for r in resp):
                status = constants.CI_STATUS_PENDING
            else:
                raise RuntimeError('Unexpected type for eval response')
        else:
            raise RuntimeError('Unexpected response format')
        return status, msg

    def dispatch(self, base_dirs, botname_dirs, changed_filenames,
                 changed_filetypes, err, pull_request, should_gen,
                 user_dirs) -> Tuple[Union[Response, List[Response]], bool]:
        if err is not None:
            resp = err
        elif base_dirs == [constants.BOTS_DIR]:
            resp, should_gen = process_changed_bot(
                base_repo=self.base_repo,
                botname_dirs=botname_dirs,
                changed_filenames=changed_filenames,
                head_repo=self.head_repo,
                pull_request=pull_request,
                user_dirs=user_dirs,
                changed_filetypes=changed_filetypes,
                from_mock=self.is_mock,
                github_client=self.github_client)
        elif base_dirs == [constants.PROBLEMS_DIR]:
            # Trigger problem CI
            # TODO: Verify that a problem submission does not change the name of
            #  an existing problem - use "renamed" to key off of as we did with
            #  bots
            pass
        elif constants.BOTS_DIR in base_dirs or \
                constants.PROBLEMS_DIR in base_dirs:
            # Fail pull request, either a bot or problem,
            # not both can be changed in a single pull request
            resp = ErrorResponse(
                'Either a bot or problem, not both, can be changed '
                'in a single pull request')
        elif 'json' in changed_filetypes:
            # Fail pull request. Unexpected files, json files should
            # only be changed in the context of a bot or problem.
            resp = ErrorResponse('Unexpected files, json files should '
                                 'only be changed in the context of a bot or '
                                 'problem.')
        else:
            # Allow the pull request, likely a docs / license, etc... change
            resp = IgnoreResponse('No leaderboard changes detected')
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


class PrProcessor(PrProcessorBase):
    def __init__(self, pr_event):
        if get_test_name_from_callstack():
            raise RuntimeError('Should not be using this class in tests!')
        super().__init__()
        self.pr_event = pr_event

    def get_changed_files(self) -> List[Box]:
        if self.changed_files is not None:
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
            target_url='https://botleague.io/users/username/botname/this-evaluation',
            context='Botleague')
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
    if c.is_test:
        # This is a guard rail, you should just use the mock constructor in
        # tests
        ret = PrProcessorMock()
    else:
        ret = PrProcessor(pr_event)
    return ret


def group_changed_files(changed_files):
    base_dirs = set()
    user_dirs = set()
    botname_dirs = set()
    problem_dirs = set()
    changed_filenames = []
    changed_filetypes = set()
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
                #   ['bots', username, botname, 'bot.json']
                err = ErrorResponse('Malformed bot submission')
                break
            elif path_parts[-1] not in constants.ALLOWED_BOT_FILENAMES:
                err = ErrorResponse('%s not an allowed bot file name' %
                                    path_parts[-1])
                break
            elif changed_file.status == 'renamed':
                # Verify that botnames and usernames have not been changed
                # We do this to avoid complicated migrations in the
                # leaderboard data. If someone changes their GitHub name,
                # they will get a new user for now.
                err = ErrorResponse('Renaming bots currently not supported')
                break
            else:
                user_dirs.add(path_parts[1])
                botname_dirs.add(path_parts[2])
        elif base_dir == constants.PROBLEMS_DIR:
            if len(path_parts) != 3:
                # Expect something like
                #   ['problems', problem_id, 'problem.json']
                err = ErrorResponse('Malformed problem submission')
                break
            elif path_parts[-1] not in constants.ALLOWED_PROBLEM_FILENAMES:
                err = ErrorResponse('%s not an allowed bot file name' %
                                    path_parts[-1])
                break
            elif changed_file.status == 'renamed':
                err = ErrorResponse(constants.RENAME_PROBLEM_ERROR_MSG)
                break
            else:
                problem_dirs.add(path_parts[1])
        base_dirs.add(base_dir)
        filetype = filename.split('.')[-1]
        changed_filetypes.add(filetype)
    base_dirs = list(base_dirs)
    pre_ret = (base_dirs, botname_dirs, changed_filenames,
               changed_filetypes, user_dirs, err)

    ret = []
    for item in pre_ret:
        if isinstance(item, set):
            ret.append(list(item))
        else:
            ret.append(item)
    return ret

