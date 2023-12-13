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
import logging
import subprocess
import sys

import flask


NAME = "aws_metadata_service"

AWS_METADATA_IP = "169.254.169.254"


app = flask.Flask(NAME)

token: str = "token"
region_name: str = "us-east-1"
instance_id: str = "i-0123456789abcdef"


@app.route("/latest/api/token", methods=["PUT"])
def route_latest_api_token():
    return token


@app.route("/latest/meta-data/placement/region", methods=["GET"])
def route_latest_metadata_placement_region():
    return region_name


@app.route("/latest/meta-data/instance-id", methods=["GET"])
def route_latest_metadata_instanceid():
    return instance_id


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", "-r", help="EC2 region name to return")
    parser.add_argument("--instance-id", "-i", help="EC2 instance ID to return")
    return parser.parse_args(argv)


def main(argv: list[str]):
    global region_name, instance_id
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG)
    if args.region:
        region_name = args.region
    if args.instance_id:
        instance_id = args.instance_id
    subprocess.run(
        ["ip", "addr", "add", f"{AWS_METADATA_IP}/32", "dev", "eth0"],
        check=True,
        timeout=1,
    )
    logging.debug("Starting mock AWS metadata server...")
    app.run(AWS_METADATA_IP, 80)


if __name__ == "__main__":
    main(sys.argv[1:])
