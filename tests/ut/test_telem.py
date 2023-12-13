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

import logging
from unittest import mock

import google.protobuf.message
import grpc
import pytest

from ha_app import telem
from ha_app.gpb.cisco_grpc_dialout_pb2 import MdtDialoutArgs
from ha_app.gpb.telemetry_pb2 import Telemetry, TelemetryField
from ha_app.types import VRRPEvent, VRRPSession, VRRPState


@pytest.fixture
def grpc_context() -> mock.Mock:
    return mock.Mock(peer=mock.Mock(return_value="ipv4:1.2.3.4:56789"))


def _create_msg_from_telemetry(telem_msg: Telemetry) -> MdtDialoutArgs:
    return MdtDialoutArgs(ReqId=1, data=telem_msg.SerializePartialToString())


def _create_msg_from_gpbkv(gpbkv: list[TelemetryField]) -> MdtDialoutArgs:
    telem_msg = Telemetry(
        subscription_id_str="sub-vrrp",
        encoding_path="Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
        collection_start_time=1679657395741,
        collection_end_time=1679657855771,
        msg_timestamp=1679657395741,
        data_gpbkv=gpbkv,
    )
    return _create_msg_from_telemetry(telem_msg)


def _create_msg(intf_name: str, vrid: int, state: str) -> MdtDialoutArgs:
    """Create a telemetry message to be sent into the MdtDialout RPC."""
    gpbkv_msg = TelemetryField(
        timestamp=1679657855766,
        fields=[
            TelemetryField(
                name="keys",
                fields=[
                    TelemetryField(
                        name="interface-name",
                        string_value=intf_name,
                    ),
                    TelemetryField(
                        name="virtual-router-id",
                        uint32_value=vrid,
                    ),
                ],
            ),
            TelemetryField(
                name="content",
                fields=[
                    TelemetryField(
                        name="vrrp-state",
                        string_value=f"state-{state}",
                    ),
                    TelemetryField(
                        name="interface-name-xr",
                        string_value=intf_name,
                    ),
                    TelemetryField(
                        name="virtual-router-id-xr",
                        uint32_value=vrid,
                    ),
                ],
            ),
        ],
    )
    return _create_msg_from_gpbkv([gpbkv_msg])


def test_vrrp_single_msg_active(grpc_context: mock.Mock):
    """Test a single 'active' message being sent."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)

    grpc_servicer.MdtDialout(
        iter([_create_msg("test-intf", 1, "master")]),
        grpc_context,
    )

    msg_handler.assert_called_once_with(
        VRRPEvent(VRRPSession("test-intf", 1), VRRPState.ACTIVE)
    )
    disconnect_handler.assert_called_once()


def test_vrrp_single_msg_inactive(grpc_context: mock.Mock):
    """Test a single 'inactive' message being sent."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)

    grpc_servicer.MdtDialout(
        iter([_create_msg("test-intf", 1, "backup")]),
        grpc_context,
    )

    msg_handler.assert_called_once_with(
        VRRPEvent(VRRPSession("test-intf", 1), VRRPState.INACTIVE)
    )
    disconnect_handler.assert_called_once()


def test_vrrp_msg_iterator(grpc_context: mock.Mock):
    """Test multiple messages being sent via an iterator."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)

    def msg_iterator():
        msg_handler.assert_not_called()
        yield _create_msg("HundredGigE0/0/0/1", 1, "init")
        msg_handler.assert_called_once_with(
            VRRPEvent(VRRPSession("HundredGigE0/0/0/1", 1), VRRPState.INACTIVE)
        )
        msg_handler.reset_mock()
        yield _create_msg("HundredGigE0/0/0/2", 2, "master")
        msg_handler.assert_called_once_with(
            VRRPEvent(VRRPSession("HundredGigE0/0/0/2", 2), VRRPState.ACTIVE)
        )
        msg_handler.reset_mock()
        yield _create_msg("HundredGigE0/0/0/2", 2, "backup")
        msg_handler.assert_called_once_with(
            VRRPEvent(VRRPSession("HundredGigE0/0/0/2", 2), VRRPState.INACTIVE)
        )
        msg_handler.reset_mock()
        disconnect_handler.assert_not_called()

    grpc_servicer.MdtDialout(msg_iterator(), grpc_context)
    # The disconnect happens at the completion of message iteration.
    disconnect_handler.assert_called_once()


def test_connection_closed(grpc_context: mock.Mock):
    """Test the connection being closed by the client side."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)

    def msg_iterator():
        msg_handler.assert_not_called()
        yield _create_msg("HundredGigE0/0/0/1", 1, "init")
        msg_handler.assert_called_once_with(
            VRRPEvent(VRRPSession("HundredGigE0/0/0/1", 1), VRRPState.INACTIVE)
        )
        msg_handler.reset_mock()
        disconnect_handler.assert_not_called()
        raise grpc.RpcError

    with pytest.raises(grpc.RpcError):
        grpc_servicer.MdtDialout(msg_iterator(), grpc_context)

    # The disconnect happens when the connection is closed.
    disconnect_handler.assert_called_once()


def test_unexpected_empty_vrrp_msg(
    grpc_context: mock.Mock, caplog: pytest.LogCaptureFixture
):
    """Test an unexpected empty VRRP telemetry message, ignored with a warning."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)
    msg = _create_msg_from_gpbkv([])

    with caplog.at_level(logging.WARNING, "ha_app.telem"):
        grpc_servicer.MdtDialout(iter([msg]), grpc_context)

    assert len(caplog.records) == 1
    msg_handler.assert_not_called()
    disconnect_handler.assert_called_once()


def test_unexpected_telemetry_msg_path(
    grpc_context: mock.Mock, caplog: pytest.LogCaptureFixture
):
    """Test an unexpected telemetry message, ignored with a single warning."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)
    msg = _create_msg_from_telemetry(
        Telemetry(encoding_path="Cisco-IOS-XR-infra-syslog-oper:syslog/messages")
    )

    with caplog.at_level(logging.WARNING, "ha_app.telem"):
        grpc_servicer.MdtDialout(iter([msg, msg, msg]), grpc_context)

    # Only logged the first time for unexpected encoding path.
    assert len(caplog.records) == 1
    msg_handler.assert_not_called()
    disconnect_handler.assert_called_once()


def test_many_unexpected_telemetry_msg_paths(
    grpc_context: mock.Mock, caplog: pytest.LogCaptureFixture
):
    """Test lots of unexpected telemetry messages."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)
    msgs = [
        _create_msg_from_telemetry(Telemetry(encoding_path=p))
        for p in (
            "0",  # 10 paths to fill the deque
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "foo",  # Drop '0' from the deque
            "foo",  # No warning
            "2",  # No warning
            "1",  # No warning
            "0",  # Warn, back in the deque, drop '1'
            "1",  # Now warns
        )
    ]

    with caplog.at_level(logging.WARNING, "ha_app.telem"):
        grpc_servicer.MdtDialout(iter(msgs), grpc_context)

    assert caplog.messages == [
        "Received unexpected telemetry message with path '0' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '1' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '2' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '3' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '4' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '5' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '6' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '7' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '8' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '9' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path 'foo' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '0' (subsequent messages will be silently dropped)",
        "Received unexpected telemetry message with path '1' (subsequent messages will be silently dropped)",
    ]
    msg_handler.assert_not_called()
    disconnect_handler.assert_called_once()


def test_invalid_vrrp_msg(grpc_context: mock.Mock, caplog: pytest.LogCaptureFixture):
    """Test an invalid VRRP telemetry message, ignored with a warning."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)
    msg = _create_msg_from_gpbkv([TelemetryField()])

    with caplog.at_level(logging.WARNING, "ha_app.telem"):
        grpc_servicer.MdtDialout(iter([msg]), grpc_context)

    assert len(caplog.records) == 1
    msg_handler.assert_not_called()
    disconnect_handler.assert_called_once()


def test_json_msg_payload(grpc_context: mock.Mock, caplog: pytest.LogCaptureFixture):
    """Test a JSON data payload in MdtDialoutArgs, ignored with a warning."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)

    with caplog.at_level(logging.WARNING, "ha_app.telem"):
        grpc_servicer.MdtDialout(iter([MdtDialoutArgs(data=b"{}")]), grpc_context)

    assert len(caplog.records) == 1
    msg_handler.assert_not_called()
    disconnect_handler.assert_called_once()


def test_unexpected_msg_payload(
    grpc_context: mock.Mock, caplog: pytest.LogCaptureFixture
):
    """Test an expected MdtDialoutArgs data payload, closes connection."""
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()
    grpc_servicer = telem.VRRPServicer(msg_handler, disconnect_handler)

    with caplog.at_level(logging.ERROR, "ha_app.telem"):
        with pytest.raises(google.protobuf.message.DecodeError):
            grpc_servicer.MdtDialout(iter([MdtDialoutArgs(data=b"foo")]), grpc_context)

    assert len(caplog.records) == 1
    msg_handler.assert_not_called()
    disconnect_handler.assert_called_once()


def test_listen_api():
    """Test creation of gRPC server when calling listen() API."""
    threadpool = mock.Mock()
    msg_handler = mock.Mock()
    disconnect_handler = mock.Mock()

    with mock.patch("grpc.server") as server_func_mock:
        telem.listen(
            threadpool,
            vrrp_handler=msg_handler,
            disconnect_handler=disconnect_handler,
            port=12345,
        )

    server_func_mock.assert_called_once_with(
        threadpool,
        maximum_concurrent_rpcs=1,
        options=(
            ("grpc.keepalive_time_ms", 1000),
            ("grpc.keepalive_timeout_ms", 1000),
        ),
    )
    server_mock = server_func_mock.return_value
    server_mock.add_insecure_port.assert_has_calls([mock.call("0.0.0.0:12345")])
    server_mock.start.assert_called_once()
