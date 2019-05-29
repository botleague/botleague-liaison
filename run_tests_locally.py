import sys

from tests import test

"""
Used for local debugging of tests. Use pytest otherwise.
"""


def test_all():
    print('running all tests')
    for attr in dir(test):
        if attr.startswith('test_'):
            print('running ' + attr)
            getattr(test, attr)()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        test_case = sys.argv[1]
        getattr(test, test_case)()
    else:
        test_all()
