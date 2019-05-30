from os.path import join

from botleague_helpers.config import get_test_name_from_callstack

from tests.test_constants import DATA_DIR
from util import read_file, get_str_or_json


class Mockable:
    test_name: str = None

    def __init__(self):
        self.test_name = get_test_name_from_callstack()

    def github_get(self, repo, filename):
        filepath = self.get_test_filename(filename)
        content_str = read_file(filepath)
        ret = get_str_or_json(content_str, filepath)
        return ret

    def get_test_filename(self, filename):
        return join(DATA_DIR, self.test_name, filename)
