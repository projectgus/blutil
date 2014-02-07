#!/usr/bin/env python3
"""
"""

import argparse, serial, time, subprocess, sys, os, re

parser = argparse.ArgumentParser(description='Perform various operations with BL600-SA')
parser.add_argument('-p', '--port', required=True, help="Serial port to connect to")
parser.add_argument('-m', '--model', help="Specify (instead of detecting) the model number, see command output for example model string")
parser.add_argument('-b', '--baud', type=int, default=9600, help="Baud rate for connection")
parser.add_argument('--no-dtr', action="store_true", help="Don't toggle the DTR line as a reset")
parser.add_argument('-c', '--compile', action="store_true", help="Compile specified smartBasic file")
parser.add_argument('-l', '--load', action="store_true", help="Upload specified smartBasic file to BL600")
parser.add_argument('-r', '--run', action="store_true", help="Execute specified smartBasic file on BL600")
parser.add_argument("filepath", metavar="BASICFILE")

class RuntimeError(Exception):
    pass

class BLDevice(object):
    def __init__(self, args):
        self.port = serial.Serial(args.port, args.baud, timeout=0.8)

    def writecmd(self, args, expect_response=True, timeout=0.5):
        self.port.write(bytearray("AT%s%s\r"%("" if args.startswith("+") else " ", args), "ascii"))
        if not expect_response:
            return
        response = b''
        start = time.time()
        while not response.endswith(b"00\r") and time.time() < start + timeout:
            response += self.port.read(1)
        if response.endswith(b"00\r"):
            return str(response, "ascii")[:-3].strip()
        else:
            if len(response) == 0:
                raise RuntimeError("Got no response to command '%s'" % args)
            else:
                raise RuntimeError("Got unexpected/error response to command '%s': %s" % (args,response))

    def read_param(self, param):
        return self.writecmd("I %d"%param).split("\t")[-1]

    def detect_model(self):
        model = self.read_param(0)
        revision = self.read_param(13)
        print("Detected model %s %s" % (model, revision))
        self.model = "%s_%s" % (model, revision.replace(" ","_"))

    def compile(self, filepath):
        compiler = "XComp_%s.exe" % (self.model,)
        print("Compiling %s with %s..." % (filepath, compiler))
        args = [ compiler, filepath ]
        if os.name != 'nt':
            args = [ "wine" ] + args
        ret = subprocess.call(args, stdin=None, stdout=sys.stdout, stderr=sys.stderr, shell=False)
        if ret != 0:
            raise RuntimeError("Compilation failed")
        print("Compilation success")

    def upload(self, filepath):
        parts = os.path.splitext(filepath)
        if parts[1] != ".uwc": # compiled files have .uwc extension
            filepath = "%s.uwc" % (parts[0],)
        devicename = get_devicename(filepath)
        print("Uploading %s as %s" % (filepath, devicename))
        self.writecmd('+DEL "%s" +' % devicename)
        self.writecmd('+FOW "%s"' % devicename)
        with open(filepath, "rb") as f:
            for line in chunks(f, 16):
                row = "".join([ "%02x" % x for x in line ])
                self.writecmd('+FWRH "%s"' % row)
        self.writecmd('+FCL')
        print("Upload success")

    def run(self, filepath):
        devicename = get_devicename(filepath)
        print("Running %s..." % devicename)
        self.writecmd('+RUN "%s"' % devicename, expect_response=False)
        output = self.port.read(1024)
        if len(output):
            print("Immediate output:\n%s" % output)
        else:
            print("No immediate output, program probably running...")


def chunks(somefile, chunklen):
    while True:
        chunk = somefile.read(chunklen)
        if len(chunk) == 0:
            return
        yield chunk

def get_devicename(filepath):
    """ Given a file path, find an acceptable name on the BL filesystem """
    filename = os.path.split(filepath)[1]
    filename = os.path.splitext(filename)[0]
    return re.sub(r'[:*?"<>|]', "", filename)[:24]

def main():
    args = parser.parse_args()
    device = BLDevice(args)

    ops = []
    if args.compile:
        ops += [ "compile" ]
    if args.load:
        ops += [ "load" ]
    if args.run:
        ops += [ "run" ]

    if len(ops) == 0:
        print("Nothing to do! Choose one of --compile, --load or --run, or chain them ie -clr")
        sys.exit(1)

    if (args.load or args.run or args.model is None) and not args.no_dtr:
        print("Resetting board via DTR...")
        device.port.setDTR(False)
        time.sleep(0.1)
        device.port.setDTR(True)

    if args.model is not None:
        device.model = args.model.replace(" ", "_")
    elif args.compile:
        device.detect_model()

    print("Performing %s for %s" % (", ".join(ops), args.filepath))

    if args.compile:
        device.compile(args.filepath)
    if args.load:
        device.upload(args.filepath)
    if args.run:
        device.run(args.filepath)

if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(e)
        sys.exit(2)

