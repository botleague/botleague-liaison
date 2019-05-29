import inspect
import os
from os.path import join

from tests.test_constants import DATA_DIR
from util import get_str_or_json, read_file


class Mockable:
    test_name: str

    def __init__(self):
        for level in inspect.stack():
            fn = level.function
            test_prefix = 'test_'
            if fn.startswith(test_prefix):
                self.test_name = fn[len(test_prefix):]
                break
        else:
            self.test_name = None

    def github_get(self, repo, filename):
        filepath = self.get_test_filename(filename)
        content_str = read_file(filepath)
        ret = get_str_or_json(content_str, filepath)
        return ret

    def get_test_filename(self, filename):
        return join(DATA_DIR, self.test_name, filename)