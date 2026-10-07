"""Loopback TCP tunnel into an isolated Docker container via docker exec, no extra network."""
import os
import select
import socketserver
import subprocess
import threading


def open_tunnel(container, port):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            script = """import os,select,socket
s=socket.create_connection(('127.0.0.1',8069))
while True:
 ready,_,_=select.select([0,s],[],[],30)
 for source in ready:
  data=os.read(0,65536) if source==0 else s.recv(65536)
  if not data: raise SystemExit()
  if source==0: s.sendall(data)
  else: os.write(1,data)
"""
            process = subprocess.Popen(['docker', 'exec', '-i', container, 'python3', '-u', '-c', script],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                while process.poll() is None:
                    ready, _, _ = select.select([self.request, process.stdout], [], [], 2)
                    for source in ready:
                        data = self.request.recv(65536) if source is self.request else os.read(process.stdout.fileno(), 65536)
                        if not data: return
                        if source is self.request:
                            process.stdin.write(data); process.stdin.flush()
                        else:
                            self.request.sendall(data)
            except (OSError, ValueError):
                pass
            finally:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                process.stdin.close(); process.stdout.close()
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
    server = Server(('127.0.0.1', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    return server
