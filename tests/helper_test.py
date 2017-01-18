from matrigram import helper


def test_chunks():
    l = []
    for i in range(10):
        l.append(i)

    chunks = helper.chunks(l, 4)
    chunks_list = [chunk for chunk in chunks]

    assert chunks_list[0] == [0, 1, 2, 3]
    assert chunks_list[1] == [4, 5, 6, 7]
    assert chunks_list[2] == [8, 9]


def test_list_to_str():
    l = ['room1', 'room2', 'room3']

    assert helper.list_to_nice_str(l) == 'room1, room2, room3'
