import matrigram.matrigram_main
import multiprocessing


class TestMatrigram(object):
    def test_one(self):
        p = multiprocessing.Process(target=matrigram.matrigram_main.main)
        p.start()

        p.join(5)

        assert p.is_alive(), "matrigram did not boot"
        p.terminate()
        p.join()
