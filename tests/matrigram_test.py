import subprocess
import shlex
import time


class TestMatrigram(object):
    def test_one(self):
        cmd = 'python matrigram_main.py'
        p = subprocess.Popen(shlex.split(cmd))

        time.sleep(5)

        assert not p.poll(), "matrigram did not boot"
        p.terminate()
        p.wait()
