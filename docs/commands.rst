Bot commands
============

- ``/login <username> <password>``

  Log in with your matrix username and password.
- ``/logout``

  Log out of your matrix user.
- ``/join <room_name>``

  Join to the given room.
- ``/leave``

  Get a list of the rooms you have joined.
- ``/discover_rooms``

  Get a list of public rooms on the server.

  `This may not work on big servers with many public rooms`
- ``/focus``

  Interactive command. Prompt the user for the room he wants to "focus" right now.
- ``/status``

  Return general information regarding the user status.

Every other message (text, photos, videos) which is sent while logged in and focused to a room will be propagated to the room, and vice versa for the room messages being sent from other users.