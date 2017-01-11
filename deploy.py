import logging
import logging.handlers
import os
import tempfile

from flask import Flask
from matrigram.bot import MatrigramBot

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def matrigram():
    return 'matrigram'


def main():
    logger = logging.getLogger('matrigram')
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s '
                                      '%(module)s@%(funcName)s +%(lineno)d: %(message)s',
                                  datefmt='%H:%M:%S')
    sh = logging.StreamHandler()
    fh = logging.handlers.RotatingFileHandler('matrigram.log', maxBytes=10000, backupCount=1)
    sh.setFormatter(formatter)
    fh.setFormatter(formatter)
    logger.addHandler(sh)
    logger.addHandler(fh)

    config = {
        'telegram_token': os.environ['TG_TOKEN'],
        'server': os.environ['M_SERVER'],
    }
    media_dir = os.path.join(tempfile.gettempdir(), "matrigram")
    if not os.path.exists(media_dir):
        logging.debug('creating dir %s', media_dir)
        os.mkdir(media_dir)

    config['media_dir'] = media_dir
    token = config['telegram_token']

    mg = MatrigramBot(token, config=config)
    mg.message_loop(run_forever=False)


main()
