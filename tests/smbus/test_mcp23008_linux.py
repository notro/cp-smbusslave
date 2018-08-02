import cpboard
import os
import periphery
import pytest
import queue
import random
import subprocess
import sys
import threading
import time

if not pytest.config.option.i2cbus:
    pytest.skip("--bus is missing, skipping tests", allow_module_level=True)

address = 0x20


def mcp23008slave_func(tout, address, pins, intpin):
    import board
    import digitalio
    import mcp23008slave
    from i2cslave import I2CSlave


    tout = False  # Needed while printing stuff for debugging


    pins = [getattr(board, p) if p else None for p in pins]
    intpin = getattr(board, intpin) if intpin else None
    print('mcp23008slave_func', tout, '0x%02x' % (address,), repr(pins), repr(intpin))
    mcp23008 = mcp23008slave.MCP23008Slave(pins, intpin)

    mcp23008.debug2 = True
    for pin in mcp23008.pins:
        if pin:
            pin.debug = True

    once = True

    def dump_regs():
        for i in range(mcp23008.max_reg + 1):
            print('%02x: 0x%02x  %s' % (i, mcp23008.regs[i], bin(mcp23008.regs[i])))

    def dump_regs_once():
        if not once:
            return
        once = False
        dump_regs()


    with I2CSlave(board.SCL, board.SDA, (address,), smbus=tout) as slave:
        while True:
            mcp23008.check_events()
            try:
                r = slave.request()
                if not r:
                    continue
                with r:
                    if r.address == address:
                        mcp23008.process(r)
            except OSError as e:
                print('ERROR:', e)

            #if any(mcp23008.pulse) or mcp23008.regs[mcp23008slave.GPINTEN]:
            #    dump_regs_once()


@pytest.fixture(scope='module')
def mcp23008slave(request, board, digital_connect, host_connect):
    tout = request.config.option.smbus_timeout
    server = cpboard.Server(board, mcp23008slave_func, out=sys.stdout)
    pins = digital_connect
    if not pins:
        pins = [None, None]
    pins += ['D13']  # Red led

    intpin = host_connect[1] if host_connect else None

    server.start(tout, address, pins, intpin)
    time.sleep(1)
    yield server
    server.stop()


def system(cmd):
    print('\n' + cmd)
    if os.system(cmd) != 0:
        raise RuntimeError('Failed to run: %s' % (cmd,))
    print()


def sudo(cmd):
    system('sudo ' + cmd)


def dtc(name):
    path = os.path.dirname(os.path.realpath(__file__))
    dts = os.path.join(path, '%s-overlay.dts' % (name,))
    dtbo = os.path.join(path, '%s.dtbo' % (name,))
    if not os.path.exists(dtbo) or (os.stat(dts).st_mtime - os.stat(dtbo).st_mtime) > 1:
        system('dtc -@ -I dts -O dtb -o %s %s' % (dtbo, dts))
    return dtbo


def dtoverlay(dtbo, gpio):
    path = os.path.dirname(dtbo)
    name = os.path.splitext(os.path.basename(dtbo))[0]
    sudo('dtoverlay -v -d %s %s intgpio=%d' % (path, name, gpio))


@pytest.fixture(scope='module')
def mcp23008(request, host_connect, mcp23008slave):
    busnum = request.config.option.i2cbus
    dev = '/sys/bus/i2c/devices/i2c-%d' % (busnum,)

    # Use a finalizer to ensure that teardown happens should an exception occur during setup
    def teardown():
        sudo('dtoverlay -v -r')
         #if os.path.exists(dev):
         #   sudo('sh -c "echo 0x%02x > %s/delete_device"; dmesg | tail' % (address, dev))
    request.addfinalizer(teardown)


    dtbo = dtc('mcp23008')
    dtoverlay(dtbo, 17)
    #sudo('sh -c "echo mcp23008 0x%02x > %s/new_device" && dmesg | tail' % (address, dev))

    time.sleep(1)

    gpiochipdir = os.listdir('/sys/bus/i2c/devices/%d-%04x/gpio/' % (busnum, address))
    if len(gpiochipdir) != 1:
        raise RuntimeError('gpiodir should have one item: %r' % (gpiochipdir,))
    chipnum = int(os.path.basename(gpiochipdir[0])[8:])

    #debugfs = '/sys/kernel/debug/pinctrl/%d-%04x' % (busnum, address)
    #sudo('sh -c "tail -n +1 %s/*"' % (debugfs,))

    return chipnum


def debugfs(gpio):
    try:
        sudo('cat /sys/kernel/debug/gpio | grep gpio-%d' % (gpio,))
    except RuntimeError:
        pass


def gpio_fixture_helper(request, gpionr):
    gpio = None
    sudo('sh -c "echo %d > /sys/class/gpio/export"' % (gpionr,))
    time.sleep(0.5)

    def teardown():
        if gpio:
            gpio.direction = 'in'
            gpio.close()
        sudo('sh -c "echo %d > /sys/class/gpio/unexport"' % (gpionr,))
    request.addfinalizer(teardown)

    gpio = periphery.GPIO(gpionr)
    return gpio


@pytest.fixture(scope='module')
def gpio0(request, mcp23008):
    return gpio_fixture_helper(request, mcp23008 + 0)


@pytest.fixture(scope='module')
def gpio1(request, mcp23008):
    return gpio_fixture_helper(request, mcp23008 + 1)


@pytest.fixture(scope='module')
def gpio2(request, mcp23008):
    return gpio_fixture_helper(request, mcp23008 + 2)


@pytest.mark.parametrize('blinks', range(5))
def test_blink_led(mcp23008slave, gpio2, blinks):
    server = mcp23008slave

    gpio2.direction = 'out'
    server.check()

    for val in [True, False]:
        gpio2.write(val)
        time.sleep(0.5)
        server.check()


def delayed_check(server):
    time.sleep(pytest.config.option.serial_wait / 1000)
    out = server.check()
    sys.stdout.flush()
    return out


@pytest.mark.parametrize('swap', [False, True], ids=['gpio1->gpio0', 'gpio0->gpio1'])
def test_digitalio(digital_connect, mcp23008slave, gpio0, gpio1, swap):
    pins = digital_connect
    if not pins:
        pytest.skip('No test wire connected')
    server = mcp23008slave

    if swap:
        gpio0, gpio1 = gpio1, gpio0

    gpio_in = gpio0
    gpio_out = gpio1

    sys.stdout.write('SETUP %s\n' % swap); sys.stdout.flush()
    gpio_in.direction = 'in'
    gpio_out.direction = 'out'
    delayed_check(server)

    for val in [False, True]:
        sys.stdout.write('WRITE %s\n' % val); sys.stdout.flush()
        gpio_out.write(val)
        delayed_check(server)
        sys.stdout.write('READ %s\n' % val); sys.stdout.flush()
        assert gpio_in.read() == val


# From python-periphery/tests/test_gpio.py
# Wrapper for running poll() in a thread
def threaded_poll(gpio, timeout):
    ret = queue.Queue()

    def f():
        ret.put(gpio.poll(timeout))

    thread = threading.Thread(target=f)
    thread.start()
    return ret


@pytest.mark.skip('Waiting for PulseIn.value property to be implemented')
@pytest.mark.parametrize('swap', [False, True], ids=['gpio1->gpio0', 'gpio0->gpio1'])
def test_interrupt_val(host_connect, digital_connect, mcp23008slave, gpio0, gpio1, swap):
    if not digital_connect or not host_connect:
        pytest.skip('No test wire(s) connected')
    server = mcp23008slave
    delayed_check(server)

    if swap:
        gpio0, gpio1 = gpio1, gpio0

    gpio_in = gpio0
    gpio_out = gpio1

    gpio_in.direction = 'in'
    gpio_in.edge = 'both'
    delayed_check(server)

    gpio_out.direction = 'out'
    gpio_out.write(True)
    gpio_out.write(False)
    delayed_check(server)

    for val in [False, True]:
        gpio_out.write(val)
        delayed_check(server)
        assert gpio_in.read() == val


@pytest.mark.skip('Waiting for PulseIn.value property to be implemented')
def test_interrupt_falling(host_connect, digital_connect, mcp23008slave, gpio0, gpio1):
    if not digital_connect or not host_connect:
        pytest.skip('No test wire(s) connected')
    server = mcp23008slave
    delayed_check(server)

    system('cat /proc/interrupts')

    gpio_in = gpio0
    gpio_out = gpio1

    gpio_out.direction = 'out'
    gpio_out.write(True)
    delayed_check(server)

    # Check poll falling 1 -> 0 interrupt
    print("Check poll falling 1 -> 0 interrupt")
    gpio_in.edge = "falling"
    delayed_check(server)
    poll_ret = threaded_poll(gpio_in, 5)
    time.sleep(1)
    delayed_check(server)
    gpio_out.write(False)

    # Extra pulse to get past the missing pulseio first edge
    gpio_out.write(True)
    gpio_out.write(False)

    delayed_check(server)
    system('cat /proc/interrupts')

    assert poll_ret.get() == True
    assert gpio_in.read() == False


@pytest.mark.skip('Waiting for PulseIn.value property to be implemented')
def test_interrupt_rising(host_connect, digital_connect, mcp23008slave, gpio0, gpio1):
    if not digital_connect or not host_connect:
        pytest.skip('No test wire(s) connected')
    server = mcp23008slave
    delayed_check(server)

    gpio_in = gpio0
    gpio_out = gpio1

    gpio_out.direction = 'out'
    gpio_out.write(False)
    delayed_check(server)

    # Check poll rising 0 -> 1 interrupt
    print("Check poll rising 0 -> 1 interrupt")
    gpio_in.edge = "rising"
    poll_ret = threaded_poll(gpio_in, 5)
    time.sleep(1)
    delayed_check(server)

    gpio_out.write(True)

    # Extra pulse to get past the missing pulseio first edge
    gpio_out.write(False)
    gpio_out.write(True)

    delayed_check(server)
    assert poll_ret.get() == True
    assert gpio_in.read() == True


@pytest.mark.skip('Waiting for PulseIn.value property to be implemented')
def test_interrupt_rising_falling(host_connect, digital_connect, mcp23008slave, gpio0, gpio1):
    if not digital_connect or not host_connect:
        pytest.skip('No test wire(s) connected')
    server = mcp23008slave
    delayed_check(server)

    gpio_in = gpio0
    gpio_out = gpio1

    gpio_out.direction = 'out'

    # Check poll rising+falling interrupts
    print("Check poll rising/falling interrupt")
    gpio_in.edge = "both"
    poll_ret = threaded_poll(gpio_in, 5)
    time.sleep(1)
    gpio_out.write(False)
    assert poll_ret.get() == True
    assert gpio_in.read() == False
    poll_ret = threaded_poll(gpio_in, 5)
    time.sleep(1)
    gpio_out.write(True)
    assert poll_ret.get() == True
    assert gpio_in.read() == True
