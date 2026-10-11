#!/usr/bin/env python3
"""Local-only TCP forwarding through an already authorized SSH server.

Configuration contains connection coordinates, never passwords or model keys.
The SSH password is read without echo and retained only for this process.
"""
import argparse
import getpass
import json
from pathlib import Path
import select
import socketserver
import threading

import paramiko


class Connection:
    def __init__(self, config, password):
        self.config, self.password = config, password
        self.client = None
        self.lock = threading.Lock()

    def transport(self):
        with self.lock:
            if self.client and self.client.get_transport() and self.client.get_transport().is_active():
                return self.client.get_transport()
            if self.client:
                self.client.close()
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(self.config['ssh_host'], port=self.config.get('ssh_port', 22),
                           username=self.config['ssh_user'], password=self.password,
                           allow_agent=False, look_for_keys=False, timeout=12,
                           auth_timeout=12, banner_timeout=12)
            client.get_transport().set_keepalive(30)
            self.client = client
            return client.get_transport()

    def close(self):
        if self.client:
            self.client.close()


class ForwardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    if any(key in config for key in ('password', 'api_key', 'ssh_password')):
        raise ValueError('Credentials must not be stored in connection configuration')
    for key in ('ssh_host', 'ssh_user', 'target_host'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f'{key} is required')
    for key in ('target_port', 'local_port'):
        if type(config.get(key)) is not int or not 1 <= config[key] <= 65535:
            raise ValueError(f'{key} must be a valid port')
    connection = Connection(config, getpass.getpass('SSH password (not saved): '))
    connection.transport()

    class Forward(socketserver.BaseRequestHandler):
        def handle(self):
            channel = None
            try:
                channel = connection.transport().open_channel('direct-tcpip',
                    (config['target_host'], config['target_port']), self.request.getpeername(), timeout=15)
                if channel is None:
                    return
                while True:
                    ready, _, _ = select.select([self.request, channel], [], [], 60)
                    if self.request in ready:
                        data = self.request.recv(65536)
                        if not data:
                            break
                        channel.sendall(data)
                    if channel in ready:
                        data = channel.recv(65536)
                        if not data:
                            break
                        self.request.sendall(data)
            except Exception as failure:
                print(json.dumps({'forward_error': type(failure).__name__}), flush=True)
            finally:
                if channel:
                    channel.close()

    try:
        with ForwardServer(('127.0.0.1', config['local_port']), Forward) as server:
            print(json.dumps({'local_forward_ready': True, 'local_port': config['local_port']}), flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        connection.close()


if __name__ == '__main__':
    main()
