import digitalio
import pulseio
from smbusslave import SMBusSlave

IODIR = 0x00
IPOL = 0x01
GPINTEN = 0x02
DEFVAL = 0x03
INTCON = 0x04
IOCON = 0x05
GPPU = 0x06
INTF = 0x07
INTCAP = 0x08
GPIO = 0x09
OLAT = 0x0a

IOCON_SEQOP = 1 << 5
IOCON_ODR = 1 << 2
IOCON_INTPOL = 1 << 1


# Pull up on interrupt pins are not supported

# Interrupts are not working yet, need PulseIn.value

class MCP23008Slave(SMBusSlave):
    def __init__(self, pins, intpin=None):
        if len(pins) == 0:
            raise ValueError('pins is empty')
        super().__init__()
        pins.extend([None] * (8 - len(pins)))  # Fill up with dummies
        self.pins = [Pin(pin, i) for i, pin in enumerate(pins)]
        self.int = None
        if intpin:
            self.int = digitalio.DigitalInOut(intpin)
            self.int.switch_to_output(True)
        self.protocol = SMBusSlave.SMBUS_BYTE_SEQ
        self.max_reg = 0x0a
        self.regs = [0] * (self.max_reg + 1)
        self.regs[IODIR] = 0xff
        self.debug2 = False

    def check_events(self):
        prev_intf = self.regs[INTF]
        val = 0
        for i in range(8):
            val |= self.pins[i].interrupt << i
        self.regs[INTF] = val

        if self.regs[INTF] and not prev_intf:
            val = 0
            for i in range(8):
                val |= self.pins[i].value << i
            val |= self.regs[INTF]  # In case we're slow and have lost it. Revisit if IPOL is supported
            self.regs[INTCAP] = val
            self.set_interrupt()

    def readreg(self, reg):
        if reg == GPIO:
            val = 0
            for i in range(8):
                if self.regs[IODIR] & (1 << i):  # Is this an input?
                    val |= self.pins[i].value << i
                else:
                    val |= self.regs[OLAT] & (1 << i)

            if self.regs[INTF]:
                self.regs[INTF] = 0
                self.clear_interrupt()

        elif reg == INTCAP:
            val = self.regs[INTCAP]
            if self.regs[INTF]:
                self.regs[INTF] = 0
                self.clear_interrupt()

        else:
            val = self.regs[reg]

        if self.debug2:
            print(" 0x%02x==0x%02x" % (reg, val))
        return val

    def writereg(self, reg, val):
        if self.debug2:
            print(" 0x%02x=0x%02x" % (reg, val))

        changed = self.regs[reg] ^ val

        if reg == IODIR:
            self.regs[IODIR] = val
            self.setpinmode(changed)
        elif reg == IPOL:
            if val:
                # Not used by the Linux driver
                raise NotImplementedError('IPOL is not implemented')
        elif reg == GPINTEN:
            self.regs[GPINTEN] = val
            self.setpinmode(changed)
        elif reg == DEFVAL:
            pass
        elif reg == INTCON:
            pass
        elif reg == IOCON:
            val &= 0b00111110
            if val & IOCON_SEQOP:
                # Not used by the Linux driver
                raise NotImplementedError('IOCON:SEQOP is not implemented')
            if self.int:
                if changed & IOCON_ODR:
                    if val & IOCON_ODR:
                        self.int.drive_mode = digitalio.DriveMode.OPEN_DRAIN
                    else:
                        self.int.drive_mode = digitalio.DriveMode.PUSH_PULL
                if changed & IOCON_INTPOL:
                    self.int.value = not val & IOCON_INTPOL
        elif reg == GPPU:
            self.regs[GPPU] = val
            self.setpinmode(changed)
        elif reg == INTF:
            return  # Read only
        elif reg == INTCAP:
            return  # Read only
        elif reg == GPIO or reg == OLAT:
            if reg == GPIO:
                self.regs[OLAT] = val
            for i in range(8):
                mask = 1 << i
                if changed & mask and not self.regs[IODIR] & mask:  # Changed and not input
                    self.pins[i].value = val & mask

        self.regs[reg] = val

    def setpinmode(self, changed):
        for i in range(8):
            mask = 1 << i
            if changed & mask:
                if self.regs[IODIR] & mask:
                    interrupt = self.regs[GPINTEN] & mask
                    pull = digitalio.Pull.UP if self.regs[GPPU] & mask else None
                    self.pins[i].switch_to_input(pull, interrupt)
                else:
                    val = self.regs[OLAT] & mask
                    self.pins[i].switch_to_output(val)

    def set_interrupt(self):
        if self.debug2:
            print('\nset_interrupt: INTF=%02x INTCAP=%02x\n' % (self.regs[INTF], self.regs[INTCAP]))
        if self.int:
            active = bool(self.regs[IOCON] & IOCON_INTPOL)
            self.int.value = active

    def clear_interrupt(self):
        if self.debug2:
            print('\nclear_interrupt\n')
        if self.int:
            active = bool(self.regs[IOCON] & IOCON_INTPOL)
            self.int.value = not active


# Doubles as a DigitalInOut and PulseIn dummy for the Pin class
class DummyIO:
    def __init__(self):
        self.direction = digitalio.Direction.INPUT
        self.drive_mode = digitalio.DriveMode.PUSH_PULL
        self.value = False
        self.pull = None

    def switch_to_output(self, value=False, drive_mode=digitalio.DriveMode.PUSH_PULL):
        self.direction = digitalio.Direction.OUTPUT
        self.value = value
        self.drive_mode = drive_mode

    def switch_to_input(self, pull=None):
        self.direction = digitalio.Direction.INPUT
        self.pull = pull
        if pull == digitalio.Pull.UP:
            self.value = True
        else:
            self.value = False

    def __len__(self):
        return 0


class Pin:
    def __init__(self, pin, index):
        self.pin = pin
        self.index = index
        self.io = None
        self.pulseio = None
        self.pulseio_val = None
        self.pulseio_maxlen = 10
        self._interrupt = False
        self.debug = False
        if self.pin is None:
            self.io = DummyIO()
            self.pulseio = self.io
            self.pulseio_val = False
        else:
            self._ensure_io()

    def switch_to_output(self, value=False, drive_mode=digitalio.DriveMode.PUSH_PULL):
        self._ensure_io()
        if self.debug:
            print('%d.switch_to_output(%r)' % (self.index, value,))
        self.io.switch_to_output(value)

    # Edge/level?
    def switch_to_input(self, pull=None, interrupt=False):
        if interrupt:
            self._ensure_pulseio()
        else:
            self._ensure_io()
            if self.debug:
                print('%s.switch_to_input(%r)' % (self.index, pull,))
            self.io.switch_to_input(pull)

    @property
    def value(self):
        if self.io is not None:
            val = bool(self.io.value)
            if self.debug and self.pin:
                print('%s.value == %r' % (self.index, val,))
            return val

        if self.pulseio is not None:
            val = self._get_pulseio_value()
            if val is not None:
                if self.debug:
                    print('%s.value == %r (%d)' % (self.index, val, len(self.pulseio)))
                return val

            # Unable to determine value so look at the pin
            self.pulseio.deinit()
            tmp = digitalio.DigitalInOut(self.pin)
            tmp.switch_to_input(None)
            val = tmp.value
            tmp.deinit()
            self.pulseio = None
            self._ensure_pulseio()
            if self.debug:
                print('%s.value(DIG) == %r' % (self.index, val,))
            return val

        raise ValueError('bug: neither io nor pulseio is set')

    @value.setter
    def value(self, val):
        if self.io is None or self.io.direction == digitalio.Direction.INPUT:
            raise AttributeError('Cannot set value when direction is input.')
        val = bool(val)
        self.io.value = val
        if self.debug:
            print('%s.value = %r' % (self.index, val,))

    @property
    def interrupt(self):
        if self.pulseio is None:
            return False
        val = self._interrupt
        self._interrupt = False
        return val

    def _get_pulseio_value(self):
        pulses = [self.pulseio.popleft() for _ in range(len(self.pulseio))]
        num_pulses = len(pulses)

        if num_pulses == 0:
            return self.pulseio_val

        self._interrupt = True

        if num_pulses == self.pulseio_maxlen:
            return None

        if self.pulseio_val is None:
            self.pulseio_val = False
            num_pulses += 1  # The 'missing' first edge
        val = bool(self.pulseio_val ^ bool(num_pulses % 2))
        self.pulseio_val = val
        return val

    def _ensure_io(self):
        if self.pin is None:
            return
        if self.pulseio is not None:
            if self.debug:
                print('%s.PulseIn(%r).deinit()' % (self.index, self.pin,))
            self.pulseio.deinit()
            self.pulseio = None
        if self.io is None:
            if self.debug:
                print('%d = DigitalInOut(%r)' % (self.index, self.pin,))
            self.io = digitalio.DigitalInOut(self.pin)

    def _ensure_pulseio(self):
        if self.pin is None:
            return
        if self.io is not None:
            if self.debug:
                print('%s.DigitalInOut(%r).deinit()' % (self.index, self.pin,))
            self.io.deinit()
            self.io = None
        if self.pulseio is None:
            if self.debug:
                print('%s = PulseIn(%r, maxlen=%d)' % (self.index, self.pin, self.pulseio_maxlen,))
            self.pulseio = pulseio.PulseIn(self.pin, maxlen=self.pulseio_maxlen) # , idle_state=False)
            self.pulseio_val = None
