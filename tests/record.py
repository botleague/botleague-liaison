import os
os.environ['DISABLE_CLOUD_LOGGING'] = '1'

from botleague_helpers.config import disable_firestore_access, blconfig
from handlers.pr_handler import PrProcessor
from tests.mockable import Mockable
from tests.test_constants import CHANGED_FILES_FILENAME
from utils import write_json

# Just use a local github token, no need to fetch from firestore.
# Also, we don't want to be setting things like
# should_gen on the production db here.
disable_firestore_access()

def record_start_bot_eval():
    record_changed_files_for_test('bot_eval')

def record_problem_ci_sim_build():
    record_changed_files_for_test('problem_ci_sim_build')


def record_changed_files_for_test(test_name):
    pr_event = Mockable.get_pr_event_from_test_name(test_name)
    record_changed_files(pr_event, test_name)

def record_changed_files(pr_event, test_name):
    pr_processor = PrProcessor(pr_event)
    resp = pr_processor.setup()
    changed_files = pr_processor.get_changed_files()
    out_filename = Mockable.get_test_filename_from_test_name(
        test_name, CHANGED_FILES_FILENAME)
    write_json(changed_files, out_filename)
    print('Wrote changed files to %s' % out_filename)


if __name__ == '__main__':
    record_problem_ci_sim_build()
