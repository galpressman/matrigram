import argparse
import logging
import os
import tempfile

from matrigram import helper
from matrigram.bot import MatrigramBot


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s'
                        '%(module)s@%(funcName)s +%(lineno)d: %(message)s',
                        datefmt='%H:%M:%S')
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description=helper.HELP_MSG)
    parser.add_argument('--config', default='config.json', help='path to config file')
    args = parser.parse_args()

    config = helper.get_config(args.config)
    media_dir = os.path.join(tempfile.gettempdir(), "matrigram")
    if not os.path.exists(media_dir):
        logging.debug('creating dir %s', media_dir)
        os.mkdir(media_dir)

    config['media_dir'] = media_dir
    token = config['telegram_token']

    mg = MatrigramBot(token, config=config)
    mg.message_loop(run_forever='-I- matrigram running...')


if __name__ == '__main__':
    main()
