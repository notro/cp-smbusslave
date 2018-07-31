import cpboard
import periphery
import pytest
import sh
import smbus
import sys
import time

def pytest_addoption(parser):
    group = parser.getgroup('smbusslave')
    group.addoption("--bus", dest='i2cbus', type=int, help='I2C bus number')
    group.addoption("--serial-wait", default=20, dest='serial_wait', type=int, help='Number of milliseconds to wait before checking board output (default: 20ms)')
    group.addoption("--smbus-timeout", default=True, dest='smbus_timeout', type=bool, help='Use SMBUS timeout limit (default: True)')


@pytest.fixture
def bus(request):
    """
    Return a smbus.SMBus instance (function scope)
    """
    return smbus.SMBus(request.config.option.i2cbus)


@cpboard.remote
def check_digital_connect(pin0, pin1):
    import board
    import digitalio

    try:
        p0 = getattr(board, pin0)
        p1 = getattr(board, pin1)

        with digitalio.DigitalInOut(p0) as d0:
            with digitalio.DigitalInOut(p1) as d1:
                d0.switch_to_input(digitalio.Pull.UP)
                d1.switch_to_output(True)

                print('d0', d0, d0.value)
                print('d1', d1, d1.value)

                if d0.value != True:
                    return False
                d1.value = False
                if d0.value != False:
                    return False
    except Exception:
        return False
    return True


@pytest.fixture(scope='session')
def digital_connect(board):
    """
    Return board pins that are wired together
    """
    # FIXME: Make it possible to overrride these
    pin0 = 'A0'
    pin1 = 'A1'
    res = check_digital_connect(board, pin0, pin1, _out=sys.stdout)
    if res:
        return [pin0, pin1]
    else:
        return None


def check_host_connect_func(pin, val):
    import board
    import digitalio

    p = getattr(board, pin)

    with digitalio.DigitalInOut(p) as d:
        d.switch_to_output(val)
        while True:
            pass


def start_check_host_connect(board, pin, val):
    server = cpboard.Server(board, check_host_connect_func, out=sys.stdout)
    server.start(pin, val)
    time.sleep(1)
    try:
        server.check()
    except Exception:
        return None
    return server


def check_host_connect(board, gpio, pin):
    for val in [True, False]:
        server = start_check_host_connect(board, pin, val)
        if server is None:
            return False

        res = gpio.read()
        if bool(res) != val:
            return False

        try:
            server.stop()
        except Exception:
            return False
    return True


@pytest.fixture(scope='session')
def host_connect(request, board):
    """
    Return board and host pins that are wired together
    """
    # FIXME: Make it possible to overrride these
    pin = 'D5'
    gpionr = 17

    gpio = None

    sh.sudo.tee(sh.echo(gpionr), '/sys/class/gpio/export')
    time.sleep(0.5)

    def teardown():
        if gpio:
            gpio.close()
        sh.sudo.tee(sh.echo(gpionr), '/sys/class/gpio/unexport')
    request.addfinalizer(teardown)

    gpio = periphery.GPIO(gpionr)
    gpio.direction = 'in'

    if check_host_connect(board, gpio, pin):
        return gpio, pin
    else:
        return None
