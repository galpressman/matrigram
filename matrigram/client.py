# -*- coding: utf-8 -*-

import logging
import mimetypes
import os
import re

import requests
from matrix_client.client import MatrixClient
from matrix_client.client import MatrixRequestError
from requests import ConnectionError

from .helper import download_file
from .helper import pprint_json

logger = logging.getLogger('matrigram')


class MatrigramClient(object):
    def __init__(self, server, tb, username):
        self.client = MatrixClient(server)
        self.tb = tb
        self.token = None
        self.server = server
        self.username = username
        self.focus_room_id = None
        self.msg_type_router = {
            'm.image': self.forward_image_to_tb,
            'm.audio': self.forward_voice_to_tb,
            'm.video': self.forward_video_to_tb,
        }

    def login(self, username, password):
        try:
            self.token = self.client.login_with_password(username, password)
            logger.info('token = %s', self.token)
            rooms = self.get_rooms_aliases()
            if rooms:
                # set focus room to "first" room
                self.set_focus_room(rooms.keys()[0])

            self.client.add_invite_listener(self.on_invite_event)
            self.client.add_leave_listener(self.on_leave_event)
            self.client.start_listener_thread()
            return True, "OK"
        except MatrixRequestError:
            return False, "Failed to login"
        except ConnectionError:
            return False, "Server is offline"

    def logout(self):
        self.client.logout()

    def on_event(self, _, event):
        logger.debug('entered with message %s', pprint_json(event))
        sender = event['sender'].split(':')[0].encode('utf-8')

        # Prevent messages loopback
        if sender.startswith(u'@{}'.format(self.username)):
            return

        if event['type'] == "m.room.message":
            msgtype = event['content']['msgtype']

            if msgtype != 'm.text':
                callback = self.msg_type_router.get(msgtype)
                if callback:
                    callback(event)
                return

            content = event['content']['body'].encode('utf-8')
            self.tb.send_message(sender, content, self)

        elif event['type'] == "m.room.topic":
            topic = event['content']['topic'].encode('utf-8')
            self.tb.send_topic(sender, topic, self)

    def on_ephemeral_event(self, _, ee):
        logger.debug(pprint_json(ee))

        if ee['type'] == 'm.typing':
            if ee['content']['user_ids']:
                self.tb.start_typing_thread(self)
            else:
                self.tb.stop_typing_thread(self)

    def on_leave_event(self, room_id, le):
        logger.debug(pprint_json(le))

        if le['timeline']['events'][0]['sender'] != le['timeline']['events'][0]['state_key']:
            self.tb.send_kick(self._room_id_to_alias(room_id), self)

    def on_invite_event(self, _, ie):
        logger.debug('invite event %s', pprint_json(ie))
        room_name = None
        for event in ie['events']:
            if event['type'] == 'm.room.name':
                room_name = event['content']['name']

        if room_name:
            self.tb.send_invite(self, self._room_id_to_alias(room_name))

    def join_room(self, room_id_or_alias):
        try:
            self.client.join_room(room_id_or_alias)
            self.set_focus_room(room_id_or_alias)
            return True
        except MatrixRequestError:
            return False

    def leave_room(self, room_id_or_alias):
        room = self.get_room_obj(room_id_or_alias)
        if not room:
            logger.error('cant find room')
            return False

        if self.focus_room_id == room.room_id:
            rooms = self.get_rooms_aliases()
            room_id = self._room_alias_to_id(room_id_or_alias)

            del rooms[room_id]
            new_focus_room = rooms.keys()[0] if rooms else None
            self.set_focus_room(new_focus_room)

        return room.leave()

    def set_focus_room(self, room_id_or_alias):
        if self._room_alias_to_id(room_id_or_alias) == self.focus_room_id:
            return

        # remove current focus room listeners
        if self.focus_room_id is not None:
            # tmp solution, maybe implement this in the SDK
            room_obj = self.get_room_obj(self.focus_room_id)
            for listener in room_obj.listeners:
                if listener['callback'] == self.on_event:
                    room_obj.listeners.remove(listener)
                    logger.debug('removed listener from room %s',
                                 self._room_id_to_alias(self.focus_room_id))
            for ephemeral_listener in room_obj.ephemeral_listeners:
                if ephemeral_listener['callback'] == self.on_ephemeral_event:
                    room_obj.ephemeral_listeners.remove(ephemeral_listener)
                    logger.debug('removed ephemeral listener from room %s',
                                 self._room_id_to_alias(self.focus_room_id))
            self.focus_room_id = None

        # set new room on focus
        if room_id_or_alias is not None:
            self.focus_room_id = self._room_alias_to_id(room_id_or_alias)
            room_obj = self.get_room_obj(self.focus_room_id)
            room_obj.add_listener(self.on_event)
            room_obj.add_ephemeral_listener(self.on_ephemeral_event)

        logger.debug("set focus room to %s", self.focus_room_id)

    def get_focus_room_alias(self):
        return self._room_id_to_alias(self.focus_room_id)

    def have_focus_room(self):
        return self.focus_room_id is not None

    def get_members(self):
        # workaround until sdk pull request is merged
        res = self.client.api._send("GET", "/rooms/{}/members".format(self.focus_room_id),
                                    api_path='/_matrix/client/r0')
        return [event["content"]["displayname"].encode('utf-8') for event in res["chunk"] if
                event["content"].get("displayname") and event["content"]["membership"] == "join"]

    def set_name(self, name):
        # maybe we should generate an event to catch the correct server address from the answer
        server = re.sub(r'https?://', '', self.server)
        user_id = '@{}:{}'.format(self.username, server)
        user = self.client.get_user(user_id)
        user.set_display_name(name)

    def create_room(self, alias, is_public=False, invitees=()):
        try:
            room_obj = self.client.create_room(alias, is_public, invitees)
            room_obj.update_aliases()
            logger.debug('room_id %s', room_obj.room_id)
            logger.debug('room_alias %s', room_obj.aliases[0])
            return (room_obj.room_id, room_obj.aliases[0])
        except MatrixRequestError:
            logger.error('error creating room')
            return None, None

    def backfill_previous_messages(self, limit=10):
        room_obj = self.get_room_obj(self.focus_room_id)
        room_obj.backfill_previous_messages(limit=limit)

    def get_rooms_aliases(self):
        # returns a dict with id: room obj
        rooms = self._get_rooms_updated()
        if not rooms:
            return rooms

        logger.debug("rooms got from server are %s", rooms)

        # return dict with id: list of aliases or id (if no alias exists)
        return {key: val.aliases if val.aliases else [key] for (key, val) in rooms.items()}

    def get_room_obj(self, room_id_or_alias):
        """Get room object of specific id or alias.

        Args:
            room_id_or_alias (str): Room's id or alias.

        Returns (Room): Room object corresponding to room_id_or_alias.

        """
        rooms = self._get_rooms_updated()
        room_id = self._room_alias_to_id(room_id_or_alias)

        return rooms.get(room_id)

    def send_message(self, msg):
        room_obj = self.get_room_obj(self.focus_room_id)

        if not room_obj:
            logger.error('cant find room')
        else:
            room_obj.send_text(msg)

    def send_photo(self, path):
        with open(path, 'rb') as f:
            mxcurl = self.client.upload(f.read(), mimetypes.guess_type(path)[0])

            room_obj = self.get_room_obj(self.focus_room_id)

            if not room_obj:
                logger.error('cant find room')
            else:
                room_obj.send_image(mxcurl, os.path.split(path)[1])

    def send_voice(self, path):
        with open(path, 'rb') as f:
            mxcurl = self.client.upload(f.read(), mimetypes.guess_type(path)[0])
            room_obj = self.get_room_obj(self.focus_room_id)
            room_obj.send_audio(mxcurl, os.path.split(path)[1])

    def send_video(self, path):
        with open(path, 'rb') as f:
            mxcurl = self.client.upload(f.read(), mimetypes.guess_type(path)[0])
            room_obj = self.get_room_obj(self.focus_room_id)
            room_obj.send_video(mxcurl, os.path.split(path)[1])

    def discover_rooms(self):
        res = requests.get('{}/_matrix/client/r0/publicRooms?limit=20'.format(self.server))
        res_json = res.json()

        room_objs = res_json['chunk']
        return [room['aliases'][0] for room in room_objs if room.get('aliases')]

    def download_from_event(self, event):
        mxcurl = event['content']['url']
        link = self.client.api.get_download_url(mxcurl)
        media_id = mxcurl.split('/')[3]
        media_type = event['content']['info']['mimetype'].split('/')[1]
        path = os.path.join(self.tb.config['media_dir'], '{}.{}'.format(media_id, media_type))
        download_file(link, path)

        return path

    def forward_image_to_tb(self, event):
        path = self.download_from_event(event)
        self.tb.send_photo(path, self)

    def forward_voice_to_tb(self, event):
        path = self.download_from_event(event)
        self.tb.send_voice(path, self)

    def forward_video_to_tb(self, event):
        path = self.download_from_event(event)
        self.tb.send_video(path, self)

    def _room_id_to_alias(self, id):
        """Convert room id to alias.

        Args:
            id (str): Room id.

        Returns (str): Room alias.

        """
        if id is None:
            return None
        if id.startswith('#'):
            return id
        rooms = self.get_rooms_aliases()
        if id in rooms:
            return rooms[id][0]
        else:
            return None

    def _room_alias_to_id(self, alias):
        """Convert room alias to id.

        Args:
            alias (str): Room alias.

        Returns (str): Room id.

        """
        if alias is None:
            return None

        if not alias.startswith('#'):
            return alias

        return self.client.api.get_room_id(alias)

    def _get_rooms_updated(self):
        """Return rooms dictionary with updated aliases.

        Returns (dict): Return rooms dictionary with updated aliases.

        """
        rooms = self.client.get_rooms()
        for room in rooms.values():
            room.update_aliases()

        return rooms
