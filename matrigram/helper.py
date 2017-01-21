import hashlib
import json
import os
import shutil

import requests

HELP_MSG = 'matrigram: A bridge between matrix and telegram'
CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.matrigramconfig')


def pprint_json(to_print):
    """Pretty print json.

    Args:
        to_print (json): The json to be printed.

    Returns:
        str: Pretty printed json string.
    """
    return json.dumps(to_print, sort_keys=True, indent=4)


def get_config():
    """Query config file.

    Returns:
        dict: The config dictionary.
    """
    with open(CONFIG_PATH) as config_file:
        return json.load(config_file)


def download_file(url, path):
    """Download a file from the net.

    Args:
        url (str): Link to the file.
        path (str): Where to save.
    """
    res = requests.get(url)
    with open(path, 'wb') as f:
        f.write(res.content)


def list_to_nice_str(l):
    """Convert a string list to a ready to print string.

    Args:
        l (list): List of strings to be printed

    Returns:
        str: A string that can be printed.
    """
    return ', '.join(l)


def chunks(l, n):
    """Yield successive n-sized chunks from l.

    Args:
        l (list): List to be split.
        n (int): Size of chunk.
    """
    for i in range(0, len(l), n):
        yield l[i:i + n]


def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def init_config():
    """Init ~/.matrigramconfig.

    """
    shutil.copyfile('config.json.example', CONFIG_PATH)


def config_filled():
    """Check if the user filled the config file.

    Returns:
        bool: True if config is filled, else False.
    """
    orig_md5 = md5('config.json.example')
    config_md5 = md5(CONFIG_PATH)

    return orig_md5 != config_md5
