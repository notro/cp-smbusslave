import cpboard
import errno
import pytest
import sys
import time

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def write_read_slave_func(tout, addresses, num):
    import board
    from i2cslave import I2CSlave

    data = b''

    print('\nwrite_read_slave_func: num=%d' % num, repr(data))

    with I2CSlave(board.SCL, board.SDA, addresses, smbus=tout) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue
            except OSError as e:
                if e.args and e.args[0] == 116: #  Why is timeout 116 and not 110?
                    continue

            try:
                rd = None
                with r:
                    #print('address==0x%02x' % r.address)
                    #print('is_read', r.is_read)
                    #print('is_restart', r.is_restart)
                    rd = r.is_read
                    if (r.is_restart):
                        print('RESTART')

                    if r.address == 0x40:
                        if r.is_read:
                            if len(data):
                                data = data * (round(512 / len(data)) + 1)
                                n = r.write(data)
                                #print('write(0x40)', n, repr(list(data)[:n]))
                            else:
                                print('ERROR: len(data) == 0')
                        else:
                            data = r.read(num)
                            #print('read(0x40)', repr(list(b)))

                print('CLOSED', 'READ' if rd else 'WRITE')
            except OSError as e:
                print('ERROR:', e)


slave_read_num = [0, 1, 4, 16, -1]
slave_read_num_ids = ['sr({})'.format(num)
                        for num in slave_read_num]

@pytest.fixture(scope='module', params=slave_read_num, ids=slave_read_num_ids)
def write_read_slave(request, board):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, write_read_slave_func, out=sys.stdout)
    server.start(tout, (0x40,), request.param)
    time.sleep(1)
    yield server
    server.stop()


master_write_data = [
    [11],
    [15, 21],
    [3, 5, 7, 11],
    [133, 167, 194, 229] * 2,
    [171, 104, 56, 134] * 4,
    [127, 129, 253, 254, 255],
    [164, 165],
    [177],
]
master_write_data_ids = ['mw({})'.format(len(d)) for d in master_write_data]

master_read_num = [1, 2, 3, 4, 8, 16, 32, 64, 128, 256, 512]
master_read_num_ids = ['mr({})'.format(num) for num in master_read_num]

@pytest.mark.parametrize('data', master_write_data, ids=master_write_data_ids)
@pytest.mark.parametrize('num', master_read_num, ids=master_read_num_ids)
def test_write_read(write_read_slave, i2cbus, num, data):
    server = write_read_slave
    slave_num = server.args[2]
    write_fails = 0 <= slave_num < len(data)

    try:
        if write_fails:
            with pytest.raises(OSError):
                res = i2cbus.write_read(0x40, data, num)
        else:
            res = i2cbus.write_read(0x40, data, num)
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        out = server.check()

    assert 'CLOSED WRITE' in out

    if not write_fails:
        assert 'RESTART' in out
        assert 'CLOSED READ' in out

        slave_received_num = min(slave_num, len(data))
        if slave_received_num < 0:
            slave_received_num = len(data)
        slave_received_data = data[:slave_received_num]
        expected = (slave_received_data * 512)[:num]

        print('res', repr(res))
        assert res == expected
