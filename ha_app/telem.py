# Copyright 2023 Cisco Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
XRd HA app telemetry module, passing through received VRRP telemetry events.
"""

__all__ = ("listen",)

import json
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Iterator

import google.protobuf
import grpc

from .gpb import cisco_grpc_dialout_pb2_grpc as dialout_pb2_grpc
from .gpb.cisco_grpc_dialout_pb2 import MdtDialoutArgs
from .gpb.telemetry_pb2 import Telemetry, TelemetryField
from .types import VRRPEvent, VRRPSession, VRRPState


logger = logging.getLogger(__name__)


def _gpbkv_get_field(gpbkv: Iterable[TelemetryField], field: str) -> TelemetryField:
    """
    Get a field from a GPB key-value iterable.

    Example:
    gpbkv = [
        TelemetryField(name="interface-name", string_value="Hun0/0/0/1"),
        TelemetryField(name="virtual-router-id", uint32_value=1),
    ]
    field = "interface-name"
    ->
    TelemetryField(name="interface-name", string_value="Hun0/0/0/1")

    :param gpbkv:
        The GPB key-value iterable to find the field in.
    :param field:
        The field name to look for.
    :raise KeyError:

    :return:
    """
    for f in gpbkv:
        if f.name == field:
            break
    else:
        raise KeyError(f"Field {field!r} not found in the gpbkv data")
    return f


class VRRPServicer(dialout_pb2_grpc.gRPCMdtDialoutServicer):
    """gRPC servicer for handling VRRP telemetry events."""

    def __init__(
        self,
        msg_handler: Callable[[VRRPEvent], None],
        disconnect_handler: Callable[[], None],
    ):
        """
        :param msg_handler:
            The callback to invoke on receiving VRRP events.
        :param disconnect_handler:
            The callback to invoke on the client connection being dropped.
        """
        self._msg_handler = msg_handler
        self._disconnect_handler = disconnect_handler
        # Use deque so that we can restrict the size to mitigate possible
        # memory exhaustion DoS attack.
        self._unexpected_received_paths: deque[str] = deque(maxlen=10)

    def MdtDialout(
        self,
        request_iterator: Iterator[MdtDialoutArgs],
        context: grpc.ServicerContext,
    ) -> Iterator[MdtDialoutArgs]:
        """
        The MdtDialout RPC method, as defined in cisco_grpc_dialout.proto.

        :param request_iterator:
            An iterator that yields MdtDialoutArgs messages until the connection
            is closed.
        :param context:
            Connection context.
        :return:
            Iterator of MdtDialoutArgs (unused, always empty).
        """
        _, dialout_ip, dialout_port = context.peer().split(":")  # Assumes IPv4
        peer = f"{dialout_ip}:{dialout_port}"
        logger.info("Connection established with gRPC peer: %s", peer)
        try:
            for msg in request_iterator:
                self._handle_msg(msg)
        except grpc.RpcError:
            logger.info("Connection lost with gRPC peer %s", peer)
            self._disconnect_handler()
            raise
        except Exception:
            # Don't log traceback as it will be logged by the grpcio library.
            logger.error("Unexpected exception in MdtDialout from gRPC peer %s", peer)
            self._disconnect_handler()
            raise
        logger.info("Connection closed by gRPC peer %s", peer)
        self._disconnect_handler()

        return iter(())

    def _handle_msg(self, msg: MdtDialoutArgs) -> None:
        """Handle an MdtDialout message."""
        try:
            telemetry_msg = Telemetry()
            telemetry_msg.ParseFromString(msg.data)
        except google.protobuf.message.DecodeError:
            try:
                json.loads(msg.data)
            except json.JSONDecodeError:
                pass  # Reraise original exception
            else:
                logger.warning(
                    "Ignoring message with JSON payload, "
                    "only self-describing-gpb encoding is supported",
                )
                return
            raise
        else:
            self._handle_telemetry_msg(telemetry_msg)

    def _handle_telemetry_msg(self, msg: Telemetry) -> None:
        """Handle an arbitrary telemetry message."""
        if (
            msg.encoding_path
            == "Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router"
        ):
            if not msg.data_gpbkv:
                logger.warning(
                    "Ignoring telemetry message on path %r without gpbkv data, "
                    "only self-describing-gpb encoding is supported",
                    msg.encoding_path,
                )
                return
            self._handle_vrrp_msg(msg)
        elif msg.encoding_path not in self._unexpected_received_paths:
            logger.warning(
                "Received unexpected telemetry message with path %r "
                "(subsequent messages will be silently dropped)",
                msg.encoding_path,
            )
            self._unexpected_received_paths.append(msg.encoding_path)

    def _handle_vrrp_msg(self, msg: Telemetry) -> None:
        """Handle an VRRP telemetry message."""
        for session in msg.data_gpbkv:
            try:
                keys = _gpbkv_get_field(session.fields, "keys").fields
                content = _gpbkv_get_field(session.fields, "content").fields
                intf_name = _gpbkv_get_field(keys, "interface-name").string_value
                vrid = _gpbkv_get_field(keys, "virtual-router-id").uint32_value
                state = (
                    VRRPState.ACTIVE
                    if _gpbkv_get_field(content, "vrrp-state").string_value
                    == "state-master"
                    else VRRPState.INACTIVE
                )
                event = VRRPEvent(VRRPSession(intf_name, vrid), state)
            except Exception:
                logger.error(
                    "VRRP session data has unexpected structure",
                    exc_info=True,
                )
            else:
                self._msg_handler(event)


def listen(
    thread_pool: ThreadPoolExecutor,
    *,
    vrrp_handler: Callable[[VRRPEvent], None],
    disconnect_handler: Callable[[], None],
    port: int,
) -> grpc.Server:
    """
    Register a gRPC servicer for handling VRRP telemetry events.

    :param thread_pool:
        A thread pool to use for handling events.
    :param vrrp_handler:
        The callback to invoke on receiving VRRP events.
    :param disconnect_handler:
        The callback to invoke on the client connection being dropped.
    :param port:
        The port to listen on.
    :return:
        The server object, for which a reference must be kept to avoid GC.
    """
    # Create the gRPC server with the following options are used:
    #  * maximum_concurrent_rpcs=1
    #      only expect one connection (the paired XRd vRouter instance)
    #  * grpc.keepalive_time_ms=1000
    #      1 second interval for keepalives, to detect connection loss quickly
    #  * grpc.keepalive_timeout_ms=1000
    #      1 second keepalive timeout, to detect connection loss quickly
    server = grpc.server(
        thread_pool,
        maximum_concurrent_rpcs=1,
        options=(
            ("grpc.keepalive_time_ms", 1000),
            ("grpc.keepalive_timeout_ms", 1000),
        ),
    )
    dialout_pb2_grpc.add_gRPCMdtDialoutServicer_to_server(
        VRRPServicer(vrrp_handler, disconnect_handler),
        server,
    )
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    logger.info("Listening on port %d...", port)
    return server
