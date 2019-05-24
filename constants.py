import os

# TODO: Move this and key_value_store into shared botleague-gcp pypi package

# For local testing, set SHOULD_USE_FIRESTORE=false in your environment
from botleague_helpers.constants import GITHUB_TOKEN
from github import Github

GITHUB_CLIENT = Github(GITHUB_TOKEN)
BOTS_DIR = 'bots'
PROBLEMS_DIR = 'problems'
PROBLEM_DEFINITION_FILENAME = 'problem.json'
BOT_DEFINITION_FILENAME = 'bot.json'
README_FILENAME = 'README.md'

CI_STATUS_ERROR = 'error'
CI_STATUS_FAILURE = 'failure'
CI_STATUS_PENDING = 'pending'
CI_STATUS_SUCCESS = 'success'

EVAL_STATUS_STARTED = 'started'

ONGOING_EVALUATIONS_COLLECTION_NAME = 'botleague_ongoing_evaluations'
ONGOING_EVALUATIONS_KEY_PREFIX = 'botleague_eval'

ALLOWED_BOT_FILENAMES = [BOT_DEFINITION_FILENAME, README_FILENAME]
ALLOWED_PROBLEM_FILENAMES = [PROBLEM_DEFINITION_FILENAME, README_FILENAME]
