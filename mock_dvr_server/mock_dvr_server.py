import asyncio
import struct

##################################
# Commands from tcpsvr.h
##################################
START_RECORD    = 0x20001
START_RECORD_R  = 0x21001
STOP_RECORD     = 0x20002
STOP_RECORD_R   = 0x21002
START_PLACE     = 0x20003
START_PLACE_R   = 0x21003
STOP_PLACE      = 0x20004
STOP_PLACE_R    = 0x21004
UNKNOWN_MSG     = 0xffffff

##################################
# The struct:
#   typedef struct{
#       int cmd;        // 4B
#       int size;       // 4B
#       short ver;      // 2B
#       char table[4];  // 4B
#       char gmcode[16];//16B
#   } DEALER_CMD_T; // total 30 bytes with #pragma pack(2)
#
# We'll parse it with struct.unpack("!I I H 2x 4s 16s")
#   (the '2x' accounts for 2 bytes of alignment after 'ver')
#
# For responses, there's a similar struct:
#   typedef struct{
#       int cmd;        // 4B
#       int size;       // 4B
#       short ver;      // 2B
#       char gmcode[16];//16B
#       int ret;        // 4B
#   } DEALER_RES_T; // also 30 bytes
# We'll pack that with struct.pack("!I I H 2x 16s I")
##################################

PACKET_SIZE = 30  # The "on-wire" size of DEALER_CMD_T

class MockDvrServerProtocol(asyncio.Protocol):
    def __init__(self):
        super().__init__()
        self.transport = None
        self.buffer = b""

    def connection_made(self, transport):
        self.transport = transport
        peername = transport.get_extra_info('peername')
        print(f"[MockDVR] Connection from {peername}")

    def data_received(self, data: bytes):
        """
        We'll buffer the incoming data because we might receive partial
        or multiple 30-byte packets in a single call.
        """
        print(f"[MockDVR] Raw data received ({len(data)} bytes): {data}")
        self.buffer += data

        # while we have at least one full packet, process it
        while len(self.buffer) >= PACKET_SIZE:
            packet = self.buffer[:PACKET_SIZE]
            self.buffer = self.buffer[PACKET_SIZE:]
            self.handle_one_packet(packet)

    def handle_one_packet(self, packet: bytes):
        """
        Parse the 30-byte DEALER_CMD_T, log it, and optionally send a response.
        """
        if len(packet) != PACKET_SIZE:
            print(f"[MockDVR] handle_one_packet: got {len(packet)} bytes, expected 30.")
            return

        # Unpack => "!I I H 2x 4s 16s"
        #   cmd (4B), size(4B), ver(2B), [2 bytes pad],
        #   table(4B), gmcode(16B)
        # cmd, size, ver, table_bytes, gmcode_bytes = struct.unpack(
        #     "!I I H 2x 4s 16s", packet
        # )
        cmd, size, ver, table_bytes, gmcode_bytes = struct.unpack("!I I H 4s 16s", packet)

        table_str = table_bytes.decode('utf-8', errors='ignore').rstrip('\x00')
        gmcode_str = gmcode_bytes.decode('utf-8', errors='ignore').rstrip('\x00')

        print(
            f"[MockDVR] Received => cmd=0x{cmd:X}, size={size}, ver={ver}, "
            f"table='{table_str}', gmcode='{gmcode_str}'"
        )

        # Basic sanity checks
        if size != PACKET_SIZE:
            print(f"[MockDVR] Warning: 'size' field != {PACKET_SIZE} => {size}")
        # Now we can interpret the command
        if cmd == START_RECORD:
            print(f"[MockDVR] => START_RECORD for table={table_str}, round={gmcode_str}")
            # Optionally respond with 0x21001:
            self.send_response(START_RECORD_R, ver, gmcode_str, ret_code=0)
        elif cmd == STOP_RECORD:
            print(f"[MockDVR] => STOP_RECORD for table={table_str}, round={gmcode_str}")
            self.send_response(STOP_RECORD_R, ver, gmcode_str, ret_code=0)
        elif cmd == START_PLACE:
            print(f"[MockDVR] => START_PLACE for table={table_str}, round={gmcode_str}")
            self.send_response(START_PLACE_R, ver, gmcode_str, ret_code=0)
        elif cmd == STOP_PLACE:
            print(f"[MockDVR] => STOP_PLACE for table={table_str}, round={gmcode_str}")
            self.send_response(STOP_PLACE_R, ver, gmcode_str, ret_code=0)
        else:
            print(f"[MockDVR] => Unknown cmd=0x{cmd:X}")
            self.send_response(UNKNOWN_MSG, ver, gmcode_str, ret_code=0x1001)

    def send_response(self, cmd, ver, gmcode_str, ret_code=0):
        """
        Send a 30-byte DEALER_RES_T struct back, with cmd, size=30,
        ver, gmcode(16B), and ret(4B).
          typedef struct{
             int cmd;   // 4B
             int size;  // 4B
             short ver; // 2B
             char gmcode[16];
             int ret;
          } DEALER_RES_T; // total 30 with #pragma pack(2)
        We'll pack as "!I I H 2x 16s I".
        """
        if not self.transport:
            return

        gmcode_bytes = gmcode_str.encode('utf-8')[:16].ljust(16, b'\x00')
        size = PACKET_SIZE
        # data = struct.pack("!I I H 2x 16s I",
        #                    cmd,
        #                    size,
        #                    ver,
        #                    gmcode_bytes,
        #                    ret_code)
        # server side
        data = struct.pack("!I I H 16s I", cmd, size, ver, gmcode_bytes, ret_code)
        # yields 30 bytes total
        self.transport.write(data)
        print(f"[MockDVR] Sent response => cmd=0x{cmd:X}, ret=0x{ret_code:X}")

    def connection_lost(self, exc):
        print("[MockDVR] Connection closed.")
        self.transport = None

async def main(host="0.0.0.0", port=11007):
    """
    Run the mock DVR server on host:port (default 0.0.0.0:11007).
    Accept connections, each handled by MockDvrServerProtocol.
    """
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: MockDvrServerProtocol(),
        host, port
    )
    print(f"[MockDVR] Listening on {host}:{port}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11007, help="Port to run the mock DVR server on")
    args = parser.parse_args()

    try:
        asyncio.run(main(port=args.port))
    except KeyboardInterrupt:
        print("[MockDVR] Stopped by user.")
