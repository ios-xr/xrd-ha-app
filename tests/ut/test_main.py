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

import contextlib
import logging
import re
import runpy
import signal
import typing
from concurrent.futures import Future
from ipaddress import IPv4Address, IPv4Network
from types import FrameType
from typing import Any, Callable, Mapping
from unittest import mock

import pytest

from ha_app import __main__
from ha_app.config import (
    AWSActivateVIPActionConfig,
    AWSConfig,
    AWSUpdateRouteTableActionConfig,
    Config,
    GlobalConfig,
    GroupConfig,
)
from ha_app.types import Action, ActionType, VRRPEvent, VRRPSession, VRRPState
from tests.utils import parametrize_with_namedtuples


logger = logging.getLogger(__name__)


@pytest.fixture
def registered_actions() -> Mapping[VRRPSession, Action]:
    return {
        VRRPSession("GigabitEthernet0/0/0/0", 1): Action(
            ActionType.AWS_ACTIVATE_VIP, mock.Mock(), kwarg1=1
        ),
        VRRPSession("HundredGigE0/0/0/1", 2): Action(
            ActionType.AWS_UPDATE_ROUTE_TABLE, mock.Mock()
        ),
    }


@pytest.fixture(autouse=True)
def vrrp_states(
    registered_actions: Mapping[VRRPSession, VRRPState]
) -> dict[VRRPSession, VRRPState]:
    mock_state = {k: VRRPState.INACTIVE for k in registered_actions}
    with mock.patch.object(__main__, "VRRP_STATES", mock_state):
        yield mock_state


@pytest.fixture
def valid_config() -> Config:
    return Config(
        groups=[
            GroupConfig(
                xr_interface="HundredGigE0/0/0/1",
                vrid=1,
                action=AWSActivateVIPActionConfig(
                    type=ActionType.AWS_ACTIVATE_VIP,
                    device_index=1,
                    vip=IPv4Address("10.0.2.100"),
                ),
            ),
            GroupConfig(
                xr_interface="HundredGigE0/0/0/2",
                vrid=2,
                action=AWSUpdateRouteTableActionConfig(
                    type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                    route_table_id="rtb-55555",
                    destination=IPv4Network("10.0.2.0/24"),
                    target_network_interface="eni-66666",
                ),
            ),
        ]
    )


aws_client_mock = mock.Mock()


@pytest.fixture(autouse=True)
def aws_client() -> mock.Mock:
    with mock.patch("ha_app.aws.AWSClient", aws_client_mock):
        yield aws_client_mock
    aws_client_mock.reset_mock()


@pytest.fixture
def alarm_as_ctrl_c():
    """Set the alarm signal handler to raise KeyboardInterrupt."""

    def alarm_handler(signum: int, frame: FrameType):
        logger.debug("Received alarm (SIGALRM), simulating Ctrl+C")
        raise KeyboardInterrupt

    signal.signal(signal.SIGALRM, alarm_handler)
    yield
    signal.signal(signal.SIGALRM, signal.SIG_DFL)


@pytest.fixture
def consistency_check_single_iteration() -> Callable:
    """Set up mocks such that the consistency check event loop only runs once."""

    class MockEventLoopBreakout(Exception):
        pass

    def mocked_consistency_check(*args, **kwargs) -> None:
        try:
            __main__.start_consistency_check_event_loop(*args, **kwargs)
        except MockEventLoopBreakout:
            pass
        else:
            assert False

    with mock.patch("time.sleep", side_effect=[None, MockEventLoopBreakout]):
        yield mocked_consistency_check


class TestVRRPHandler:
    """Tests for the vrrp_handler function."""

    thread_pool_full = False

    @pytest.fixture(autouse=True)
    def _reset_thread_pool(self) -> None:
        """Reset the thread pool mocking."""
        self.thread_pool_full = False

    @pytest.fixture(autouse=True)
    def mock_thread_submit(self) -> mock.Mock:
        """Mock the thread pool's submit method."""

        def fake_thread_submit(func: Callable, *args, **kwargs) -> Future:
            try:
                func(*args, **kwargs)
            except Exception:
                pass
            return mock.Mock(
                wraps=Future,
                running=mock.Mock(return_value=not self.thread_pool_full),
                done=mock.Mock(return_value=False),
            )

        with mock.patch.object(
            __main__.THREAD_POOL, "submit", side_effect=fake_thread_submit
        ) as mock_submit:
            yield mock_submit

    def test_unregistered_event(
        self,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test an event being received for an unregistered VRRP session."""
        initial_state = vrrp_states.copy()
        event = VRRPEvent(VRRPSession("foo", 0), VRRPState.ACTIVE)
        __main__.vrrp_handler(event, actions=registered_actions)
        mock_thread_submit.assert_not_called()
        assert vrrp_states == initial_state

    def test_go_inactive_event(
        self,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test an inactive event being received for an active VRRP session."""
        session = VRRPSession("GigabitEthernet0/0/0/0", 1)
        vrrp_states[session] = VRRPState.ACTIVE
        event = VRRPEvent(session, VRRPState.INACTIVE)
        __main__.vrrp_handler(event, actions=registered_actions)
        mock_thread_submit.assert_not_called()
        assert vrrp_states[session] is VRRPState.INACTIVE

    def test_remain_inactive_event(
        self,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test an inactive event being received for an inactive VRRP session."""
        session = VRRPSession("GigabitEthernet0/0/0/0", 1)
        vrrp_states[session] = VRRPState.INACTIVE
        event = VRRPEvent(session, VRRPState.INACTIVE)
        __main__.vrrp_handler(event, actions=registered_actions)
        mock_thread_submit.assert_not_called()
        assert vrrp_states[session] is VRRPState.INACTIVE

    def test_remain_active_event(
        self,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test an active event being received for an active VRRP session."""
        session = VRRPSession("GigabitEthernet0/0/0/0", 1)
        vrrp_states[session] = VRRPState.ACTIVE
        event = VRRPEvent(session, VRRPState.ACTIVE)
        __main__.vrrp_handler(event, actions=registered_actions)
        mock_thread_submit.assert_not_called()
        assert vrrp_states[session] is VRRPState.ACTIVE

    def test_go_active_event(
        self,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test an active event being received for an inactive VRRP session."""
        session = VRRPSession("GigabitEthernet0/0/0/0", 1)
        vrrp_states[session] = VRRPState.INACTIVE
        event = VRRPEvent(session, VRRPState.ACTIVE)
        __main__.vrrp_handler(event, actions=registered_actions)
        mock_thread_submit.assert_called_once()
        registered_actions[session].func.assert_called_once_with(
            kwarg1=1, precheck=False
        )
        assert vrrp_states[session] is VRRPState.ACTIVE

    def test_go_active_exception(
        self,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test a go-active thread hitting an exception."""
        session = VRRPSession("GigabitEthernet0/0/0/0", 1)
        action = registered_actions[session]
        action.func: mock.Mock
        action.func.side_effect = Exception("Testing thread hitting exception!")
        vrrp_states[session] = VRRPState.INACTIVE
        event = VRRPEvent(session, VRRPState.ACTIVE)
        __main__.vrrp_handler(event, actions=registered_actions)
        mock_thread_submit.assert_called_once()
        action.func.assert_called_once_with(kwarg1=1, precheck=False)
        assert vrrp_states[session] is VRRPState.ACTIVE

    def test_go_active_pool_full(
        self,
        caplog: pytest.LogCaptureFixture,
        vrrp_states: dict[VRRPSession, VRRPState],
        registered_actions: Mapping[VRRPSession, Action],
        mock_thread_submit: mock.Mock,
    ):
        """Test an active event being received for an inactive VRRP session."""
        session = VRRPSession("GigabitEthernet0/0/0/0", 1)
        vrrp_states[session] = VRRPState.INACTIVE
        event = VRRPEvent(session, VRRPState.ACTIVE)
        self.thread_pool_full = True
        __main__.vrrp_handler(event, actions=registered_actions)
        assert (
            "Thread pool for performing actions is full, go-active events may be delayed"
            in caplog.messages
        )


class TestDisconnectHandler:
    """Tests for the disconnect_handler() function."""

    def test_handler(self, vrrp_states: dict[VRRPSession, VRRPState]):
        vrrp_states[VRRPSession("GigabitEthernet0/0/0/0", 1)] = VRRPState.ACTIVE
        __main__.disconnect_handler()
        assert all(s is VRRPState.INACTIVE for s in vrrp_states.values())


class GetActionsFromConfigTestParams(typing.NamedTuple):
    input_config: Config
    exp_actions: Mapping[VRRPSession, Action]
    aws_client_kwargs: Mapping[str, Any] = {}


get_actions_from_config_testcases = {
    "empty": GetActionsFromConfigTestParams(
        input_config=Config(groups=[]), exp_actions={}
    ),
    "single_vip": GetActionsFromConfigTestParams(
        input_config=Config(
            groups=[
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/1",
                    vrid=1,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=1,
                        vip=IPv4Address("10.0.2.100"),
                    ),
                )
            ],
        ),
        exp_actions={
            VRRPSession("HundredGigE0/0/0/1", 1): Action(
                ActionType.AWS_ACTIVATE_VIP,
                aws_client_mock.return_value.assign_vip,
                device_index=1,
                ip_addr=IPv4Address("10.0.2.100"),
            )
        },
    ),
    "single_route": GetActionsFromConfigTestParams(
        input_config=Config(
            groups=[
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/2",
                    vrid=2,
                    action=AWSUpdateRouteTableActionConfig(
                        type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                        route_table_id="rtb-ec081d94",
                        destination=IPv4Network("10.0.2.0/24"),
                        target_network_interface="eni-7c90349273e5a5db",
                    ),
                )
            ],
        ),
        exp_actions={
            VRRPSession("HundredGigE0/0/0/2", 2): Action(
                ActionType.AWS_UPDATE_ROUTE_TABLE,
                aws_client_mock.return_value.update_route_table,
                route_table_id="rtb-ec081d94",
                destination=IPv4Network("10.0.2.0/24"),
                target_network_interface="eni-7c90349273e5a5db",
            )
        },
    ),
    "many": GetActionsFromConfigTestParams(
        input_config=Config(
            groups=[
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/1",
                    vrid=1,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=1,
                        vip=IPv4Address("10.0.1.100"),
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/1",
                    vrid=2,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=2,
                        vip=IPv4Address("10.0.1.200"),
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/2",
                    vrid=2,
                    action=AWSActivateVIPActionConfig(
                        type=ActionType.AWS_ACTIVATE_VIP,
                        device_index=2,
                        vip=IPv4Address("10.0.2.100"),
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/11",
                    vrid=11,
                    action=AWSUpdateRouteTableActionConfig(
                        type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                        route_table_id="rtb-123",
                        destination=IPv4Network("10.0.2.0/24"),
                        target_network_interface="eni-7c90349273e5a5db",
                    ),
                ),
                GroupConfig(
                    xr_interface="HundredGigE0/0/0/12",
                    vrid=12,
                    action=AWSUpdateRouteTableActionConfig(
                        type=ActionType.AWS_UPDATE_ROUTE_TABLE,
                        route_table_id="rtb-456",
                        destination=IPv4Network("22.22.0.0/20"),
                        target_network_interface="eni-03d03cf989c6b48c",
                    ),
                ),
            ],
        ),
        exp_actions={
            VRRPSession("HundredGigE0/0/0/1", 1): Action(
                ActionType.AWS_ACTIVATE_VIP,
                aws_client_mock.return_value.assign_vip,
                device_index=1,
                ip_addr=IPv4Address("10.0.1.100"),
            ),
            VRRPSession("HundredGigE0/0/0/1", 2): Action(
                ActionType.AWS_ACTIVATE_VIP,
                aws_client_mock.return_value.assign_vip,
                device_index=2,
                ip_addr=IPv4Address("10.0.1.200"),
            ),
            VRRPSession("HundredGigE0/0/0/2", 2): Action(
                ActionType.AWS_ACTIVATE_VIP,
                aws_client_mock.return_value.assign_vip,
                device_index=2,
                ip_addr=IPv4Address("10.0.2.100"),
            ),
            VRRPSession("HundredGigE0/0/0/11", 11): Action(
                ActionType.AWS_UPDATE_ROUTE_TABLE,
                aws_client_mock.return_value.update_route_table,
                route_table_id="rtb-123",
                destination=IPv4Network("10.0.2.0/24"),
                target_network_interface="eni-7c90349273e5a5db",
            ),
            VRRPSession("HundredGigE0/0/0/12", 12): Action(
                ActionType.AWS_UPDATE_ROUTE_TABLE,
                aws_client_mock.return_value.update_route_table,
                route_table_id="rtb-456",
                destination=IPv4Network("22.22.0.0/20"),
                target_network_interface="eni-03d03cf989c6b48c",
            ),
        },
    ),
    "aws_endpoint": GetActionsFromConfigTestParams(
        input_config=Config(
            **{
                "global": GlobalConfig(
                    aws=AWSConfig(
                        ec2_private_endpoint_url="https://vpce-1234.ec2.us-west-2.vpce.amazonaws.com"
                    )
                ),
                "groups": [
                    GroupConfig(
                        xr_interface="HundredGigE0/0/0/1",
                        vrid=1,
                        action=AWSActivateVIPActionConfig(
                            type=ActionType.AWS_ACTIVATE_VIP,
                            device_index=1,
                            vip=IPv4Address("10.0.2.100"),
                        ),
                    )
                ],
            }
        ),
        exp_actions={
            VRRPSession("HundredGigE0/0/0/1", 1): Action(
                ActionType.AWS_ACTIVATE_VIP,
                aws_client_mock.return_value.assign_vip,
                device_index=1,
                ip_addr=IPv4Address("10.0.2.100"),
            )
        },
        aws_client_kwargs=dict(
            endpoint_url="https://vpce-1234.ec2.us-west-2.vpce.amazonaws.com"
        ),
    ),
}


@parametrize_with_namedtuples(get_actions_from_config_testcases)
def test_parse_config(
    input_config: Config,
    exp_actions: Mapping[VRRPSession, Action],
    aws_client_kwargs: Mapping[str, Any],
    aws_client: mock.Mock,
):
    """Test using config to initialise the registered actions."""
    actual_actions = __main__.get_actions_from_config(input_config)
    assert actual_actions == exp_actions
    if exp_actions:
        aws_client.assert_called_once_with(**aws_client_kwargs)


def test_consistency_check_success(
    registered_actions: Mapping[VRRPSession, Action],
    vrrp_states: dict[VRRPSession, VRRPState],
    consistency_check_single_iteration,
) -> None:
    """Test the consistency check event loop in success flow."""
    session = VRRPSession("GigabitEthernet0/0/0/0", 1)
    vrrp_states[session] = VRRPState.ACTIVE
    action = registered_actions[session]

    consistency_check_single_iteration(registered_actions, 10)

    action.func.assert_called_once_with(kwarg1=1, precheck=True)


def test_consistency_check_error(
    caplog: pytest.LogCaptureFixture,
    registered_actions: Mapping[VRRPSession, Action],
    vrrp_states: dict[VRRPSession, VRRPState],
    consistency_check_single_iteration,
) -> None:
    """Test the consistency check event loop in error performing action."""

    session = VRRPSession("GigabitEthernet0/0/0/0", 1)
    vrrp_states[session] = VRRPState.ACTIVE
    action = registered_actions[session]
    action.func.side_effect = Exception("Test-induced exception!")

    with caplog.at_level(logging.ERROR, logger="ha_app"):
        consistency_check_single_iteration(registered_actions, 10)

    action.func.assert_called_once_with(kwarg1=1, precheck=True)
    assert len(caplog.records) == 1
    assert caplog.messages[0] == (
        "Hit an error trying to perform consistency check action "
        "'aws_activate_vip' on <xr_interface=GigabitEthernet0/0/0/0,vrid=1>"
    )


def test_startup_flow_success(
    capsys: pytest.CaptureFixture, valid_config: Config, alarm_as_ctrl_c
):
    """Test the main startup flow, with expected module API calls."""
    with contextlib.ExitStack() as ctxs:
        ctxs.enter_context(mock.patch("sys.argv", ["ha_app"]))
        mock_config = ctxs.enter_context(
            mock.patch("ha_app.config.Config.from_file", return_value=valid_config)
        )
        mock_aws_cls = ctxs.enter_context(mock.patch("ha_app.aws.AWSClient"))
        mock_aws_client = mock_aws_cls.return_value
        mock_telem_listen = ctxs.enter_context(mock.patch("ha_app.telem.listen"))

        signal.alarm(1)  # Simulate Ctrl+C from event loop
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")

        assert exc_info.value.code == 130
        mock_config.assert_called_once_with("/etc/ha_app/config.yaml")
        mock_aws_cls.assert_called_once()
        mock_aws_client.get_indexed_eni.assert_called_once_with(1)
        mock_aws_client.get_route_table.assert_called_once_with("rtb-55555")
        mock_aws_client.get_eni.assert_called_once_with("eni-66666")
        mock_telem_listen.assert_called_once()

    stderr = capsys.readouterr().err
    assert re.search(r"INFO.*Exiting on Ctrl\+C\n", stderr)


def test_config_parse_error(capsys: pytest.CaptureFixture):
    """Test hitting an error at config parsing."""
    with contextlib.ExitStack() as ctxs:
        ctxs.enter_context(mock.patch("sys.argv", ["ha_app"]))
        mock_config = ctxs.enter_context(
            mock.patch("ha_app.config.Config.from_file", side_effect=FileNotFoundError)
        )
        mock_aws_client = ctxs.enter_context(mock.patch("ha_app.aws.AWSClient"))
        mock_telem_listen = ctxs.enter_context(mock.patch("ha_app.telem.listen"))

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")

        assert exc_info.value.code == 2
        mock_config.assert_called_once_with("/etc/ha_app/config.yaml")
        mock_aws_client.assert_not_called()
        mock_telem_listen.assert_not_called()

    stderr = capsys.readouterr().err
    assert re.search(r"ERROR.*Initialisation error:\n", stderr)
    assert "\nInitError: Error reading config file\n" in stderr
    assert "\nFileNotFoundError\n" in stderr


def test_unexpected_error_exit(capsys: pytest.CaptureFixture, valid_config: Config):
    """
    Test an unexpected error causing the main thread to exit.

    The error is injected when the consistency checks start, after the main
    initialisation flow has completed.
    """
    with contextlib.ExitStack() as ctxs:
        ctxs.enter_context(mock.patch("sys.argv", ["ha_app"]))
        mock_thread_pool = mock.Mock()
        ctxs.enter_context(
            mock.patch(
                "concurrent.futures.ThreadPoolExecutor", return_value=mock_thread_pool
            )
        )
        mock_config = ctxs.enter_context(
            mock.patch("ha_app.config.Config.from_file", return_value=valid_config)
        )
        mock_subprocess = ctxs.enter_context(mock.patch("subprocess.check_output"))
        mock_aws_client = ctxs.enter_context(mock.patch("ha_app.aws.AWSClient"))
        mock_server = mock.Mock()
        mock_telem_listen = ctxs.enter_context(
            mock.patch("ha_app.telem.listen", return_value=mock_server)
        )
        mock_sleep = ctxs.enter_context(
            mock.patch(
                "time.sleep", side_effect=Exception("Mock time.sleep() exception")
            )
        )

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")

        assert exc_info.value.code == 1

        mock_config.assert_called_once()
        mock_subprocess.assert_called_once()
        mock_aws_client.assert_called_once()
        mock_telem_listen.assert_called_once()
        mock_sleep.assert_called_once()
        # Check cleanup was performed.
        mock_thread_pool.shutdown.assert_called_once()
        mock_server.stop.assert_called_once()

    stderr = capsys.readouterr().err
    assert re.search(r"ERROR.*Exiting on unexpected error:\n", stderr)
    assert "\nException: Mock time.sleep() exception\n" in stderr


def test_get_actions_error(capsys: pytest.CaptureFixture, valid_config: Config):
    """Test hitting an error getting actions from config."""
    with contextlib.ExitStack() as ctxs:
        ctxs.enter_context(mock.patch("sys.argv", ["ha_app"]))
        mock_config = ctxs.enter_context(
            mock.patch("ha_app.config.Config.from_file", return_value=valid_config)
        )
        mock_aws_client = ctxs.enter_context(
            mock.patch(
                "ha_app.aws.AWSClient",
                side_effect=Exception("Mock AWSClient exception"),
            )
        )
        mock_telem_listen = ctxs.enter_context(mock.patch("ha_app.telem.listen"))

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")

        assert exc_info.value.code == 2
        mock_config.assert_called_once_with("/etc/ha_app/config.yaml")
        mock_aws_client.assert_called_once()
        mock_telem_listen.assert_not_called()

    stderr = capsys.readouterr().err
    assert re.search(r"ERROR.*Initialisation error:\n", stderr)
    assert "\nInitError: Error validating config: Mock AWSClient exception\n" in stderr
    assert "\nException: Mock AWSClient exception\n" in stderr


def test_telem_listen_error(capsys: pytest.CaptureFixture, valid_config: Config):
    """Test hitting an error calling telem.listen()."""
    with contextlib.ExitStack() as ctxs:
        ctxs.enter_context(mock.patch("sys.argv", ["ha_app"]))
        mock_config = ctxs.enter_context(
            mock.patch("ha_app.config.Config.from_file", return_value=valid_config)
        )
        mock_aws_client = ctxs.enter_context(mock.patch("ha_app.aws.AWSClient"))
        mock_telem_listen = ctxs.enter_context(
            mock.patch(
                "ha_app.telem.listen",
                side_effect=Exception("Mock telem.listen() exception"),
            )
        )

        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")

        assert exc_info.value.code == 2
        mock_config.assert_called_once_with("/etc/ha_app/config.yaml")
        mock_aws_client.assert_called_once()
        mock_telem_listen.assert_called_once()

    stderr = capsys.readouterr().err
    assert re.search(r"ERROR.*Initialisation error:\n", stderr)
    assert "\nInitError: Error starting gRPC telemetry server\n" in stderr
    assert "\nException: Mock telem.listen() exception\n" in stderr


def test_help_output():
    """Test that help output is supported."""
    with mock.patch("sys.argv", ["ha_app", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")
    assert exc_info.value.code == 0


def test_version_output(capsys: pytest.CaptureFixture):
    """Test getting the app version."""
    with mock.patch("sys.argv", ["ha_app", "--version"]):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ha_app", run_name="__main__")
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.rstrip() == __main__.__version__
