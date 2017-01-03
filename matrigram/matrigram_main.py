# -*- coding: utf-8 -*-

import argparse
import logging
import os
import re
import tempfile
import time
from threading import Lock
from threading import Thread

import requests
import telepot

from . import helper
from .helper import download_file
from .helper import pprint_json
from .mc import MC

BOT_BASE_URL = 'https://api.telegram.org/bot{token}/{path}'
BOT_FILE_URL = 'https://api.telegram.org/file/bot{token}/{file_path}'


def logged_in(func):
    def func_wrapper(self, msg, *args):
        from_id = msg['from']['id']
        client = self._get_client(from_id)
        if client is None:
            self.sendMessage(from_id,
                             'You are not logged in. Login to start with /login username password')
            return
        func(self, msg, *args)

    return func_wrapper


def focused(func):
    def func_wrapper(self, msg, *args):
        from_id = msg['from']['id']
        client = self._get_client(from_id)
        if not client.get_rooms_aliases():
            self.sendMessage(from_id, 'You are not in any room. Type /join #room to join one.')
            return
        if not client.have_focus_room():
            self.sendMessage(from_id, 'You don\'t have a room in focus. Type /focus to choose one.')
            return
        func(self, msg, *args)

    return func_wrapper


class Matrigram(telepot.Bot):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')

        super(Matrigram, self).__init__(*args, **kwargs)

        routes = [
            (r'^/login (?P<username>\S+) (?P<password>\S+)$', self.login),
            (r'^/logout$', self.logout),
            (r'^/join\s(?P<room_name>[^$]+)$', self.join_room),
            (r'^/leave$', self.leave_room),
            (r'^/get_rooms$', self.get_rooms),
            (r'^/discover$', self.discover_rooms),
            (r'^/focus$', self.change_focus_room),
            (r'^/status$', self.status),
            (r'^(?P<text>[^/].*)$', self.forward_message_to_mc),
        ]

        callback_query_routes = [
            (r'^LEAVE (?P<room>\S+)$', self.do_leave),
            (r'^FOCUS (?P<room>\S+)$', self.do_change_focus),
        ]

        self.routes = [(re.compile(pattern), callback) for pattern, callback in routes]
        self.callback_query_routes = [(re.compile(pattern), callback)
                                      for pattern, callback in callback_query_routes]

        self.content_type_routes = {
            'text': self.on_text_message,
            'photo': self.forward_photo_to_mc,
            'voice': self.forward_voice_to_mc,
            'video': self.forward_video_to_mc,
            'document': self.forward_gif_to_mc,
        }

        # users map telegram_id -> client
        self.users = {}
        self.config = config

        self.users_lock = Lock()  # self.users lock for typing related matters

    def on_chat_message(self, msg):
        content_type, _, _ = telepot.glance(msg)
        logging.debug('content type: %s', content_type)
        self.content_type_routes[content_type](msg)

    def on_callback_query(self, msg):
        data = msg['data']

        for route, callback in self.callback_query_routes:
            match = route.match(data)
            if match:
                callback_thread = Thread(target=callback, args=(msg, match))
                callback_thread.start()
                break

    def on_text_message(self, msg):
        text = msg['text'].encode('utf-8')

        for route, callback in self.routes:
            match = route.match(text)
            if match:
                callback_thread = Thread(target=callback, args=(msg, match))
                callback_thread.start()

                # wait for login thread to finish before moving on
                if callback == self.login:
                    callback_thread.join()
                break

    def login(self, msg, match):
        username = match.group('username')
        password = match.group('password')
        from_id = msg['from']['id']

        logging.info('telegram user %s, login to %s', from_id, username)
        self.sendChatAction(from_id, 'typing')

        client = MC(self.config['server'], self, username)
        login_bool, login_message = client.login(username, password)
        if login_bool:
            self.sendMessage(from_id, 'Logged in as {}'.format(username))

            self.users[from_id] = {
                'client': client,
                'typing_thread': None,
                'should_type': False,
            }

            rooms = client.get_rooms_aliases()
            logging.debug("rooms are: %s", rooms)

            if rooms:
                room_aliases = '\n'.join([room_alias[0] for room_alias in rooms.values()])
                self.sendMessage(from_id, 'You are currently in rooms:\n{}'.format(room_aliases))
                self.sendMessage(from_id,
                                 'You are now participating in: {}'.format(
                                     client.get_focus_room_alias()))
            logging.debug('%s user state:\n%s', from_id, self.users[from_id])
        else:
            self.sendMessage(from_id, login_message)

    @logged_in
    def logout(self, msg, _):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        logging.info('logout %s', from_id)

        client.logout()
        self.users[from_id]['client'] = None

    @logged_in
    def join_room(self, msg, match):
        from_id = msg['from']['id']
        client = self._get_client(from_id)
        room_name = match.group('room_name')
        ret = client.join_room(room_name)
        if not ret:
            self.sendMessage(from_id, 'Can\'t join room')
        else:
            self.sendMessage(from_id, "Joined {}".format(room_name))

    @logged_in
    def leave_room(self, msg, _):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        rooms = [room[0] for _, room in client.get_rooms_aliases().iteritems()]
        if not rooms:
            self.sendMessage(from_id, 'Nothing to leave...')
            return

        keyboard = {
            'inline_keyboard': [[{'text': room,
                                  'callback_data': 'LEAVE {}'.format(room)} for room in rooms]]
        }
        self.sendMessage(from_id, 'Choose a room to leave:', reply_markup=keyboard)

    @logged_in
    def do_leave(self, msg, match):
        query_id, from_id, _ = telepot.glance(msg, flavor='callback_query')
        room_name = match.group('room')

        client = self._get_client(from_id)
        client.leave_room(room_name)
        self.answerCallbackQuery(query_id, 'Done!')

    @logged_in
    def change_focus_room(self, msg, _):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        rooms = [room[0] for _, room in client.get_rooms_aliases().iteritems()]
        if not rooms or len(rooms) == 0:
            self.sendMessage(from_id, 'You need to be at least in one room to use this command.')
            return

        keyboard = {
            'inline_keyboard': [[{'text': room,
                                  'callback_data': 'FOCUS {}'.format(room)} for room in rooms]]
        }
        self.sendMessage(from_id, 'Choose a room to focus:', reply_markup=keyboard)

    @logged_in
    def do_change_focus(self, msg, match):
        query_id, from_id, _ = telepot.glance(msg, flavor='callback_query')
        room_name = match.group('room')

        self.sendChatAction(from_id, 'typing')
        client = self._get_client(from_id)
        client.set_focus_room(room_name)
        self.answerCallbackQuery(query_id, 'Done!')
        self.sendMessage(from_id, 'You are now participating in {}'.format(room_name))

    @logged_in
    def status(self, msg, _):
        from_id = msg['from']['id']
        self.sendChatAction(from_id, 'typing')
        client = self._get_client(from_id)

        focus_room = client.get_focus_room_alias()
        joined_rooms = client.get_rooms_aliases()
        joined_rooms_list = [val[0] for _, val in joined_rooms.items()]

        message = '''Status:
        Focused room: {}
        Joined rooms: {}'''.format(focus_room, helper.list_to_nice_str(joined_rooms_list))
        self.sendMessage(from_id, message)

    @logged_in
    def get_rooms(self, msg, _):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        rooms = client.get_rooms_aliases()
        to_send = [room[0] for _, room in rooms.iteritems()]
        self.sendMessage(from_id, to_send)

    @logged_in
    def discover_rooms(self, msg, _):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        rooms = client.discover_rooms()
        self.sendMessage(from_id, rooms)

    @logged_in
    @focused
    def forward_message_to_mc(self, msg, match):
        text = match.group('text')
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        client.send_message(text)

    @logged_in
    @focused
    def forward_photo_to_mc(self, msg):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        logging.debug(pprint_json(msg))
        file_id = msg['photo'][-1]['file_id']
        file_obj = self.getFile(file_id)
        file_path = file_obj['file_path']
        file_name = os.path.split(file_path)[1]

        link = BOT_FILE_URL.format(token=self._token, file_path=file_path)
        download_file(link, os.path.join(self.config['media_dir'], file_name))

        client.send_photo(os.path.join(self.config['media_dir'], file_name))

    @logged_in
    @focused
    def forward_voice_to_mc(self, msg):
        from_id = msg['from']['id']
        client = self._get_client(from_id)

        file_id = msg['voice']['file_id']
        file = self.getFile(file_id)
        file_path = file['file_path']
        file_name = os.path.split(file_path)[1]

        link = BOT_FILE_URL.format(token=self._token, file_path=file_path)
        path = os.path.join(self.config['media_dir'], file_name)
        download_file(link, path)

        client.send_voice(path)

    @logged_in
    @focused
    def forward_video_to_mc(self, msg):
        from_id = msg['from']['id']

        client = self._get_client(from_id)

        file_id = msg['video']['file_id']
        file = self.getFile(file_id)
        file_path = file['file_path']
        file_name = os.path.split(file_path)[1]

        link = BOT_FILE_URL.format(token=self._token, file_path=file_path)
        path = os.path.join(self.config['media_dir'], file_name)
        download_file(link, path)

        client.send_video(path)

    # gifs are mp4 in telegram
    @logged_in
    @focused
    def forward_gif_to_mc(self, msg):
        from_id = msg['from']['id']

        client = self._get_client(from_id)

        file_id = msg['document']['file_id']
        file = self.getFile(file_id)
        file_path = file['file_path']
        file_name = os.path.split(file_path)[1]
        link = BOT_FILE_URL.format(token=self._token, file_path=file_path)
        path = os.path.join(self.config['media_dir'], file_name)
        download_file(link, path)

        client.send_video(path)

    def send_message(self, sender, msg, client):
        from_id = self._get_from_id(client)
        if not from_id:
            return

        self.sendChatAction(from_id, 'typing')
        self.sendMessage(from_id, "{}: {}".format(sender, msg))

    def send_topic(self, sender, topic, client):
        from_id = self._get_from_id(client)
        if not from_id:
            return

        self.sendChatAction(from_id, 'typing')
        self.sendMessage(from_id, "{} changed topic to: \"{}\"".format(sender, topic))

    # temporary fixes are permanent, lets do it the hard way
    def _workaround_sendPhoto(self, path, from_id):
        payload = {
            'chat_id': from_id
        }

        files = {
            'photo': open(path, 'rb')
        }

        base_url = BOT_BASE_URL.format(token=self._token, path='sendPhoto')
        requests.post(base_url, params=payload, files=files)

    def _workaround_sendAudio(self, path, from_id):
        payload = {
            'chat_id': from_id
        }

        files = {
            'audio': open(path, 'rb')
        }

        base_url = BOT_BASE_URL.format(token=self._token, path='sendAudio')
        requests.post(base_url, params=payload, files=files)

    def _workaround_sendVideo(self, path, from_id):
        payload = {
            'chat_id': from_id
        }

        files = {
            'video': open(path, 'rb')
        }

        base_url = BOT_BASE_URL.format(token=self._token, path='sendVideo')
        requests.post(base_url, params=payload, files=files)

    def send_photo(self, path, client):
        logging.info('path = %s', path)
        from_id = self._get_from_id(client)
        if not from_id:
            return

        self.sendChatAction(from_id, 'upload_photo')
        self._workaround_sendPhoto(path, from_id)
        # self.sendPhoto(from_id, open(path, 'rb'))

    def send_voice(self, path, client):
        logging.info('path = %s', path)
        from_id = self._get_from_id(client)
        if not from_id:
            return

        self.sendChatAction(from_id, 'upload_audio')
        self._workaround_sendAudio(path, from_id)

    def send_video(self, path, client):
        logging.info('path = %s', path)
        from_id = self._get_from_id(client)
        if not from_id:
            return

        self.sendChatAction(from_id, 'upload_video')
        self._workaround_sendVideo(path, from_id)

    def relay_typing(self, from_id):
        while True:
            with self.users_lock:
                if not self.users[from_id]['should_type']:
                    return
            self.sendChatAction(from_id, 'typing')
            time.sleep(2)

    def start_typing_thread(self, client):
        from_id = self._get_from_id(client)

        with self.users_lock:
            if self.users[from_id]['typing_thread']:
                return

            typing_thread = Thread(target=self.relay_typing, args=(from_id,))
            self.users[from_id]['should_type'] = True
            typing_thread.start()
            self.users[from_id]['typing_thread'] = typing_thread

    def stop_typing_thread(self, client):
        from_id = self._get_from_id(client)

        with self.users_lock:
            if not self.users[from_id]['typing_thread']:
                return

            typing_thread = self.users[from_id]['typing_thread']
            self.users[from_id]['should_type'] = False
        typing_thread.join()

        with self.users_lock:
            self.users[from_id]['typing_thread'] = None

    def _get_client(self, from_id):
        try:
            return self.users[from_id]['client']
        except KeyError:
            return None

    def _get_from_id(self, client):
        for from_id, user in self.users.items():
            if user['client'] == client:
                return from_id

        logging.error('client without user?')
        return None


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

    mg = Matrigram(token, config=config)
    mg.message_loop(run_forever='-I- matrigram running...')
