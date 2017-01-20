import logging
import logging.handlers
import os
import tempfile

from matrigram import helper
from matrigram.bot import MatrigramBot


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

    if not os.path.isfile(helper.CONFIG_PATH):
        logger.error('Please fill the config file at %s', helper.CONFIG_PATH)
        helper.init_config()
        return

    config = helper.get_config(helper.CONFIG_PATH)
    media_dir = os.path.join(tempfile.gettempdir(), "matrigram")
    if not os.path.exists(media_dir):
        logging.debug('creating dir %s', media_dir)
        os.mkdir(media_dir)

    config['media_dir'] = media_dir
    token = config['telegram_token']
    if not helper.token_changed(config):
        logger.error('Please enter you tg token in %s', helper.CONFIG_PATH)
        return

    mg = MatrigramBot(token, config=config)
    mg.message_loop(run_forever='-I- matrigram running...')


if __name__ == '__main__':
    main()
