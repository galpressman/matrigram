# -*- coding: utf-8 -*-

import logging
import os
import re
import time
from threading import Lock
from threading import Thread

import requests
import telepot

from . import helper
from .helper import download_file
from .helper import pprint_json
from .client import MatrigramClient

BOT_BASE_URL = 'https://api.telegram.org/bot{token}/{path}'
BOT_FILE_URL = 'https://api.telegram.org/file/bot{token}/{file_path}'
logger = logging.getLogger('matrigram')

OPTS_IN_ROW = 4


def logged_in(func):
    def func_wrapper(self, msg, *args):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)
        if client is None:
            self.sendMessage(chat_id,
                             'You are not logged in. Login to start with /login username password')
            return
        func(self, msg, *args)

    return func_wrapper


def focused(func):
    def func_wrapper(self, msg, *args):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)
        if not client.get_rooms_aliases():
            self.sendMessage(chat_id, 'You are not in any room. Type /join #room to join one.')
            return
        if not client.have_focus_room():
            self.sendMessage(chat_id, 'You don\'t have a room in focus. Type /focus to choose one.')
            return
        func(self, msg, *args)

    return func_wrapper


class MatrigramBot(telepot.Bot):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')

        super(MatrigramBot, self).__init__(*args, **kwargs)

        routes = [
            (r'^/login (?P<username>\S+) (?P<password>\S+)$', self.login),
            (r'^/logout$', self.logout),
            (r'^/join\s(?P<room_name>[^$]+)$', self.join_room),
            (r'^/leave$', self.leave_room),
            (r'^/discover$', self.discover_rooms),
            (r'^/focus$', self.change_focus_room),
            (r'^/status$', self.status),
            (r'^/members$', self.get_members),
            (r'^/create_room (?P<room_name>[\S]+)(?P<invitees>\s.*\S)*$', self.create_room),
            (r'^/setname\s(?P<matrix_name>[^$]+)$', self.set_name),
            (r'^(?P<text>[^/].*)$', self.forward_message_to_mc),
        ]

        callback_query_routes = [
            (r'^LEAVE (?P<room>\S+)$', self.do_leave),
            (r'^FOCUS (?P<room>\S+)$', self.do_change_focus),
            (r'^JOIN (?P<room>\S+)$', self.do_join),
            (r'^NOP$', self.do_nop),
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
        """Main entry point.

        This function is our main entry point to the bot.
        Messages will be routed according to their content type.

        Args:
            msg: The message object received from telegram user.
        """
        content_type, _, _ = telepot.glance(msg)
        logger.debug('content type: %s', content_type)
        self.content_type_routes[content_type](msg)

    def on_callback_query(self, msg):
        """Handle callback queries.

        Route queries using ``self.callback_query_routes``.

        Args:
            msg: The message object received from telegram user.
        """
        data = msg['data']

        for route, callback in self.callback_query_routes:
            match = route.match(data)
            if match:
                callback_thread = Thread(target=callback, args=(msg, match))
                callback_thread.start()
                break

    def on_text_message(self, msg):
        """Handle text messages.

        Route text messages using ``self.routes``.

        Args:
            msg: The message object received from telegram user.
        """
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
        """Perform login.

        Args:
            msg: The message object received from telegram user.
            match: Match object containing extracted data.
        """
        username = match.group('username')
        password = match.group('password')
        chat_id = msg['chat']['id']

        logger.info('telegram user %s, login to %s', chat_id, username)
        self.sendChatAction(chat_id, 'typing')

        client = MatrigramClient(self.config['server'], self, username)
        login_bool, login_message = client.login(username, password)
        if login_bool:
            self.sendMessage(chat_id, 'Logged in as {}'.format(username))

            self.users[chat_id] = {
                'client': client,
                'typing_thread': None,
                'should_type': False,
            }

            rooms = client.get_rooms_aliases()
            logger.debug("rooms are: %s", rooms)

            if rooms:
                room_aliases = '\n'.join([room_alias[0] for room_alias in rooms.values()])
                self.sendMessage(chat_id, 'You are currently in rooms:\n{}'.format(room_aliases))
                self.sendMessage(chat_id,
                                 'You are now participating in: {}'.format(
                                     client.get_focus_room_alias()))
            logger.debug('%s user state:\n%s', chat_id, self.users[chat_id])
        else:
            self.sendMessage(chat_id, login_message)

    @logged_in
    def logout(self, msg, _):
        """Perform logout.

        Args:
            msg: The message object received from telegram user.
        """
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

        logger.info('logout %s', chat_id)

        client.logout()
        self.users[chat_id]['client'] = None

    @logged_in
    def join_room(self, msg, match):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)
        room_name = match.group('room_name')
        ret = client.join_room(room_name)
        if not ret:
            self.sendMessage(chat_id, 'Can\'t join room')
        else:
            self.sendMessage(chat_id, "Joined {}".format(room_name))

    @logged_in
    def leave_room(self, msg, _):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

        rooms = [room[0] for dummy_room_id, room in client.get_rooms_aliases().items()]
        if not rooms:
            self.sendMessage(chat_id, 'Nothing to leave...')
            return

        opts = [{'text': room, 'callback_data': 'LEAVE {}'.format(room)} for room in rooms]

        keyboard = {
            'inline_keyboard': [chunk for chunk in helper.chunks(opts, OPTS_IN_ROW)]
        }
        self.sendMessage(chat_id, 'Choose a room to leave:', reply_markup=keyboard)

    def do_leave(self, msg, match):
        query_id, _, _ = telepot.glance(msg, flavor='callback_query')
        chat_id = msg['message']['chat']['id']
        room_name = match.group('room')
        client = self._get_client(chat_id)

        prev_focus_room = client.get_focus_room_alias()
        client.leave_room(room_name)
        self.sendMessage(chat_id, 'Left {}'.format(room_name))
        curr_focus_room = client.get_focus_room_alias()

        if curr_focus_room != prev_focus_room and curr_focus_room is not None:
            self.sendMessage(chat_id,
                             'You are now participating in: {}'.format(
                                 client.get_focus_room_alias()))

        self.answerCallbackQuery(query_id, 'Done!')

    @logged_in
    def change_focus_room(self, msg, _):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

        rooms = [room[0] for dummy_room_id, room in client.get_rooms_aliases().items()]
        if not rooms or len(rooms) == 0:
            self.sendMessage(chat_id, 'You need to be at least in one room to use this command.')
            return

        opts = [{'text': room, 'callback_data': 'FOCUS {}'.format(room)} for room in rooms]

        keyboard = {
            'inline_keyboard': [chunk for chunk in helper.chunks(opts, OPTS_IN_ROW)]
        }
        self.sendMessage(chat_id, 'Choose a room to focus:', reply_markup=keyboard)

    def do_change_focus(self, msg, match):
        query_id, _, _ = telepot.glance(msg, flavor='callback_query')
        chat_id = msg['message']['chat']['id']
        room_name = match.group('room')

        self.sendChatAction(chat_id, 'typing')
        client = self._get_client(chat_id)

        client.set_focus_room(room_name)
        self.sendMessage(chat_id, 'You are now participating in {}'.format(room_name))
        self.sendMessage(chat_id, '{} Room history:'.format(room_name))
        client.backfill_previous_messages()

        self.answerCallbackQuery(query_id, 'Done!')

    def do_join(self, msg, match):
        query_id, _, _ = telepot.glance(msg, flavor='callback_query')
        chat_id = msg['message']['chat']['id']
        room_name = match.group('room')

        self.sendChatAction(chat_id, 'typing')
        client = self._get_client(chat_id)

        ret = client.join_room(room_name)
        if not ret:
            self.answerCallbackQuery(query_id, 'Can\'t join room')
        else:
            self.answerCallbackQuery(query_id, 'Joined {}'.format(room_name))

    def do_nop(self, msg, _):
        query_id, _, _ = telepot.glance(msg, flavor='callback_query')
        chat_id = msg['message']['chat']['id']

        self.sendChatAction(chat_id, 'typing')
        self.answerCallbackQuery(query_id, 'OK Boss!')

    @logged_in
    def status(self, msg, _):
        chat_id = msg['chat']['id']
        self.sendChatAction(chat_id, 'typing')
        client = self._get_client(chat_id)

        focus_room = client.get_focus_room_alias()
        joined_rooms = client.get_rooms_aliases()
        joined_rooms_list = [val[0] for dummy_room_id, val in joined_rooms.items()]

        message = '''Status:
        Focused room: {}
        Joined rooms: {}'''.format(focus_room, helper.list_to_nice_str(joined_rooms_list))
        self.sendMessage(chat_id, message)

    @logged_in
    @focused
    def get_members(self, msg, _):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

        l = client.get_members()
        # TODO: we need to think how we avoid too long messages, for now send 10 elements
        self.sendMessage(chat_id, helper.list_to_nice_str(l[0:10]))

    @logged_in
    def discover_rooms(self, msg, _):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

        rooms = client.discover_rooms()
        self.sendMessage(chat_id, helper.list_to_nice_lines(rooms))

    @logged_in
    def create_room(self, msg, match):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)
        room_alias = match.group('room_name')
        invitees = match.group('invitees')

        invitees = invitees.split() if invitees else None
        room_id, actual_alias = client.create_room(room_alias, is_public=True, invitees=invitees)
        if room_id:
            self.sendMessage(chat_id,
                             'Created room {} with room id {}'.format(actual_alias, room_id))
            self.sendMessage(chat_id,
                             'Invitees for the rooms are {}'.format(
                                 helper.list_to_nice_str(invitees)))
        else:
            self.sendMessage(chat_id, 'Could not create room')

    @logged_in
    @focused
    def forward_message_to_mc(self, msg, match):
        text = match.group('text')
        chat_id = msg['chat']['id']
        from_user = msg['from'].get('username')

        if from_user and chat_id < 0:
            text = '{}: {}'.format(from_user, text)
        client = self._get_client(chat_id)

        client.send_message(text)

    @logged_in
    @focused
    def forward_photo_to_mc(self, msg):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

        logger.debug(pprint_json(msg))
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
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)

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
        chat_id = msg['chat']['id']

        client = self._get_client(chat_id)

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
        chat_id = msg['chat']['id']

        client = self._get_client(chat_id)

        file_id = msg['document']['file_id']
        file = self.getFile(file_id)
        file_path = file['file_path']
        file_name = os.path.split(file_path)[1]
        link = BOT_FILE_URL.format(token=self._token, file_path=file_path)
        path = os.path.join(self.config['media_dir'], file_name)
        download_file(link, path)

        client.send_video(path)

    def send_message(self, sender, msg, client):
        """Send message to telegram user.

        Args:
            sender (str): Name of the sender.
            msg (str): Text message.
            client (MatrigramClient): The client the message is originated in.

        Returns:

        """
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        self.sendChatAction(chat_id, 'typing')
        self.sendMessage(chat_id, "{}: {}".format(sender, msg))

    def send_topic(self, sender, topic, client):
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        self.sendChatAction(chat_id, 'typing')
        self.sendMessage(chat_id, "{} changed topic to: \"{}\"".format(sender, topic))

    def send_kick(self, room, client):
        logger.info('got kicked from %s', room)
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        self.sendMessage(chat_id, 'You got kicked from {}'.format(room))
        client.set_focus_room(None)

    @logged_in
    def set_name(self, msg, match):
        chat_id = msg['chat']['id']
        client = self._get_client(chat_id)
        name = match.group('matrix_name')
        client.set_name(name)
        self.sendMessage(chat_id, 'Set matrix display name to: {}'.format(name))

    def send_invite(self, client, room):
        logger.info('join room %s?', room)
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        keyboard = {
            'inline_keyboard': [
                [
                    {
                        'text': 'Yes',
                        'callback_data': 'JOIN {}'.format(room),
                    },
                    {
                        'text': 'No',
                        'callback_data': 'NOP',
                    }
                ]
            ]
        }

        self.sendMessage(chat_id, 'You have been invited to room {}, accept?'.format(room),
                         reply_markup=keyboard)

    # temporary fixes are permanent, lets do it the hard way
    def _workaround_sendPhoto(self, path, chat_id):
        payload = {
            'chat_id': chat_id
        }

        files = {
            'photo': open(path, 'rb')
        }

        base_url = BOT_BASE_URL.format(token=self._token, path='sendPhoto')
        requests.post(base_url, params=payload, files=files)

    def _workaround_sendAudio(self, path, chat_id):
        payload = {
            'chat_id': chat_id
        }

        files = {
            'audio': open(path, 'rb')
        }

        base_url = BOT_BASE_URL.format(token=self._token, path='sendAudio')
        requests.post(base_url, params=payload, files=files)

    def _workaround_sendVideo(self, path, chat_id):
        payload = {
            'chat_id': chat_id
        }

        files = {
            'video': open(path, 'rb')
        }

        base_url = BOT_BASE_URL.format(token=self._token, path='sendVideo')
        requests.post(base_url, params=payload, files=files)

    def send_photo(self, path, client):
        logger.info('path = %s', path)
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        self.sendChatAction(chat_id, 'upload_photo')
        self._workaround_sendPhoto(path, chat_id)
        # self.sendPhoto(chat_id, open(path, 'rb'))

    def send_voice(self, path, client):
        logger.info('path = %s', path)
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        self.sendChatAction(chat_id, 'upload_audio')
        self._workaround_sendAudio(path, chat_id)

    def send_video(self, path, client):
        logger.info('path = %s', path)
        chat_id = self._get_chat_id(client)
        if not chat_id:
            return

        self.sendChatAction(chat_id, 'upload_video')
        self._workaround_sendVideo(path, chat_id)

    def relay_typing(self, chat_id):
        while True:
            with self.users_lock:
                if not self.users[chat_id]['should_type']:
                    return
            self.sendChatAction(chat_id, 'typing')
            time.sleep(2)

    def start_typing_thread(self, client):
        chat_id = self._get_chat_id(client)

        with self.users_lock:
            if self.users[chat_id]['typing_thread']:
                return

            typing_thread = Thread(target=self.relay_typing, args=(chat_id,))
            self.users[chat_id]['should_type'] = True
            typing_thread.start()
            self.users[chat_id]['typing_thread'] = typing_thread

    def stop_typing_thread(self, client):
        chat_id = self._get_chat_id(client)

        with self.users_lock:
            if not self.users[chat_id]['typing_thread']:
                return

            typing_thread = self.users[chat_id]['typing_thread']
            self.users[chat_id]['should_type'] = False
        typing_thread.join()

        with self.users_lock:
            self.users[chat_id]['typing_thread'] = None

    def _get_client(self, chat_id):
        """Get matrigram client.

        Args:
            chat_id: Telegram user id.

        Returns:
            MatrigramClient: The client associated to the telegram user with `chat_id`.
        """
        try:
            return self.users[chat_id]['client']
        except KeyError:
            logger.error('chat_id doesnt exist?')
            return None

    def _get_chat_id(self, client):
        """Get telegram id associated with client.

        Args:
            client (MatrigramClient): The client to be queried.

        Returns:
            str: The `chat_id` associated to the client.
        """
        for chat_id, user in self.users.items():
            if user['client'] == client:
                return chat_id

        logger.error('client without user?')
        return None
