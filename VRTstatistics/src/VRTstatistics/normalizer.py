from __future__ import annotations
import sys
from typing import Dict, List, Optional, Tuple, Any

from .datastore import DataStore, DataStoreError, DataStoreRecord

__all__ = ["SessionNormalizer"]


class _RoleInfo:
    role: str
    session_id: str
    session_start_time: float
    desync: float
    desync_uncertainty: float
    user_name: Optional[str]
    # component_name → component_role string (e.g. "sender.pc.grabber")
    component_map: Dict[str, str]
    # topology metadata (protocol, nTiles, etc.)
    topology: Dict[str, Any]

    def __init__(self, role: str) -> None:
        self.role = role
        self.component_map = {}
        self.topology = {}


class SessionNormalizer:
    """
    Phase 1 of the annotation pipeline.

    Validates that all per-role DataStores belong to the same session,
    aligns clocks, converts orchtime→sessiontime, stamps role, drops
    pre-session records, merges, and sorts.

    Also discovers pipeline topology from the raw per-role DataStores
    (while they still contain pre-orchtime structure records) and stores
    the component→component_role mapping in session_metadata so that
    ComponentRoleAnnotation can apply it later without needing the raw data.
    """
    verbose: bool = True

    def __init__(self, datastores: List[Tuple[str, DataStore]], output: DataStore) -> None:
        self._inputs = datastores
        self._output = output

    def normalize(self) -> bool:
        if not self._inputs:
            raise RuntimeError("No datastores to normalize")

        roles: List[_RoleInfo] = []
        for role, ds in self._inputs:
            info = self._collect_role(role, ds)
            roles.append(info)

        session_ids = {r.session_id for r in roles}
        if len(session_ids) > 1:
            raise DataStoreError(f"Session ID mismatch across roles: {session_ids}")

        start_times = [r.session_start_time for r in roles]
        if max(start_times) - min(start_times) > 1:
            print(
                f"Warning: session start times spread {max(start_times) - min(start_times):.1f}s across roles",
                file=sys.stderr,
            )

        for r in roles:
            if abs(r.desync) > 0.030:
                print(
                    f"Warning: {r.role} clock {r.desync:.3f}s (+/- {r.desync_uncertainty / 2:.3f}s) behind orchestrator",
                    file=sys.stderr,
                )

        session_start_time = min(start_times)

        all_data: List[DataStoreRecord] = []
        for info in roles:
            _, ds = next((role_ds for role_ds in self._inputs if role_ds[0] == info.role), (None, None))
            assert ds is not None
            for record in ds.data:
                if "orchtime" not in record:
                    continue
                new_record = dict(record)
                new_record["sessiontime"] = record["orchtime"] - session_start_time
                new_record["role"] = info.role
                all_data.append(new_record)

        self._output.load_data(all_data)
        self._output.sort(key=lambda r: r["sessiontime"])

        self._output.session_metadata = {
            "session_id": roles[0].session_id,
            "session_start_time": session_start_time,
            "roles": [r.role for r in roles],
            "user_names": {r.role: r.user_name for r in roles},
            "desyncs": {r.role: r.desync for r in roles},
            "desync_uncertainties": {r.role: r.desync_uncertainty for r in roles},
            "component_map": {r.role: r.component_map for r in roles},
            "role_topology": {r.role: r.topology for r in roles},
        }

        if self.verbose:
            for r in roles:
                print(f"{r.role}: session_id={r.session_id}, user={r.user_name}, desync={r.desync:.3f}s")
            print(f"Session start: {session_start_time}, roles: {[r.role for r in roles]}")

        return True

    def _collect_role(self, role: str, ds: DataStore) -> _RoleInfo:
        info = _RoleInfo(role)

        r = ds.find_first_record(
            '"starting" in record and component == "OrchestratorController"',
            f"{role} session start",
        )
        info.session_id = r["sessionId"]

        r = ds.find_first_record('component == "SessionPlayerManager"', f"{role} session start time")
        info.session_start_time = r["orchtime"]

        r = ds.find_first_record(
            '"localtime_behind_ms" in record and component == "OrchestratorController"',
            f"{role} session time synchronization",
        )
        info.desync = r["localtime_behind_ms"] / 1000.0
        info.desync_uncertainty = r["uncertainty_interval_ms"] / 1000.0

        try:
            r = ds.find_first_record(
                'component == "SessionPlayerManager" and "userName" in record and self == "True"',
                f"{role} user name",
            )
            info.user_name = r["userName"]
        except DataStoreError:
            info.user_name = None

        self._discover_topology(role, ds, info)
        return info

    def _discover_topology(self, role: str, ds: DataStore, info: _RoleInfo) -> None:
        """Discover pipeline topology for one role and populate info.component_map and info.topology."""
        protocol = None
        try:
            recs = ds.find_all_records('"proto" in record', f"{role} protocol")
            protocol = recs[0]["proto"]
        except DataStoreError:
            pass
        info.topology["protocol"] = protocol

        nTiles = 1
        nQualities = 1
        compressed = False

        # Self (outgoing) PC pipeline
        try:
            r = ds.find_first_record(
                '"PointCloudPipelineSelf" in component and "self" in record and self == 1',
                f"{role} self pc pipeline",
            )
            pipeline = r["component"]
            r2 = ds.find_first_record(
                f'component == "{pipeline}" and "writer" in record',
                f"{role} self pc writer umbrella",
            )
            grabber = r2["reader"]
            encoder = r2["encoder"]
            writer_umbrella = r2["writer"]
            nTiles = r2.get("ntile", 1)
            nQualities = r2.get("nquality", 1)
            compressed = "PCEncoder" in encoder

            info.component_map[grabber] = f"{role}.pc.grabber"
            info.component_map[encoder] = f"{role}.pc.encoder"

            if protocol in ("socketio", "tcpreflector"):
                info.component_map[writer_umbrella] = f"{role}.pc.writer.all"
            else:
                try:
                    writers = ds.find_all_records(
                        f'component == "{writer_umbrella}" and "pusher" in record',
                        f"{role} pc writers",
                    )
                    for wr in writers:
                        pusher = wr["pusher"]
                        if "tile" in wr:
                            tile = wr["tile"] - 1
                        else:
                            tile = wr.get("stream", 0)
                        info.component_map[pusher] = f"{role}.pc.writer.{tile}"
                except DataStoreError:
                    info.component_map[writer_umbrella] = f"{role}.pc.writer.0"

            if self.verbose:
                print(f"{role}: self pc pipeline found: grabber={grabber}, encoder={encoder}, nTiles={nTiles}")
        except DataStoreError:
            pass

        # Self voice pipeline
        try:
            r = ds.find_first_record(
                '"VoicePipelineSelf" in component and "writer" in record',
                f"{role} self voice pipeline",
            )
            info.component_map[r["reader"]] = f"{role}.voice.grabber"
            info.component_map[r["encoder"]] = f"{role}.voice.encoder"
            info.component_map[r["writer"]] = f"{role}.voice.writer"
            if self.verbose:
                print(f"{role}: self voice pipeline found")
        except DataStoreError:
            pass

        # Other (incoming) PC pipeline
        try:
            r = ds.find_first_record(
                '"PointCloudPipelineOther" in component and "self" in record and self == 0',
                f"{role} other pc pipeline",
            )
            pipeline = r["component"]
            r2 = ds.find_first_record(
                f'component == "{pipeline}" and "reader" in record',
                f"{role} other pc reader umbrella",
            )
            reader_umbrella = r2["reader"]
            synchronizer = r2.get("synchronizer")

            if synchronizer:
                info.component_map[synchronizer] = f"{role}.synchronizer"

            # Tile selector
            try:
                r3 = ds.find_first_record(
                    f'"TileSelector" in component and "pipeline" in record and pipeline == "{pipeline}"',
                    f"{role} tile selector",
                )
                info.component_map[r3["component"]] = f"{role}.pc.tileselector"
            except DataStoreError:
                pass

            if "SocketIOReader" in reader_umbrella or "TCPReflectorReader" in reader_umbrella:
                info.component_map[reader_umbrella] = f"{role}.pc.reader.all"
            else:
                try:
                    readers = ds.find_all_records(
                        f'component == "{reader_umbrella}" and "pull_thread" in record',
                        f"{role} pc readers",
                    )
                    for rr in readers:
                        tile = rr["tile"]
                        if "Sub" in reader_umbrella:
                            tile = tile - 1
                        info.component_map[rr["pull_thread"]] = f"{role}.pc.reader.{tile}"
                except DataStoreError:
                    info.component_map[reader_umbrella] = f"{role}.pc.reader.0"

            try:
                decoders = ds.find_all_records(
                    f'component == "{pipeline}" and "decoder" in record',
                    f"{role} pc decoders",
                )
                for rr in decoders:
                    info.component_map[rr["decoder"]] = f"{role}.pc.decoder.{rr['tile']}"
            except DataStoreError:
                pass

            try:
                renderers = ds.find_all_records(
                    f'component == "{pipeline}" and "renderer" in record',
                    f"{role} pc preparers and renderers",
                )
                for rr in renderers:
                    info.component_map[rr["preparer"]] = f"{role}.pc.preparer.{rr['tile']}"
                    info.component_map[rr["renderer"]] = f"{role}.pc.renderer.{rr['tile']}"
            except DataStoreError:
                pass

            if self.verbose:
                print(f"{role}: other pc pipeline found: synchronizer={synchronizer}")
        except DataStoreError:
            pass

        # Other voice pipeline
        try:
            r = ds.find_first_record(
                '"VoicePipelineOther" in component and "reader" in record',
                f"{role} other voice pipeline",
            )
            info.component_map[r["component"]] = f"{role}.voice.renderer"
            if "preparer" in r:
                info.component_map[r["preparer"]] = f"{role}.voice.preparer"
            if self.verbose:
                print(f"{role}: other voice pipeline found")
        except DataStoreError:
            pass

        info.topology["nTiles"] = nTiles
        info.topology["nQualities"] = nQualities
        info.topology["compressed"] = compressed
