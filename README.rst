|matrigram|\ matrigram
======================

|Build Status| |Documentation Status|

A bridge between `matrix <https://www.matrix.org>`_ and
`telegram <https://www.telegram.org>`_.

Installation
~~~~~~~~~~~~

Install dependencies using:

.. code:: bash

    $ pip install -r requirements.txt

Usage
~~~~~

First fill ``~/.matrigramconfig`` with your details (similar to
``config.json.example``). If the config file doesn't exist, matrigram
will create one for you to fill.

Run using ``matrigram_main.py``, which will enter an infinite listening
loop:

.. code:: python

    mg.message_loop(run_forever='-I- matrigram running...')

Documentation
~~~~~~~~~~~~~

The documentation is hosted on `Read the
Docs <http://matrigram.readthedocs.org>`__.

Comaptibility
~~~~~~~~~~~~~

matrigram works on python2.7+.

We constantly update our
`matrix-python-sdk <https://github.com/matrix-org/matrix-python-sdk>`__
version, so requirements will *probably* change frequently to keep up.

.. |matrigram| image:: docs/logo.jpg
.. |Build Status| image:: https://travis-ci.org/GalPressman/matrigram.svg?branch=master
   :target: https://travis-ci.org/GalPressman/matrigram
.. |Documentation Status| image:: https://readthedocs.org/projects/matrigram/badge/?version=latest
   :target: http://matrigram.readthedocs.io/en/latest/?badge=latest
