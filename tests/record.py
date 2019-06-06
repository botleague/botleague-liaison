from os.path import join
from box import Box

from botleague_helpers.config import disable_firestore_access
import constants
from pr_processor import PrProcessor
from tests.mockable import Mockable
from tests.test_constants import TEST_DIR, CHANGED_FILES_FILENAME
from utils import read_json, write_json

# Just use a local github token, no need to fetch from firestore.
# Also, we don't want to be setting things like
# should_gen on the production db here.
disable_firestore_access()


def record_start_bot_eval():
    test_name = 'bot_eval'
    pr_event = Mockable.get_pr_event_from_test_name(test_name)
    record_changed_files(pr_event, test_name)


def record_changed_files(pr_event, test_name):
    pr_processor = PrProcessor(pr_event)
    resp = pr_processor.process_changes()
    changed_files = pr_processor.get_changed_files()
    out_filename = Mockable.get_test_filename_from_test_name(
        test_name, CHANGED_FILES_FILENAME)
    write_json(changed_files, out_filename)
    print('Wrote changed files to %s' % out_filename)


if __name__ == '__main__':
    record_start_bot_eval()
