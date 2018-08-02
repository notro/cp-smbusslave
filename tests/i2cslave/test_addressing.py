import errno
import sys
import time
import pytest
import cpboard

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)


def slave_func(tout, addresses):
    import board
    from i2cslave import I2CSlave

    with I2CSlave(board.SCL, board.SDA, addresses, smbus=tout) as slave:
        while True:
            try:
                r = slave.request()
                if not r:
                    continue
            except OSError as e:
                if e.args and e.args[0] == 116: #  Why is timeout 116 and not 110?
                    continue

            with r:
                print('address==0x%02x' % r.address)
                print('is_read', r.is_read)
                print('is_restart', r.is_restart)


@pytest.fixture(scope='module', params=[(0x30,), (0x30, 0x31,), (0x30, 0x31, 0x32,)])
def slave(request, board):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, slave_func, out=sys.stdout)
    print("slave: Start slave: %r" % (request.param,))
    server.start(tout, request.param)
    time.sleep(1)

    yield server

    print('slave: Back from yield')
    server.stop()
    sys.stderr.write('slave: Slave stopped:\n')


def test_addressing(slave, i2cbus):
    addresses = slave.args[1]
    for addr in addresses:
        i2cbus.write(addr, [])
        time.sleep(0.1)
        out = slave.check()
        assert 'address==0x%02x' % (addr,) in out
        assert 'is_read False' in out
        assert 'is_restart False' in out


@pytest.mark.parametrize('addr', list(range(0x03, 0x78)))
def test_addressing_failure(slave, i2cbus, addr):
    if addr in slave.args[1]:
        return

    with pytest.raises(OSError) as exc_info:
        i2cbus.write(addr, [])
    assert exc_info.value.errno == errno.ENXIO
    time.sleep(pytest.config.option.serial_wait / 1000)
    out = slave.check()
    assert 'address==0x%02x' % (addr,) not in out
