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

import argparse
import json
import logging
import sys
import time

import google.protobuf.json_format
import grpc

from cisco_grpc_dialout_pb2 import MdtDialoutArgs
from cisco_grpc_dialout_pb2_grpc import gRPCMdtDialoutStub
from telemetry_pb2 import Telemetry, TelemetryField


def create_vrrp_gpbkv_entry(intf_name: str, vrid: int, state: str) -> TelemetryField:
    """Create a VRRP telemetry message entry."""
    return TelemetryField(
        timestamp=int(time.time()),
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
                        string_value=state,
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


def create_vrrp_msg(
    gpbkv_fields: list[TelemetryField],
    encoding_path: str = "Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router",
) -> Telemetry:
    """Create a full VRRP telemetry message from the gpbkv fields."""
    return Telemetry(
        subscription_id_str="sub-vrrp",
        encoding_path=encoding_path,
        msg_timestamp=int(time.time()),
        data_gpbkv=gpbkv_fields,
    )


def send_grpc(
    target: str,
    messages: list[MdtDialoutArgs],
    *,
    pause: float = 0,
    keep_connection_open: bool = False,
    unclean_connection_close: bool = False,
) -> None:
    def msg_iterator():
        for i, msg in enumerate(messages):
            logging.debug("Sending gRPC message %d", i)
            yield msg
            time.sleep(pause)
        if unclean_connection_close:
            raise Exception("gRPC client unclean connection close")
        elif keep_connection_open:
            logging.info("Messages sent, keeping connection open")
            time.sleep(3600)  # 1 hour

    logging.info("Opening gRPC connection with %s", target)
    with grpc.insecure_channel(target) as channel:
        stub = gRPCMdtDialoutStub(channel)
        stream = stub.MdtDialout(msg_iterator())
        # Connection should be closed by server side when the iterator has been
        # exhausted, and we can wait for this by iterating on the stream object.
        for response in stream:
            assert False, "Response iterator should be empty"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        "-t",
        required=True,
        help="Target to connect to, e.g. localhost:1234",
    )
    parser.add_argument(
        "--vrrp-msgs",
        nargs="+",
        help=(
            "One or more args representing VRRP telemetry messages to send, of "
            "the form: "
            "'interface-name=Gi0/0/0/0,virtual-router-id=1,vrrp-state=state-master;...'"
        ),
    )
    parser.add_argument(
        "--json-msgs",
        nargs="+",
        help="One or more generic telemetry messages represented in JSON form",
    )
    parser.add_argument(
        "--raw-json-msgs",
        nargs="+",
        help="One or more generic MdtDialout messages represented in JSON form",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.1,
        help="How long to pause after sending each message",
    )
    parser.add_argument(
        "--keep-connection-open",
        action="store_true",
        help="Keep the connection open indefinitely",
    )
    parser.add_argument(
        "--unclean-connection-close",
        action="store_true",
        help="Shut down the connection by raising an exception",
    )
    return parser.parse_args(argv)


def convert_vrrp_msg_cli(vrrp_msg: str) -> Telemetry:
    sessions = vrrp_msg.split(";")
    gpbkv_fields = []
    session_strings = []
    for sess in sessions:
        msg_dict = dict(item.split("=") for item in sess.split(","))
        intf_name = msg_dict["interface-name"]
        vrid = int(msg_dict["virtual-router-id"])
        state = msg_dict["vrrp-state"]
        gpbkv_fields.append(create_vrrp_gpbkv_entry(intf_name, vrid, state))
        session_strings.append(
            f"interface-name={intf_name}, virtual-router-id={vrid}, vrrp-state={state}"
        )
    logging.debug(
        "Created VRRP telemetry message containing:\n  %s",
        "\n  ".join(x for x in session_strings),
    )
    return create_vrrp_msg(gpbkv_fields)


def convert_json_msg_cli(json_msg: str) -> Telemetry:
    return google.protobuf.json_format.Parse(json_msg, Telemetry())


def convert_raw_json_msg_cli(json_msg: str) -> MdtDialoutArgs:
    json_msg_decode = json.loads(json_msg)
    if "data" in json_msg_decode:
        json_msg_decode["data"] = json_msg_decode["data"].encode()
    return MdtDialoutArgs(**json_msg_decode)


def main(argv: list[str]):
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG)
    telem_msgs = []
    if args.vrrp_msgs:
        telem_msgs.extend(convert_vrrp_msg_cli(msg) for msg in args.vrrp_msgs)
    if args.json_msgs:
        telem_msgs.extend(convert_json_msg_cli(msg) for msg in args.json_msgs)
    for count, msg in enumerate(telem_msgs):
        logging.debug("Message (telemetry) %d:\n%s", count, msg)
    mdt_dialout_msgs = [
        MdtDialoutArgs(ReqId=i, data=msg.SerializePartialToString())
        for i, msg in enumerate(telem_msgs)
    ]
    if args.raw_json_msgs:
        raw_msgs = [convert_raw_json_msg_cli(msg) for msg in args.raw_json_msgs]
        for count, msg in enumerate(raw_msgs, start=len(mdt_dialout_msgs)):
            logging.debug("Message (raw MdtDialout) %d:\n%s", count, msg)
        mdt_dialout_msgs.extend(raw_msgs)
    send_grpc(
        args.target,
        mdt_dialout_msgs,
        pause=args.pause,
        keep_connection_open=args.keep_connection_open,
        unclean_connection_close=args.unclean_connection_close,
    )
    logging.debug("Clean exit")


if __name__ == "__main__":
    main(sys.argv[1:])
