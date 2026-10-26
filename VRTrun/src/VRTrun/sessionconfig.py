import json
import os
from typing import Dict, List, Tuple, Any

class SessionConfig:

    global_config : Dict[str, str]
    machines : Dict[str, Dict[str, str]]

    @staticmethod
    def from_configdir(configdir : str) -> "SessionConfig":
        rv = SessionConfig()
        rv.init_from_configdir(configdir)
        return rv
    
    @staticmethod
    def from_hostlist(hostlist : List[str]) -> "SessionConfig":
        rv = SessionConfig()
        rv.init_from_hostlist(hostlist)
        return rv
    
    def __init__(self) -> None:
        self.global_config = dict()
        self.machines = dict()

    def init_from_configdir(self, configdir : str) -> None:
        config = json.load(open(os.path.join(configdir, "runconfig.json")))
        config : List[str | Dict[str, str]] | Dict[str, Any]
        if type(config) is not dict:
            config = {
                "machines": config,
                "global": dict()
            }
        self.global_config = config["global"]
        self.machines : Dict[str, Dict[str, str]] = dict()
        machine : str | Dict[str, str]
        for machine in config["machines"]:
            if type(machine) is str:
                machine = {
                    "role": machine,
                    "address": machine
                }
            else:
                assert type(machine) is dict

            self.machines[machine["role"]] = machine
    
    def init_from_hostlist(self, hostlist : List[str]) -> None:
        self.global_config = dict()
        self.machines = {host: {"role": host, "address": host} for host in hostlist}


    def get_machines(self) -> List[Tuple[str, str]]:
        return [(m["role"], m["address"]) for m in self.machines.values()]

                                