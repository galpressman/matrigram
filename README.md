#![matrigram][logo]matrigram
[![Build Status](https://travis-ci.org/GalPressman/matrigram.svg?branch=master)](https://travis-ci.org/GalPressman/matrigram) [![Documentation Status](https://readthedocs.org/projects/matrigram/badge/?version=latest)](http://matrigram.readthedocs.io/en/latest/?badge=latest)

A bridge between *[matrix](https://www.matrix.org)* and *[telegram](https://www.telegram.org)*.

###Installation
Install all dependencies using:
```
pip install -r requirements.txt
```

###Usage
First fill `config.json` with your details.

Run using `matrigram.py`, which will enter an infinite listening loop:
```python
mg.message_loop(run_forever='-I- matrigram running...')
```

###Documentation
The documentation is hosted on [Read the Docs](http://matrigram.readthedocs.org).

[logo]: docs/logo.jpg "matrigram"
