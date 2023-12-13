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

from __future__ import annotations

import logging
import sys
import time
import typing
from pathlib import Path

import boto3
from moto.server import ThreadedMotoServer


if typing.TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client


logging.basicConfig(level=logging.DEBUG)
logging.getLogger("botocore").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)

# Run moto server.
server = ThreadedMotoServer(port=80)
server.start()
time.sleep(0.1)


def write_to_file(path: str | Path, content: str) -> None:
    logging.info("Writing %r to file %s", content, path)
    Path(path).write_text(content)


def create_vpc(client: EC2Client, cidr_block: str) -> str:
    response = client.create_vpc(CidrBlock=cidr_block)
    return response["Vpc"]["VpcId"]


def create_subnet(client: EC2Client, cidr_block: str, vpc_id: str) -> str:
    response = client.create_subnet(CidrBlock=cidr_block, VpcId=vpc_id)
    return response["Subnet"]["SubnetId"]


def create_route_table(client: EC2Client, vpc_id: str) -> str:
    response = client.create_route_table(VpcId=vpc_id)
    return response["RouteTable"]["RouteTableId"]


def create_network_interface(client: EC2Client, subnet_id: str) -> str:
    response = client.create_network_interface(SubnetId=subnet_id)
    return response["NetworkInterface"]["NetworkInterfaceId"]


# Set up EC2 instance.
client = boto3.client(
    "ec2",
    region_name="us-east-1",
    endpoint_url="http://localhost",
)

ami = client.describe_images(
    Owners=["amazon"],
    Filters=[{"Name": "Architecture", "Values": ["x86_64"]}],
)["Images"][0]
client.run_instances(ImageId=ami["ImageId"], MinCount=1, MaxCount=1)
ec2_instance_id = client.describe_instances()["Reservations"][0]["Instances"][0][
    "InstanceId"
]
write_to_file("/instance-id", ec2_instance_id)
attached_eni_id = client.describe_network_interfaces(
    Filters=[{"Name": "attachment.instance-id", "Values": [ec2_instance_id]}]
)["NetworkInterfaces"][0]["NetworkInterfaceId"]
write_to_file("/eni-id", attached_eni_id)

# Set up route table and create ENIs.
vpc_id = create_vpc(client, "10.0.0.0/16")
write_to_file("/rtb-vpc-id", vpc_id)
subnet_id = create_subnet(client, "10.0.0.0/24", vpc_id)
write_to_file("/rtb-subnet-id", subnet_id)
route_table_id = create_route_table(client, vpc_id)
write_to_file("/route-table-id", route_table_id)
rtb_orig_eni_id = create_network_interface(client, subnet_id)
write_to_file("/rtb-orig-eni-id", rtb_orig_eni_id)
rtb_target_eni_id = create_network_interface(client, subnet_id)
write_to_file("/rtb-target-eni-id", rtb_target_eni_id)

logging.info("Initialisation complete")

server._thread.join()

# Should never get here as the thread should never terminate.
sys.exit(1)
