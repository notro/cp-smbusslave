import cpboard
import errno
import pytest
import sys
import time

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def request_slave_func(tout, addresses, delay_ms):
    import board
    import busio
    import time

    with busio.I2CSlave(board.SCL, board.SDA, addresses, smbus=tout) as slave:
        while True:
            r = slave.request()
            if not r:
                time.sleep(delay_ms / 1000)
                continue

            try:
                rd = None
                with r:
                    rd = r.is_read
                    if (r.is_restart):
                        print('RESTART')

                    if r.address == 0x40:
                        if r.is_read:
                            r.write(bytes([1, 2, 3, 4, 5, 6, 7, 8]))
                        else:
                            r.read()

                print('CLOSED', 'READ' if rd else 'WRITE')
            except OSError as e:
                print('ERROR:', e)


@pytest.fixture(scope='module', params=[10, 20, 30])
def request_slave(request, board):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, request_slave_func, out=sys.stdout)
    server.start(tout, (0x40,), request.param)
    time.sleep(1)
    yield server
    server.stop()


@pytest.mark.parametrize('data',
    [
        [10, 11],
        [10, 11, 12, 13],
        [20, 21, 22, 23, 24, 25],
    ]
)
@pytest.mark.parametrize('num', [1, 4, 8])
def test_delayed(request_slave, i2cbus, data, num):
    server = request_slave

    try:
        res = i2cbus.write_read(0x40, data, num)
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        out = server.check()

