import os
from os.path import join

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = join(TEST_DIR, 'data')
PR_EVENT_FILENAME = 'pr_event.json'
CHANGED_FILES_FILENAME = 'changed_files.json'

