"""Open the Jetson dashboard on this computer through a local SSH tunnel."""

import argparse
from getpass import getpass
import os
from pathlib import Path
import select
from socketserver import BaseRequestHandler, ThreadingTCPServer
import sys
import webbrowser

import paramiko


class DashboardRelay(BaseRequestHandler):
    def handle(self):
        try:
            with self.server.transport.open_channel("direct-tcpip", ("127.0.0.1", 8787),
                                                    self.client_address, timeout=5) as channel:
                while True:
                    readable, _, _ = select.select([self.request, channel], [], [], 15)
                    if not readable:
                        return
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        target = channel if source is self.request else self.request
                        target.sendall(data)
        except (OSError, paramiko.SSHException):
            return


class LocalDashboard(ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("JETSON_HOST", "jetson.local"))
    parser.add_argument("--user", default="jetson")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    password = getpass("Jetson SSH password: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\r\n")
    with paramiko.SSHClient() as client:
        client.load_system_host_keys()
        known_hosts = Path(__file__).with_name("known_hosts")
        if known_hosts.is_file():
            client.load_host_keys(str(known_hosts))
        client.connect(args.host, username=args.user, password=password,
                       timeout=8, look_for_keys=False, allow_agent=False)
        with LocalDashboard(("127.0.0.1", args.port), DashboardRelay) as server:
            server.transport = client.get_transport()
            server.transport.set_keepalive(15)
            url = "http://127.0.0.1:%d/watch" % server.server_address[1]
            print(url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
