
class AT24Slave:
    def __init__(self, file):
        file.seek(0, 2)
        size = file.tell()
        file.seek(0, 0)
        if size == 0:
            raise ValueError('File is empty')
        self.file = file
        self.size = size
        self.addr = 0
        self.debug = False

    def process(self, req):
        if not req.is_read:
            byte = req.read(1, ack=False)
            if self.debug:
                print("process write: ", byte)
            if not byte:
                return
            addr = byte[0]
            if addr > 128:
                req.ack(False)
                return

            req.ack(True)
            self.addr = addr

            if self.debug:
                print("self.addr =", self.addr)

            data = req.read(16)
            if not data:
                return
            self.file.seek(self.addr)
            self.file.write(data)

            return

        elif req.is_restart:
            if self.debug:
                print("process restart: ")

            self.file.seek(self.addr)

        else:  # Read
            if self.debug:
                print("process read: ")

        while True:
            byte = self.file.read(1)
            if not byte:
                return
            if req.write(byte) != 1:
                return
