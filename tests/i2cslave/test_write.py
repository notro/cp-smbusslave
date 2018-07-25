import cpboard
import errno
import pytest
import sys
import time

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def write_byte_slave_func(tout, addresses, num):
    import board
    import busio

    print('write_byte_slave_func: num=%d' % num)

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
                    print('address==0x%02x' % r.address)
                    print('is_read', r.is_read)
                    print('is_restart', r.is_restart)

                    if r.address == 0x40:



                        b = r.read(num)


                        print('read(0x40)', repr(list(b)))
            except OSError as e:
                print('ERROR:', e)


@pytest.fixture(scope='module', params=[0, 1, 2, 3, 4, 8, 16, 32, 64, 128, 256, 512, -1])
def write_byte_slave(request, board):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, write_byte_slave_func, out=sys.stdout)
    server.start(tout, (0x40,), request.param)
    time.sleep(1)
    yield server
    server.stop()


primes54 = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233, 239, 241, 251]

@pytest.mark.parametrize(
    'data',
    [
        [],
        [1],
        [1, 2],
        [1, 2, 3, 4],
        [1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5, 6],
        [17, 128, 56, 132, 22, 200],
        [33, 67, 94, 129] * 2,
        [71, 204, 156, 234] * 4,
        primes54[:32],
        primes54 + primes54[:10],  # 64
        primes54 + primes54 + primes54[:20],  # 128
        primes54 + primes54 + primes54 + primes54 + primes54[:40],  # 256
        primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54 + primes54[:26],  # 512
        [255, 254, 253, 129, 127],
        [64, 65],
        [77],
        [],
    ]
)
def test_write_byte(write_byte_slave, i2cbus, data):
    server = write_byte_slave
    num = server.args[2]
    fails = 0 <= num < len(data)

    #print('\n\nTEST', data, '\n\n', flush=True)

    try:
        if fails:
            with pytest.raises(OSError):
                i2cbus.write(0x40, data)
        else:
            i2cbus.write(0x40, data)
    finally:
        time.sleep(pytest.config.option.serial_wait / 1000)
        out = server.check()
        #print('\n\nDONE\n\n', flush=True)

    if fails:
        data = data[:num]
    assert 'read(0x40) %r' % (data,) in out
