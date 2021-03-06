import sys

from tests import test
from logs import log

from botleague_helpers.config import activate_test_mode

"""
Used for local debugging of tests. Use pytest otherwise.
"""


def run_all(test_module):
    log.info('Running all tests')
    num = 0
    for attr in dir(test_module):
        if attr.startswith('test_'):
            num += 1
            log.info('Running ' + attr)
            getattr(test_module, attr)()
            log.success(f'Test: {attr} ran successfully')
    return num

@log.catch(reraise=True)
def main():
    test_module = test
    if len(sys.argv) > 1:
        test_case = sys.argv[1]
        log.info('Running ' + test_case)
        getattr(test_module, test_case)()
        num = 1
        log.success(f'{test_case} ran successfully!')
    else:
        num = run_all(test_module)
    log.success(f'{num} tests ran successfully!')


if __name__ == '__main__':
    main()
