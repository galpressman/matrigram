Quick start
===========

After the server is running, switch to your telegram app and add the bot to your contact list.

- First login with your matrix account:

  ``/login username password``

  The bot will reply with information.
- Use ``/join room_id_or_alias`` to join rooms, or ``/leave`` to leave them.
- Once you have joined rooms, use ``/focus`` to choose what room you are interested at the moment.

Focus
^^^^^
When communicating with our telegram bot, you only have one conversation windows open while you may have joined many matrix rooms.
Showing all messages from all different rooms in one conversation is confusing and a big mess, hence the `focus` feature.

If you send a message, the message will be relayed to your focused room only.
When messages are being sent in your focused rooms, they will be relayed to your telegram client. Messages from other rooms you have joined will not be sent to you while not focused.

Usage
*****
To set your `focus` room simply write down ``/focus``, which will prompt you for the rooms you have joined.

In order to view status regarding the rooms you have joined and focused room use the ``/status`` command.