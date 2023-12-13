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
The XRd HA app package entrypoint.
"""

import argparse
import logging
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, Mapping, NoReturn

import grpc

from . import __version__, aws, telem
from .config import AWSActivateVIPActionConfig, AWSUpdateRouteTableActionConfig, Config
from .types import Action, VRRPEvent, VRRPSession, VRRPState


APP_NAME = __package__

logger = logging.getLogger(APP_NAME)

# Thread pool for go-active events, with the number of workers matching the
# maximum number of supported sessions. Also a balance between being able to
# parallelise (up to 8 sessions supported) and avoiding excessive context
# switching.
THREAD_POOL = ThreadPoolExecutor(max_workers=8)

# Global reference to the gRPC telemetry server, to avoid garbage collection.
TELEM_SERVER: grpc.Server | None = None

# The VRRP state associated with each registered VRRP session.
VRRP_STATES: dict[VRRPSession, VRRPState] = {}


class InitError(Exception):
    """Error during initialisation flow."""


def _go_active_action(session: VRRPSession, action: Action) -> None:
    """
    Target function for a go-active thread, logging any exception that occurs.

    :param session:
        The VRRP session the action is being performed for.
    :param action:
        The action to perform.
    """
    logger.info("Go active on %r with %s", session, action.type)
    try:
        action.func(**action.kwargs, precheck=False)
    except Exception:
        logger.exception(
            "Hit exception when performing %s action on %r:", action.type, session
        )
        raise
    else:
        logger.info("Successful go-active on %r", session)


def vrrp_handler(event: VRRPEvent, *, actions: Mapping[VRRPSession, Action]) -> None:
    """
    Callback function for handling VRRP events.

    :param event:
        The VRRP event, i.e. an active/inactive notification.
    :param actions:
        The registered actions, which may be triggered by the event.
    """
    if event.session not in actions:
        logger.debug("Ignoring event for unregistered session %r", event.session)
        return
    logger.debug(
        "Got %s for %r, previously %s",
        event.state.name,
        event.session,
        VRRP_STATES[event.session].name,
    )
    if (
        VRRP_STATES[event.session] is VRRPState.INACTIVE
        and event.state is VRRPState.ACTIVE
    ):
        # Go-active event, performance critical path.
        future = THREAD_POOL.submit(
            _go_active_action, event.session, actions[event.session]
        )
        # Check for thread pool being full, as this is unexpected and may
        # indicate threads getting stuck.
        if not future.running() and not future.done():
            logger.warning(
                "Thread pool for performing actions is full, go-active events "
                "may be delayed"
            )
    VRRP_STATES[event.session] = event.state


def disconnect_handler() -> None:
    """Callback function for handling loss of telemetry connection."""
    logger.debug("Marking all VRRP sessions as inactive")
    for session in VRRP_STATES:
        VRRP_STATES[session] = VRRPState.INACTIVE


def start_consistency_check_event_loop(
    actions: Mapping[VRRPSession, Action], interval: int
) -> NoReturn:
    """
    Enter the consistency check event loop.

    :param actions:
        The registered actions, which may be triggered as part of the checks.
    :param interval:
        How often to perform the consistency check in seconds.
    """
    logger.info("Starting consistency checks every %d seconds", interval)
    last_check_time = time.monotonic()
    while True:
        time_since_last_check = time.monotonic() - last_check_time
        sleep_time = max(1, interval - time_since_last_check)
        time.sleep(sleep_time)

        last_check_time = time.monotonic()
        # Iterate over keys, since values may be changed in another thread.
        for session in VRRP_STATES:  # pylint: disable=consider-using-dict-items
            if VRRP_STATES[session] is VRRPState.ACTIVE:
                logger.debug("Performing consistency check on %r", session)
                try:
                    actions[session].func(**actions[session].kwargs, precheck=True)
                except Exception:
                    logger.exception(
                        "Hit an error trying to perform consistency check "
                        "action '%r' on %r",
                        actions[session].type,
                        session,
                    )


def get_actions_from_config(config: Config) -> Mapping[VRRPSession, Action]:
    """
    Construct objects representing registered actions from app config.

    :param config:
        The app config object.
    :return:
        A mapping from VRRP sessions to their configured action.
    """
    if not config.groups:
        logger.warning("No registered actions found!")
        return {}

    actions: dict[VRRPSession, Action] = {}
    aws_client_kwargs = {}
    if private_endpoint := getattr(
        config.global_.aws, "ec2_private_endpoint_url", None
    ):
        logger.info("Using private EC2 endpoint URL: %s", private_endpoint)
        aws_client_kwargs["endpoint_url"] = private_endpoint
    aws_client = aws.AWSClient(**aws_client_kwargs)

    for grp in config.groups:
        session = VRRPSession(grp.xr_interface, grp.vrid)
        assert (
            session not in actions
        ), "Only one action per VRRP group allowed in config validation"
        action_func: Callable[..., None]  # Must accept kwarg 'precheck: bool'
        action_kwargs: dict[str, Any]
        if isinstance(grp.action, AWSActivateVIPActionConfig):
            # Check the device index is valid.
            aws_client.get_indexed_eni(grp.action.device_index)

            action_func = aws_client.assign_vip
            action_kwargs = dict(
                device_index=grp.action.device_index, ip_addr=grp.action.vip
            )
        elif isinstance(grp.action, AWSUpdateRouteTableActionConfig):
            # Check the route table is valid.
            aws_client.get_route_table(grp.action.route_table_id)
            # Check the ENI is valid.
            aws_client.get_eni(grp.action.target_network_interface)

            action_func = aws_client.update_route_table
            action_kwargs = dict(
                route_table_id=grp.action.route_table_id,
                destination=grp.action.destination,
                target_network_interface=grp.action.target_network_interface,
            )
        else:
            assert False, f"Unexpected action type {grp.action.type.name}"
        actions[session] = Action(grp.action.type, action_func, **action_kwargs)
        logger.info(
            "Registered action %r on %r",
            actions[session].type.name.lower(),
            session,
        )

    return actions


def initialise() -> tuple[Config, Mapping[VRRPSession, Action]]:
    """
    Perform the initialisation flow.

    :raise InitError:
        For any expected possible initialisation errors.
    :return:
        Parsed config and registered actions.
    """
    global TELEM_SERVER

    try:
        config = Config.from_file("/etc/ha_app/config.yaml")
    except Exception as exc:
        raise InitError("Error reading config file") from exc

    try:
        actions = get_actions_from_config(config)
    except Exception as exc:
        raise InitError(f"Error validating config: {exc}") from exc

    # Initialise global VRRP state data.
    for session in actions.keys():
        VRRP_STATES[session] = VRRPState.INACTIVE

    logger.info(
        "Host IP addresses: %s",
        subprocess.check_output(["hostname", "-I"], text=True).strip(),
    )

    try:
        # Keep a reference to the server object to avoid it getting cleaned up
        # by the garbage collector.
        TELEM_SERVER = telem.listen(
            ThreadPoolExecutor(max_workers=1),
            vrrp_handler=partial(vrrp_handler, actions=actions),
            disconnect_handler=disconnect_handler,
            port=config.global_.port,
        )
    except Exception as exc:
        raise InitError("Error starting gRPC telemetry server") from exc

    return config, actions


def setup_logging() -> None:
    """
    Configure logging for the app.

    Enable debug but avoid overly verbose logging from certain modules.
    """

    class ShortLevelNameFormatter(logging.Formatter):
        """Log formatter, using log level names no longer than 5 characters."""

        def format(self, record: logging.LogRecord) -> str:
            if record.levelno == logging.WARNING:
                record.levelname = "WARN"
            elif record.levelno == logging.CRITICAL:
                record.levelname = "CRIT"
            return super().format(record)

    def thread_id_filter(record: logging.LogRecord) -> bool:
        """Inject thread_id to log record."""
        record.thread_id = threading.get_native_id()
        return True

    handler = logging.StreamHandler()
    handler.setFormatter(
        ShortLevelNameFormatter(
            style="{",
            fmt="{levelname:>5s} (t={thread_id:2d})[{name:<13s}] - {message}",
        )
    )
    handler.addFilter(thread_id_filter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)
    logging.getLogger("boto3").setLevel(logging.INFO)
    logging.getLogger("botocore").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)


def main(argv: list[str]) -> NoReturn:
    """Main function for the app."""
    # No CLI args supported, just support help output and getting version.
    help_description = textwrap.dedent(
        """\
        XRd HA app, expected to be run as a container via Helm in Kubernetes.

        See https://github.com/ios-xr/xrd-ha-app/.
        """
    )
    arg_parser = argparse.ArgumentParser(
        APP_NAME,
        description=help_description,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    arg_parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="output the app version and exit",
    )
    args = arg_parser.parse_args(argv)
    if args.version:
        print(__version__)
        sys.exit(0)

    setup_logging()
    try:
        config, actions = initialise()
    except InitError:
        logger.exception("Initialisation error:")
        sys.exit(2)

    start_consistency_check_event_loop(
        actions, config.global_.consistency_check_interval_seconds
    )


def shutdown_cleanup() -> None:
    """Perform cleanup at shutdown, before exiting the main thread."""
    THREAD_POOL.shutdown(cancel_futures=True)
    if TELEM_SERVER is not None:
        TELEM_SERVER.stop(grace=1)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        logger.info("Exiting on Ctrl+C")
        shutdown_cleanup()
        sys.exit(130)
    except Exception:
        logger.exception("Exiting on unexpected error:")
        shutdown_cleanup()
        sys.exit(1)
