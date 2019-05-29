import os

ROOT_DIR = os.path.dirname(os.path.realpath(__file__))

IS_TEST = 'IS_TEST' in os.environ
SHOULD_MOCK_GITHUB = 'SHOULD_MOCK_GITHUB' in os.environ

# For local testing, set SHOULD_USE_FIRESTORE=false in your environment
if SHOULD_MOCK_GITHUB:
    GITHUB_TOKEN = None
    GITHUB_CLIENT = None
else:
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

SHOULD_RECORD = 'SHOULD_RECORD' in os.environ

# Error messages
RENAME_PROBLEM_ERROR_MSG = 'Renaming problems currently not supported'
