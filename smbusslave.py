
class SMBusSlave:
    (SMBUS_BYTE, SMBUS_WORD,
     SMBUS_BYTE_SEQ, SMBUS_WORD_SEQ, # non-std sequential byte/word access (from Linux)
     SMBUS_PROCESS_CALL, SMBUS_BLOCK, SMBUS_BLOCK_PROC_CALL,
     SMBUS_HOST_NOTIFY) = range(8)

    def __init__(self):
        self.max_reg = 0
        self.debug = False

    def writereg(self, reg, val):
        raise NotImplementedError

    def readreg(self, reg):
        raise NotImplementedError

    def command(self, command):
        if command > self.max_reg:
            return False;
        self.regnr = command
        return True

    def _seq_reg_inc(self):
        if self.protocol == SMBusSlave.SMBUS_BYTE_SEQ or self.protocol == SMBusSlave.SMBUS_WORD_SEQ:
            self.regnr += 1
            if self.regnr > self.max_reg:
                self.regnr = 0

    def _read_byte(self, req):
        if self.debug:
            print("_read_byte: ", end='')
        byte = req.read(1)
        if self.debug:
            print(byte)
        if not byte:
            return False
        self.writereg(self.regnr, byte[0])
        self._seq_reg_inc()
        return True

    def _write_byte(self, req):
        byte = self.readreg(self.regnr)
        if self.debug:
            print(" byte=0x%02x" % byte, end='', flush=True)
        if req.write(byte.to_bytes(1, 'little')) != 1:
            return False
        self._seq_reg_inc()
        return True

    def _read_word(self, req):
        word = req.read(2)
        if len(word) != 2:
            return False
        self.writereg(self.regnr, word[1] << 8 | word[0])
        self._seq_reg_inc()
        return True

    def _write_word(self, req):
        word = self.readreg(self.regnr)
        if self.debug:
            print(" word=0x%04x" % word, end='', flush=True)
        if req.write(word.to_bytes(2, 'little')) != 2:
            return False
        self._seq_reg_inc()
        return True

    def process(self, req):
        if not req.is_read:
            cmd = req.read(1, ack=False)
            if self.debug:
                print("process write: ", cmd)
            if not cmd:
                return False
            if not self.command(cmd[0]):
                req.ack(False)
                return False

            req.ack(True)

            if self.debug:
                print("self.regnr =", self.regnr)
            if self.protocol == SMBusSlave.SMBUS_BYTE:
                return self._read_byte(req)
            elif self.protocol == SMBusSlave.SMBUS_BYTE_SEQ:
                while True:
                    if not self._read_byte(req):
                        return False
            elif self.protocol == SMBusSlave.SMBUS_WORD:
                return self._read_word(req)
            elif self.protocol == SMBusSlave.SMBUS_WORD_SEQ:
                while True:
                    if not self._read_word(req):
                        return False
            else:
                raise NotImplementedError

        elif req.is_restart:
            if self.debug:
                print("process restart: ")
            if self.protocol == SMBusSlave.SMBUS_BYTE:
                return self._write_byte(req)
            elif self.protocol == SMBusSlave.SMBUS_BYTE_SEQ:
                while True:
                    if not self._write_byte(req):
                        return False
            elif self.protocol == SMBusSlave.SMBUS_WORD:
                return self._write_word(req)
            elif self.protocol == SMBusSlave.SMBUS_WORD_SEQ:
                while True:
                    if not self._write_word(req):
                        return False
            else:
                raise NotImplementedError
        else:
            print("process NOTHING: ")
            return False
