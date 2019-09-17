import json
import os
import os.path as p

from botleague_helpers.config import blconfig
from botleague_helpers.db import DB, get_db
from box import Box

import constants as c

from loguru import logger as log

from github import UnknownObjectException


def get_file_from_github(repo, filename, ref=None):
    """@:param filename: relative path to file in repo"""
    try:
        args = [filename]
        if ref is not None:
            args.append(ref)
        contents = repo.get_contents(*args)
        content_str = contents.decoded_content.decode('utf-8')
    except UnknownObjectException:
        log.error('Unable to find %s in %s', filename, repo.html_url)
        content_str = ''
    ret = get_str_or_box(content_str, filename)
    return ret


def get_str_or_box(content_str, filename):
    if filename.endswith('.json') and content_str:
        ret = Box(json.loads(content_str))
    else:
        ret = content_str
    return ret


def read_box(json_filename) -> Box:
    ret = Box().from_json(filename=json_filename)
    return ret

def write_json(obj, path):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=2)


def read_json(filename):
    with open(filename) as file:
        results = json.load(file)
    return results


def write_file(content, path):
    with open(path, 'w') as f:
        f.write(content)


def read_file(path):
    with open(path) as f:
        ret = f.read()
    return ret


def read_lines(path):
    content = read_file(path)
    lines = content.split()
    return lines


def append_file(path, strings):
    with open(path, 'a') as f:
        f.write('\n'.join(strings) + '\n')


def exists_and_unempty(problem_filename):
    return p.exists(problem_filename) and os.stat(problem_filename).st_size != 0


def is_docker():
    path = '/proc/self/cgroup'
    return (
        os.path.exists('/.dockerenv') or
        os.path.isfile(path) and any('docker' in line for line in open(path))
    )


def generate_rand_alphanumeric(num_chars):
    from secrets import choice
    import string
    alphabet = string.ascii_uppercase + string.digits
    ret = ''.join(choice(alphabet) for _ in range(num_chars))
    return ret


def trigger_leaderboard_generation():
    db = get_db(collection_name=blconfig.botleague_collection_name)
    db.set(blconfig.should_gen_key, True)


def get_liaison_db_store():
    ret = get_db(collection_name='botleague_liaison')
    return ret


def dbox(obj=None, **kwargs):
    if kwargs:
        obj = dict(kwargs)
    else:
        obj = obj or {}
    return Box(obj, default_box=True)


def is_json(string: str):
    try:
        json.loads(string)
    except ValueError:
        return False
    return True


def box2json(box: Box):
    return box.to_json(indent=2, default=str)

# if __name__ == '__main__':
#     trigger_leaderboard_generation()
