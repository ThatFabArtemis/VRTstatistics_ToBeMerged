import sys
import os
import threading
import socketio
class Orchestrator(threading.Thread):
    def __init__(self, url : str, logfile : str):
        threading.Thread.__init__(self, name="orchestrator-log-listener")
        self.url = url
        self.logfile = logfile
        self.stopped = False
        self.verbose = False

    def run(self):
        if self.verbose:
            print(f"orchestrator: started", file=sys.stderr)
        logfile_dirname = os.path.dirname(self.logfile)
        if not os.path.exists(logfile_dirname):
            os.makedirs(logfile_dirname)
        with open(self.logfile, "w") as ofp:
            with socketio.SimpleClient() as sio:
                sio.connect(self.url, namespace="/log")
                if self.verbose:
                    print(f"orchestrator: connected to {self.url}", file=sys.stderr)
                while not self.stopped:
                    try:
                        event = sio.receive(timeout=1)
                    except socketio.exceptions.TimeoutError:
                        continue
                    except socketio.exceptions.DisconnectedError:
                        if self.verbose:
                            print(f"orchestrator: disconnected, reconnecting...", file=sys.stderr)
                        sio.connect(self.url, namespace="/log")
                        if self.verbose:
                            print(f"orchestrator: reconnected to {self.url}", file=sys.stderr)
                        continue
                    # print(f"orchestrator: received {event}", file=sys.stderr)
                    payload = event[1]
                    message = payload['message']
                    ofp.write(message + '\n')
        if self.verbose:
            print(f"orchestrator: stopped", file=sys.stderr)

    def stop(self):
        self.stopped = True
        self.join()
    