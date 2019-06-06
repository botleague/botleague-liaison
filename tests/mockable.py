from os.path import join

from botleague_helpers.config import get_test_name_from_callstack
from box import Box

from tests.test_constants import DATA_DIR, TEST_DIR, PR_EVENT_FILENAME
from utils import read_file, get_str_or_box, read_json


class Mockable:
    test_name: str = ''

    def __init__(self):
        self.test_name = get_test_name_from_callstack()
        self.is_mock = True

    def get_test_filename(self, filename):
        return self.get_test_filename_from_test_name(self.test_name, filename)

    def get_pr_event(self):
        return self.get_pr_event_from_test_name(self.test_name)

    @classmethod
    def read_test_box(cls, relative_path):
        test_name = get_test_name_from_callstack()
        file_path = cls.get_test_filename_from_test_name(test_name,
                                                         relative_path)
        ret = Box.from_json(filename=file_path)
        return ret

    @staticmethod
    def get_test_filename_from_test_name(test_name, filename):
        return join(DATA_DIR, test_name, filename)

    @staticmethod
    def get_pr_event_from_test_name(test_name):
        return Box(read_json(join(DATA_DIR, test_name,
                             PR_EVENT_FILENAME)))
