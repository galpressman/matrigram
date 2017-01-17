import json
import os
import requests

HELP_MSG = 'matrigram: A bridge between matrix and telegram'


def pprint_json(to_print):
    """Pretty print json.

    Args:
        to_print (json): The json to be printed.

    Returns:
        str: Pretty printed json string.
    """
    return json.dumps(to_print, sort_keys=True, indent=4)


def get_config(config_name):
    """Query config file.

    Args:
        config_name (str): The name of the config file.

    Returns:
        dict: The config dictionary.
    """
    config_path = os.path.join(os.path.dirname(__file__), '..', config_name)
    with open(config_path) as config_file:
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
