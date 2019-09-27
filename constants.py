import os
from os.path import dirname, join, realpath

ROOT_DIR = dirname(realpath(__file__))
BOTLEAGUE_REPO_ROOT = join('/tmp', 'botleague')

BOTS_DIR = 'bots'
PROBLEMS_DIR = 'problems'
PROBLEM_DEFINITION_FILENAME = 'problem.json'
BOT_DEFINITION_FILENAME = 'bot.json'
README_FILENAME = 'README.md'

PR_STATUS_ERROR = 'error'
PR_STATUS_FAILURE = 'failure'
PR_STATUS_PENDING = 'pending'
PR_STATUS_SUCCESS = 'success'

EVAL_STATUS_STARTED = 'started'
EVAL_STATUS_CONFIRMED = 'confirmed'
EVAL_STATUS_COMPLETE = 'complete'

ONGOING_EVALUATIONS_KEY_PREFIX = 'botleague_eval'
ONGOING_PROBLEM_CI_KEY_PREFIX = 'botleague_problem_ci'

ALLOWED_BOT_FILENAMES = [BOT_DEFINITION_FILENAME, README_FILENAME]
ALLOWED_PROBLEM_FILENAMES = [PROBLEM_DEFINITION_FILENAME, README_FILENAME]

SHOULD_RECORD = 'SHOULD_RECORD' in os.environ

# Error messages
RENAME_PROBLEM_ERROR_MSG = 'Renaming problems currently not supported'

BOTLEAGUE_RESULTS_GITHUB_TOKEN_NAME = 'BOTLEAGUE_RESULTS_GITHUB_TOKEN_encrypted'

ON_GAE = 'GAE_APPLICATION' in os.environ

HOST = 'https://liaison.botleague.io'
