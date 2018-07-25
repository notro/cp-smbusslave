import cpboard
import errno
import pytest
import sys
import time

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def read_byte_slave_func(tout, addresses, data):
    import board
    import busio

    data = bytes(data)
    print('read_byte_slave_func:', tout, repr(data))

    with busio.I2CSlave(board.SCL, board.SDA, addresses, smbus=tout) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue
            except OSError as e:
                if e.args and e.args[0] == 116: #  Why is timeout 116 and not 110?
                    continue

            try:
                with r:
                    #print('address==0x%02x' % r.address)
                    #print('is_read', r.is_read)
                    #print('is_restart', r.is_restart)

                    if r.address == 0x40:
                        n = r.write(data)
                        #print('write(0x40)', n, repr(list(data)[:n]))
                print('CLOSED')
            except OSError as e:
                print('ERROR:', e)


primes54 = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233, 239, 241, 251]

read_byte_data = [
    [],
    [14],
    [17, 24],
    [1, 2, 3, 4],
    [1, 2, 3, 4, 5],
    [1, 2, 3, 4, 5, 6],
    [17, 128, 56, 132, 22, 200],
    [33, 67, 94, 129] * 2,
    [71, 204, 156, 234] * 4,
    primes54[3:35],
    primes54[:10] + primes54,  # 64
    primes54[:20] + primes54 + primes54,  # 128
    primes54[:40] + primes54 + primes54 + primes54 + primes54,  # 256
    primes54[:26] + primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54,  # 512
    [255, 254, 253, 129, 127],
    [64, 65],
    [77],
    [],
]


@pytest.fixture(scope='module', params=read_byte_data)
def read_byte_slave(request, board):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, read_byte_slave_func, out=sys.stdout)
    server.start(tout, (0x40,), request.param)
    time.sleep(1)
    yield server
    server.stop()


@pytest.mark.parametrize('num', [1, 2, 3, 4, 8, 12, 14, 16, 18, 22, 23, 26, 32, 64, 128, 256, 512])
def test_read_byte(read_byte_slave, i2cbus, num):
    server = read_byte_slave
    data = server.args[2]

    if num - len(data) >= 1000:
        pytest.xfail('SAMD21 sends 32 dummies before giving up')

    print('\ntest_read_byte: num=%d data=%r' % (num, data))

    try:
        res = i2cbus.read(0x40, num)
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        out = server.check()

    assert 'CLOSED' in out

    if num > len(data):
        expected = data + [0xff] * (num - len(data))  # Slave waits for STOP and sends dummy 0xff
    elif num < len(data):
        expected = data[:num]  # Reads less than available
    else:
        expected = data[:]

    assert res == expected
