import sys
import os
import requests
import threading
import socket
import json
from typing import Optional, List, Any, cast, Union

__all__ = ["Runner", "RunnerServerPort"]

RunnerServerPort = 5002

RunnerArgs = dict[str, Any]


class Runner:
    host: str
    role : str
    statPath: str
    logPath: str
    exePath: str
    exeArgs : List[str]
    running : Any
    verbose : bool
    runnerConfig : dict[str, dict[str, Union[str, bool]]] = {}
    mdnsWorkaround = True

    @classmethod
    def load_config(cls, filename : str) -> None:
        cls.runnerConfig = json.load(open(filename))

    def __init__(self, host: str, role : str, config: Optional[RunnerArgs] = None, verbose: bool=False) -> None:
        self.host = host
        self.role = role
        self.running = None
        self.verbose = verbose
        return
        if not config:
            config = self.runnerConfig.get(self.host)
            if not config:
                raise RuntimeError(f"Host key '{self.host}' not found in VRTstatistics configuration")
        if "host" in config:
            self.host = config["host"]
        if self.mdnsWorkaround and ".local" in self.host:
            try:
                ip = socket.gethostbyname(self.host)
            except socket.gaierror:
                print(f"Cannot lookup '{self.host}'")
                raise
            if self.verbose:
                print(f'+ lookup {self.host} -> {ip}')
                self.host = ip
        self.statPath = config["statPath"]
        self.logPath = config["logPath"]
        self.exePath = cast(str, config.get("exePath"))
        self.exeArgs = config.get("exeArgs", [])

    def start(self, workdirname : str) -> None:
        url = f"http://{self.host}:{RunnerServerPort}/start"
        if self.verbose:
            print(f"VRTRun: + POST {url} workdir={workdirname}")
        r = requests.post(url, json={'workdir' : workdirname})
        r.raise_for_status()
        
    def upload_config_dir(self, configdir : str, recursive : bool) -> None:
        if not os.path.exists(configdir):
            return
        for root, _, files in os.walk(configdir):
            for file in files:
                if not recursive:
                    if root != configdir:
                        continue
                fullpath = os.path.join(root, file)
                relpath = os.path.relpath(fullpath, configdir)
                self.upload_config_file(fullpath, relpath)

    def upload_config_file(self, fullpath : str, relpath : str) -> None:
        url = f"http://{self.host}:{RunnerServerPort}/putfile"
        if self.verbose:
            print(f"VRTRun: + POST {url} fullpath={fullpath} relpath={relpath}")
        files = {'file' : (relpath, open(fullpath, 'rb'), 'application/octet-stream')}
        r = requests.post(url, files=files)
        r.raise_for_status()

    def send_config(self) -> None:
        pass

    def get_result_filenames(self) -> List[str]:
        url = f"http://{self.host}:{RunnerServerPort}/listdir"
        if self.verbose:
            print(f"VRTRun: + GET {url}")
        r = requests.get(url)
        r.raise_for_status()
        return r.json()
    
    def receive_results(self, remote_dirname : str, dirname : str) -> None:
        filenames = self.get_result_filenames()
        if not remote_dirname.endswith('/'):
            remote_dirname += '/'
        for filename in filenames:
            local_filename = filename
            if local_filename.startswith(remote_dirname):
                local_filename = local_filename[len(remote_dirname):]
            else:
                print(f"VRTRun: Warning: Filename {filename} does not start with {remote_dirname}")
            local_filename = os.path.join(dirname, local_filename)
            local_dirname = os.path.dirname(local_filename)
            if not os.path.exists(local_dirname):
                os.makedirs(local_dirname)
            self.get_remotefile(filename, local_filename)

    def get_log(self, filename : str) -> None:
        self.get_remotefile(self.logPath, filename)

    def get_stats(self, filename : str) -> None:
        self.get_remotefile(self.statPath, filename)

    def get_remotefile(self, remotepath : str, filename : str) -> None:
        url = f"http://{self.host}:{RunnerServerPort}/get/{remotepath}"
        if self.verbose:
            print(f"VRTRun: + GET {url}")
        r = requests.get(url, stream=True)
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        size = 0
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                size += len(chunk)
                f.write(chunk)
        r.raise_for_status()
        if self.verbose:
            print(f"VRTRun: - GET {url} filename={filename} size={size}")

    def put_file(self, filename : str, data : str) -> str:
        url = f"http://{self.host}:{RunnerServerPort}/putfile"
        if self.verbose:
            print(f"VRTRun: + POST {url} filename={filename} data=...", file=sys.stderr)
        request_arg = {'filename' : filename, 'data' : data}
        r = requests.post(url, json=request_arg)
        rv = r.json()
        if self.verbose:
            print(f'VRTRun: - POST {url} -> {rv}')
        return rv['fullpath']

    def run(self) -> None:
        assert self.running == None
        self.running = threading.Thread(target=self._run_server_thread)
        self.running.start()

    def wait(self) -> int:
        assert self.running != None
        try:
            self.running.join()
        except KeyboardInterrupt:
            print("VRTRun: KeyboardInterrupt. Sending kill to server")
            self.kill()
            print("VRTRun: Waiting for process to finish after kill")
            self.running.join()
            print("VRTRun: Process finished after kill")
        rv = self.status_code
        return rv

    def kill(self) -> None:
        url = f"http://{self.host}:{RunnerServerPort}/kill"
        if self.verbose:
            print(f"VRTRun: + POST {url}")
        r = requests.post(url)
        r.raise_for_status()
        self.status_code = r.status_code if r.status_code != 200 else 0
        
    def _run_server_thread(self):
        url = f"http://{self.host}:{RunnerServerPort}/run"
        if self.verbose:
            print(f"VRTRun: + POST {url}", file=sys.stderr)
        response = requests.post(url)
        print(response.text)
        self.status_code = response.status_code if response.status_code != 200 else 0
