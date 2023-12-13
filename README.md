# XRd HA App

This repo contains the "XRd HA app", a container application enabling High Availability of an active/standby pair of [XRd vRouter](https://www.cisco.com/c/en/us/products/routers/ios-xrd/index.html) instances running in the cloud.

If you just want to get up-and-running, jump ahead to [How To Use](#how-to-use).

For development tips and guidelines see [CONTIBUTING.md](CONTRIBUTING.md).


## Background

Documentation covering background into architecture and design decisions is provided under [`docs/`](/docs/).

The documents provided are as follows:
* [Functional Specification](/docs/functional_spec.md) - Specification of the problem being solved and the architectural solution.
* [HA App Design](/docs/app_design.md) - Design of the HA app (the code found in [`ha_app/`](/ha_app/)) and Helm chart (found in [`chart/`](/chart/)).
* [Test Plan](/docs/test_plan.md) - Test setup/approach for the HA app (tests in [`tests/`](/tests/)) and Helm chart (tests in [`chart/tests/`](/chart/tests/)).


## How To Use

This app is intended to be deployed in Kubernetes, specifically EKS in AWS, although it may be adapted to be used in other cloud provider environments.

Users are expected to fork this repository to make any required customisations.
This repository has no planned updates, so there shouldn't be too much of an ongoing cost in keeping synchronised with upstream.

The container image should be built by running `scripts/build_image.sh [--container-exe podman]`.
This built image can then be pushed to the cloud provider (e.g. ECR in AWS).

The app can then be deployed alongside its XRd vRouter partner using the Helm chart provided in the [`chart/`](/chart/) directory.


### Amazon EKS Setup

The Amazon EKS environment can be set up using [this Terraform configuration](https://github.com/ios-xr/xrd-terraform/examples/workload/ha).

In addition, the HA app makes API requests to the AWS EC2 service, and must use an IAM role to sign these requests via the [IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) mechanism.

IAM roles for service accounts must be enabled in your EKS cluster by completing the following procedures:

1. [Creating an IAM OIDC provider for your cluster](https://docs.aws.amazon.com/eks/latest/userguide/enable-iam-roles-for-service-accounts.html)
1. [Configuring a Kubernetes service account to assume an IAM role](https://docs.aws.amazon.com/eks/latest/userguide/associate-service-account-role.html)
1. [Configuring Pods to use a Kubernetes service account](https://docs.aws.amazon.com/eks/latest/userguide/pod-configuration.html)

The IAM policy created in step (2) must have the following permissions:

* ec2:DescribeInstances
* ec2:AssignPrivateIpAddresses
* ec2:UnassignPrivateIpAddresses
* ec2:CreateRoute
* ec2:DeleteRoute
* ec2:ReplaceRoute

The required annotation can be added to the ServiceAccount using the Helm chart `haApp.serviceAccount.annotations` value.

The HA app uses a VPC endpoint rather than the regional EC2 service endpoint.
This can be created using [these instructions](https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html#working-with-privatelink).


### Configuration

Example XR configuration can be found in [Functional Specification: Example XR Config](/docs/functional_spec.md#example-xr-config).

The HA app is configured by mounting a YAML configuration file at `/etc/ha_app/config.yaml` inside the container.
The mount is automatically set up if using Helm, where the `haApp.config` field should be used to provide the YAML configuration (see the [`chart/values.yaml`](/chart/values.yaml) file).

The schema for the HA app YAML configuration file is as follows:

```yaml
# Global configuration.
global:
  # Port number to use for running the gRPC server.
  port: <integer>  # optional, defaults to 50051
  # Interval in seconds at which to perform consistency checks.
  consistency_check_interval_seconds: <integer>  # optional, defaults to 10
  # Only AWS supported initially, other cloud providers may be supported in future.
  aws:
    # URL for a configured AWS VPC endpoint, see https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html.
    ec2_private_endpoint_url: <url>

# List of VRRP groups and action to perform when each goes active.
groups:
    # 'xr_interface' must be a fully qualified, long form XR interface name.
  - xr_interface: <XR interface name>
    # The virtual router ID, as configured in the XR VRRP config.
    vrid: <integer>
    # Action to perform when active state.
    action:
      # 'type' is one of:
      #   aws_activate_vip - move a secondary IP onto the relevant interface.
      #   aws_update_route_table - update route table to point to relevant interface.
      type: <enum>
      # 'device_index' is the AWS interface index, needed for 'aws_activate_vip' only.
      device_index: <integer>
      # 'vip' is the IP address to activate, needed for 'aws_activate_vip' only.
      vip: <IPv4 address>
      # 'route_table_id' is the ID of the route table, needed for 'aws_update_route_table' only.
      route_table_id: <string>
      # 'destination' is the route to update in the route table, needed for 'aws_update_route_table' only.
      destination: <IPv4 address with mask>
      # 'target_network_interface' is the ENI ID to associate the route with, needed for 'aws_update_route_table' only.
      target_network_interface: <string>
```

A valid example is as follows:
```yaml
global:
  port: 50051  # default (optional)
  consistency_check_interval_seconds: 10  # default (optional)
  aws:
    ec2_private_endpoint_url: "https://vpce-0123456789abcdef-vwje496n.ec2.us-west-2.vpce.amazonaws.com"

groups:
  - xr_interface: HundredGigE0/0/0/1
    vrid: 1
    action:
      type: aws_activate_vip
      device_index: 0
      vip: 10.0.2.100
  - xr_interface: HundredGigE0/0/0/2
    vrid: 2
    action:
      type: aws_update_route_table
      route_table_id: rtb-ec081d94
      destination: 192.0.2.0/24
      target_network_interface: eni-90a1bb4e
```


### Diagnostics and Logging

HA app logs can be accessed available via the container client.
When running in Kubernetes (the intended deployment scenario), the command is `kubectl logs <pod>`.

Example log output is given below.

```
root@ubuntu:~# kubectl logs xrd-ha-app-xrd-ha-app-856647b74c-z64gf
DEBUG (t= 9)[ha_app.config] - Reading config from file: /etc/ha_app/config.yaml
 INFO (t= 9)[ha_app       ] - Using private EC2 endpoint URL: https://vpce-0123456789abcdef-vwje496n.ec2.us-west-2.vpce.amazonaws.com
DEBUG (t= 9)[ha_app.aws   ] - Getting session token for IMDSv2
DEBUG (t= 9)[ha_app.aws   ] - Creating AWS EC2 client - instance ID: i-78ec844c4ad6cb354, region: us-east-1
 INFO (t= 9)[ha_app       ] - Registered action 'aws_activate_vip' on <xr_interface=HundredGigE0/0/0/1,vrid=1>
 INFO (t= 9)[ha_app       ] - Registered action 'aws_update_route_table' on <xr_interface=HundredGigE0/0/0/2,vrid=2>
 INFO (t= 9)[ha_app       ] - Host IP addresses: 10.88.0.4
 INFO (t= 9)[ha_app.telem ] - Listening on port 50051...
 INFO (t= 9)[ha_app       ] - Starting consistency checks every 10 seconds
 INFO (t=32)[ha_app.telem ] - Connection established with gRPC peer: 10.88.0.5:41546
DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/1,vrid=1>, previously INACTIVE
DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/1,vrid=1>, previously INACTIVE
 INFO (t=34)[ha_app       ] - Go active on <xr_interface=HundredGigE0/0/0/1,vrid=1> with aws_activate_vip
DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
 INFO (t=34)[ha_app.aws   ] - Assigning private IPv4 address 10.0.2.100 to device ID 0 (eni-aea46b22)
 INFO (t=35)[ha_app       ] - Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table
 INFO (t=35)[ha_app.aws   ] - Updating route table rtb-87763522 with destination 192.0.2.0/24, target eni-a9c26c56
 INFO (t=34)[ha_app       ] - Successful go-active on <xr_interface=HundredGigE0/0/0/1,vrid=1>
 INFO (t=35)[ha_app       ] - Successful go-active on <xr_interface=HundredGigE0/0/0/2,vrid=2>
DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/1,vrid=1>, previously ACTIVE
DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously ACTIVE
 INFO (t=32)[ha_app.telem ] - Connection closed by gRPC peer 10.88.0.5:41546
DEBUG (t=32)[ha_app       ] - Marking all VRRP sessions as inactive
```

The logs can be searched to gather insights into various events - some examples are given in the subsections below.
Note that the `--timestamps`, `--previous` and `--since` arguments to `kubectl logs` are often useful.

#### Check registered actions

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -i 'registered action'
2023-05-15T10:10:11.235557547-07:00  INFO (t= 9)[ha_app       ] - Registered action 'aws_activate_vip' on <xr_interface=HundredGigE0/0/0/1,vrid=1>
2023-05-15T10:10:11.235577225-07:00  INFO (t= 9)[ha_app       ] - Registered action 'aws_update_route_table' on <xr_interface=HundredGigE0/0/0/2,vrid=2>
```

#### Number of times there's been a go-active, and on which sessions

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -iE 'go[ -]active'
2023-05-18T08:45:10.258166575-07:00  INFO (t=34)[ha_app       ] - Go active on <xr_interface=HundredGigE0/0/0/1,vrid=1> with aws_activate_vip
2023-05-18T08:45:10.261761509-07:00  INFO (t=35)[ha_app       ] - Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table
2023-05-18T08:45:10.271116614-07:00  INFO (t=34)[ha_app       ] - Successful go-active on <xr_interface=HundredGigE0/0/0/1,vrid=1>
2023-05-18T08:45:10.273241811-07:00  INFO (t=35)[ha_app       ] - Successful go-active on <xr_interface=HundredGigE0/0/0/2,vrid=2>
```

#### Assign VIP actions

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -i 'assigning private ip'
2023-05-15T10:10:39.492806395-07:00  INFO (t=33)[ha_app.aws   ] - Assigning private IPv4 address 10.0.2.100 to device ID 0 (eni-63d83963)
2023-05-15T10:10:41.656793022-07:00  INFO (t= 9)[ha_app.aws   ] - Assigning private IPv4 address 10.0.2.100 to device ID 0 (eni-63d83963)
```

#### Route table update actions

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -i 'updating route table'
2023-05-15T10:10:12.230230406-07:00  INFO (t=35)[ha_app.aws   ] - Updating route table rtb-171a6305 with destination 10.0.10.0/24, target eni-4c4092f8
2023-05-15T10:10:50.715251259-07:00  INFO (t=34)[ha_app.aws   ] - Updating route table rtb-c51219e9 with destination 10.0.10.0/24, target eni-85e8e197
2023-05-15T10:10:52.866106573-07:00  INFO (t=10)[ha_app.aws   ] - Updating route table rtb-c51219e9 with destination 10.0.10.0/24, target eni-85e8e197
```

#### Number of no-op telemetry notifications, and on which sessions

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -iE 'got (in)?active'
2023-05-18T08:45:10.157421593-07:00 DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/1,vrid=1>, previously INACTIVE
2023-05-18T08:45:10.157491394-07:00 DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
2023-05-18T08:45:10.257045706-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/1,vrid=1>, previously INACTIVE
2023-05-18T08:45:10.258519814-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
2023-05-18T08:45:10.357584585-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/1,vrid=1>, previously ACTIVE
2023-05-18T08:45:10.357584585-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously ACTIVE
```

#### History of consistency checks

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -i -A1 'performing consistency check'
2023-05-15T10:10:39.638725017-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/1,vrid=1>
2023-05-15T10:10:39.644486368-07:00 DEBUG (t= 9)[ha_app.aws   ] - IPv4 address 10.0.2.100 already assigned
2023-05-15T10:10:40.645177872-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/1,vrid=1>
2023-05-15T10:10:40.651448543-07:00 DEBUG (t= 9)[ha_app.aws   ] - IPv4 address 10.0.2.100 already assigned
2023-05-15T10:10:41.651723138-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/1,vrid=1>
2023-05-15T10:10:41.656754793-07:00 DEBUG (t= 9)[ha_app.aws   ] - IPv4 address 10.0.2.100 not assigned at precheck
2023-05-15T10:10:50.837213021-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-15T10:10:50.852867819-07:00 DEBUG (t= 9)[ha_app.aws   ] - Route destination 10.0.10.0/24 via eni-85e8e197 already present in route table rtb-c51219e9
2023-05-15T10:10:51.853155518-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-15T10:10:51.859079088-07:00 DEBUG (t= 9)[ha_app.aws   ] - Route destination 10.0.10.0/24 via eni-85e8e197 already present in route table rtb-c51219e9
2023-05-15T10:10:52.859363940-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-15T10:10:52.866071827-07:00 DEBUG (t= 9)[ha_app.aws   ] - Route destination 10.0.10.0/24 via eni-85e8e197 not present in route table rtb-c51219e9 at precheck
```

#### Unexpected telemetry notifications, e.g. unregistered sessions

```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -iE 'unexpected telemetry|ignoring .*message'
2023-05-15T10:10:58.199099159-07:00  WARN (t=32)[ha_app.telem ] - Received unexpected telemetry message with path 'Cisco-IOS-XR-infra-syslog-oper:syslog/messages' (subsequent messages will be silently dropped)
2023-05-15T10:11:03.324309300-07:00  WARN (t=32)[ha_app.telem ] - Ignoring telemetry message on path 'Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router' without gpbkv data, only self-describing-gpb encoding is supported
2023-05-15T10:11:08.090142107-07:00  WARN (t=32)[ha_app.telem ] - Ignoring message with JSON payload, only self-describing-gpb encoding is supported
```

#### Warnings and errors (optionally including traceback)

This should be useful to check the app is functioning as expected.
In particular, checking error tracebacks may be useful for debugging the following scenarios:
* The HA app does not initialise successfully.
* Expected go-active actions are not enacted in AWS.
* You suspect that telemetry notifications may be getting dropped.

Warnings and errors (without tracebacks):
```
root@ubuntu:~# kubectl logs --timestamps <pod> --previous | grep -E 'WARN|ERROR'
2023-05-15T10:08:59.198222428-07:00  WARN (t= 7)[ha_app.aws   ] - Unable to get EC2 token for use with IMDSv2
2023-05-15T10:08:59.198252980-07:00  WARN (t= 7)[ha_app.aws   ] - This may be due to the hop limit being too low (1) for pods to connect (see https://aws.amazon.com/about-aws/whats-new/2020/08/amazon-eks-supports-ec2-instance-metadata-service-v2/)
2023-05-15T10:08:59.198252980-07:00  WARN (t= 7)[ha_app.aws   ] - Please run the following to fix: aws ec2 modify-instance-metadata-options --instance-id <instance_id> --http-put-response-hop-limit 2 --http-endpoint enabled
2023-05-15T10:08:59.201472081-07:00 ERROR (t= 7)[ha_app       ] - Initialisation error:
2023-05-15T10:10:58.199099159-07:00  WARN (t=32)[ha_app.telem ] - Received unexpected telemetry message with path 'Cisco-IOS-XR-infra-syslog-oper:syslog/messages' (subsequent messages will be silently dropped)
2023-05-15T10:11:03.324309300-07:00  WARN (t=32)[ha_app.telem ] - Ignoring telemetry message on path 'Cisco-IOS-XR-ipv4-vrrp-oper:vrrp/ipv4/virtual-routers/virtual-router' without gpbkv data, only self-describing-gpb encoding is supported
2023-05-15T10:11:08.090142107-07:00  WARN (t=32)[ha_app.telem ] - Ignoring message with JSON payload, only self-describing-gpb encoding is supported
2023-05-15T10:11:12.398709491-07:00 ERROR (t=32)[ha_app.telem ] - VRRP session data has unexpected structure
2023-05-15T10:11:16.825938818-07:00 ERROR (t=32)[ha_app.telem ] - Unexpected exception in MdtDialout from gRPC peer 10.88.0.3:37940
2023-05-15T10:11:16.826767996-07:00 ERROR (t=32)[grpc._server ] - Exception calling application: Error parsing message
```

Errors including tracebacks:
```
root@ubuntu:~# kubectl logs --timestamps <pod> --previous | awk '/ERROR/,/DEBUG/ || /INFO/ {if (/DEBUG/ || /INFO/) next; print}'
2023-05-15T10:09:20.176086925-07:00 ERROR (t= 9)[ha_app       ] - Initialisation error:
2023-05-15T10:09:20.176086925-07:00 Traceback (most recent call last):
2023-05-15T10:09:20.176086925-07:00   File "/home/appuser/ha_app/__main__.py", line 207, in initialise
2023-05-15T10:09:20.176086925-07:00     config = Config.from_file("/etc/ha_app/config.yaml")
2023-05-15T10:09:20.176086925-07:00              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2023-05-15T10:09:20.176086925-07:00   File "/home/appuser/ha_app/config.py", line 114, in from_file
2023-05-15T10:09:20.176086925-07:00     return cls(**(yaml.safe_load(f) or {}))
2023-05-15T10:09:20.176086925-07:00            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2023-05-15T10:09:20.176086925-07:00   File "pydantic/main.py", line 341, in pydantic.main.BaseModel.__init__
2023-05-15T10:09:20.176086925-07:00 pydantic.error_wrappers.ValidationError: 1 validation error for Config
2023-05-15T10:09:20.176086925-07:00 groups
2023-05-15T10:09:20.176086925-07:00   Only one action allowed per VRRP group, got multiple for <xr_interface=HundredGigE0/0/0/1,vrid=1> (type=value_error)
2023-05-15T10:09:20.176086925-07:00
2023-05-15T10:09:20.176086925-07:00 The above exception was the direct cause of the following exception:
2023-05-15T10:09:20.176086925-07:00
2023-05-15T10:09:20.176086925-07:00 Traceback (most recent call last):
2023-05-15T10:09:20.176086925-07:00   File "/home/appuser/ha_app/__main__.py", line 306, in main
2023-05-15T10:09:20.176086925-07:00     config, actions = initialise()
2023-05-15T10:09:20.176086925-07:00                       ^^^^^^^^^^^^
2023-05-15T10:09:20.176086925-07:00   File "/home/appuser/ha_app/__main__.py", line 209, in initialise
2023-05-15T10:09:20.176086925-07:00     raise InitError("Error reading config file") from exc
2023-05-15T10:09:20.176086925-07:00 InitError: Error reading config file

2023-05-15T10:09:28.549925561-07:00 ERROR (t=33)[ha_app       ] - Hit exception when performing action:
2023-05-15T10:09:28.549925561-07:00 Traceback (most recent call last):
2023-05-15T10:09:28.549925561-07:00   File "/home/appuser/ha_app/__main__.py", line 57, in _log_thread_exception
2023-05-15T10:09:28.549925561-07:00     func(*args, **kwargs)
2023-05-15T10:09:28.549925561-07:00   File "/home/appuser/ha_app/aws.py", line 98, in assign_vip
2023-05-15T10:09:28.549925561-07:00     eni: NetworkInterface = self._ec2_instance_enis[device_id]
2023-05-15T10:09:28.549925561-07:00                             ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^
2023-05-15T10:09:28.549925561-07:00 KeyError: 123
2023-05-15T10:11:12.398709491-07:00 ERROR (t=32)[ha_app.telem ] - VRRP session data has unexpected structure
2023-05-15T10:11:12.398709491-07:00 Traceback (most recent call last):
2023-05-15T10:11:12.398709491-07:00   File "/home/appuser/ha_app/telem.py", line 156, in _handle_vrrp_msg
2023-05-15T10:11:12.398709491-07:00     keys = _gpbkv_get_field(session.fields, "keys").fields
2023-05-15T10:11:12.398709491-07:00            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2023-05-15T10:11:12.398709491-07:00   File "/home/appuser/ha_app/telem.py", line 50, in _gpbkv_get_field
2023-05-15T10:11:12.398709491-07:00     raise KeyError(f"Field {field!r} not found in the gpbkv data")
2023-05-15T10:11:12.398709491-07:00 KeyError: "Field 'keys' not found in the gpbkv data"
2023-05-15T10:11:16.825938818-07:00 ERROR (t=32)[ha_app.telem ] - Unexpected exception in MdtDialout from gRPC peer 10.88.0.3:37940
2023-05-15T10:11:16.826767996-07:00 ERROR (t=32)[grpc._server ] - Exception calling application: Error parsing message
2023-05-15T10:11:16.826767996-07:00 Traceback (most recent call last):
2023-05-15T10:11:16.826767996-07:00   File "/home/appuser/.local/lib/python3.11/site-packages/grpc/_server.py", line 444, in _call_behavior
2023-05-15T10:11:16.826767996-07:00     response_or_iterator = behavior(argument, context)
2023-05-15T10:11:16.826767996-07:00                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^
2023-05-15T10:11:16.826767996-07:00   File "/home/appuser/ha_app/telem.py", line 95, in MdtDialout
2023-05-15T10:11:16.826767996-07:00     self._handle_msg(msg)
2023-05-15T10:11:16.826767996-07:00   File "/home/appuser/ha_app/telem.py", line 114, in _handle_msg
2023-05-15T10:11:16.826767996-07:00     telemetry_msg.ParseFromString(msg.data)
2023-05-15T10:11:16.826767996-07:00 google.protobuf.message.DecodeError: Error parsing message
```

#### Is the telemetry connection active?

Check whether latest log message says connection is "established" or "closed"/"lost".
```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -iE 'connection .*gRPC'
2023-05-15T10:09:28.548760316-07:00  INFO (t=32)[ha_app.telem ] - Connection established with gRPC peer: 10.88.0.5:59698
2023-05-15T10:09:28.648648519-07:00  INFO (t=32)[ha_app.telem ] - Connection closed by gRPC peer 10.88.0.5:59698
2023-05-15T10:10:12.127099661-07:00  INFO (t=32)[ha_app.telem ] - Connection established with gRPC peer: 10.88.0.5:47820
2023-05-15T10:10:12.428199440-07:00  INFO (t=32)[ha_app.telem ] - Connection closed by gRPC peer 10.88.0.5:47820
2023-05-15T10:10:30.674528502-07:00  INFO (t=32)[ha_app.telem ] - Connection established with gRPC peer: 10.88.0.5:49438
2023-05-15T10:10:30.774939010-07:00  INFO (t=32)[ha_app.telem ] - Connection closed by gRPC peer 10.88.0.5:49438
2023-05-15T10:10:39.491968389-07:00  INFO (t=32)[ha_app.telem ] - Connection established with gRPC peer: 10.88.0.5:49950
2023-05-15T10:10:42.496986869-07:00  INFO (t=32)[ha_app.telem ] - Connection lost with gRPC peer 10.88.0.5:49950
2023-05-15T10:10:50.714557006-07:00  INFO (t=32)[ha_app.telem ] - Connection established with gRPC peer: 10.88.0.5:51086
2023-05-15T10:10:53.712061198-07:00  INFO (t=32)[ha_app.telem ] - Connection closed by gRPC peer 10.88.0.5:51086
```

#### Is a given VRRP group active or inactive?

Example where the specified group is inactive (last message says "Got INACTIVE"):
```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -i '<xr_interface=HundredGigE0/0/0/2,vrid=2>'
2023-05-18T08:45:09.479175477-07:00  INFO (t= 9)[ha_app       ] - Registered action 'aws_update_route_table' on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-18T08:45:10.157491394-07:00 DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
2023-05-18T08:45:10.258519814-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
2023-05-18T08:45:10.261761509-07:00  INFO (t=35)[ha_app       ] - Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table
2023-05-18T08:45:10.273241811-07:00  INFO (t=35)[ha_app       ] - Successful go-active on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-18T08:45:13.357584585-07:00 DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously ACTIVE
```

Example where the specified group is active (last message says "Go active", "Successful go-active" or "Performing consistency check"):
```
root@ubuntu:~# kubectl logs --timestamps <pod> | grep -i '<xr_interface=HundredGigE0/0/0/2,vrid=2>'
2023-05-18T08:45:09.479175477-07:00  INFO (t= 9)[ha_app       ] - Registered action 'aws_update_route_table' on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-18T08:45:10.157491394-07:00 DEBUG (t=32)[ha_app       ] - Got INACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
2023-05-18T08:45:10.258519814-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously INACTIVE
2023-05-18T08:45:10.261761509-07:00  INFO (t=35)[ha_app       ] - Go active on <xr_interface=HundredGigE0/0/0/2,vrid=2> with aws_update_route_table
2023-05-18T08:45:10.273241811-07:00  INFO (t=35)[ha_app       ] - Successful go-active on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-18T08:45:10.357584585-07:00 DEBUG (t=32)[ha_app       ] - Got ACTIVE for <xr_interface=HundredGigE0/0/0/2,vrid=2>, previously ACTIVE
2023-05-18T08:45:10.837213021-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-18T08:45:11.853155518-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>
2023-05-18T08:45:12.859363940-07:00 DEBUG (t= 9)[ha_app       ] - Performing consistency check on <xr_interface=HundredGigE0/0/0/2,vrid=2>
```


## Performance Impact

Note that running substantial workloads on the same cpuset as XRd vRouter is not supported; the HA app is not confined to a certain cpuset and therefore may end up sharing CPUs with XRd.

The HA app has been profiled alongside XRd vRouter in a deployment environment (Amazon EKS) to ensure that it does not have a substantial performance impact.  The total time taken to enact failover of the active XRd instance, and the maximum time that an HA app thread runs on a CPU before yielding was measured, at the maximum VRRP session scale as stated in the [requirements](docs/functional_spec.md#scale-and-performance):

* The total time taken for the HA app to enact the failover is less than 40 ms.
* Go-active threads run for up to 8 ms before yielding.

If modifications are made to the HA app then these changes should be profiled to ensure that their performance impact is minimal.


## Limitations

### AWS VPC and Gratuitious ARP

Gratuitous ARP (GARP) is not supported in AWS VPC.  This has a notable impact on the Cloud HA feature; the recommended mitigation is to configure the workload (that is, the CNF using the redundant pair of XRd vRouter instances as its Cloud Gateway) to have as low an ARP cache timeout as possible.  For further details see the Configuration and Software Restrictions section of the [Functional Specification](/docs/functional_spec.md).


## Repository Contents

The most relevant parts of the repository filesystem are described below.

* `ha_app/` \
  The source code for the app. \
  The `gpb/` subpackage contains generated GPB code - run `scripts/regen_gpb.sh` to regenerate.
* `chart/` \
  The Helm chart for installing the HA app in Kubernetes.
* `protos/` \
  The protobuf files used to generate the `ha_app/gpb/` Python modules.
* `tests/` \
  Tests for the HA app. \
  Includes module UT (in `ut/`), integration testing (in `it/`), and image testing (in `image/`). \
  Run with `pytest`.
* `docs/` \
  Markdown documents associated with the project.
* `scripts/` \
  Scripts for working with the project.
* `Dockerfile` \
  The dockerfile to use for building the container image.
* `commit-check` \
  Convenience script for running the commit checks (tests, formatting, linting, ...).


## Versioning Scheme

This project loosely follows semantic versioning.
Version numbers consist of major, minor and patch, e.g. `v1.0.2`.

Cosmetic changes will involve a patch bump, moderate (possibly breaking) changes will be a minor bump, while significant backwards-incompatible changes require a major version bump.

Major version bumps are expected to be rare, since there are no plans for significant changes to the example provided here.

Minor version bumps may introduce incompatibilities such as a change to the config schema.


## Development, Issues and Contributing

Check out the repository's [open issues](https://github.com/ios-xr/xrd-ha-app/issues) or see [CONTRIBUTING.md](CONTRIBUTING.md) for more guidelines.
