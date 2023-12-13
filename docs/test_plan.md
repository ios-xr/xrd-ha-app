# Test Plan

This document describes the test plan for the Cloud HA feature for XRd vRouters running in a public cloud.
See the related documents: [Functional Specification](functional_spec.md) and [HA App Design](app_design.md).

This plan covers all testing of the HA app, from UT to end-to-end IT of the overall solution.
It does not cover testing the functionality of all solution dependencies - specifically, there is no focus on directly testing XR features - these are only covered to the extent required for the end-to-end flows.

The HA application Helm chart is considered as part of this document in [Helm Chart Testing](#helm-chart-testing).

Key sections below include:
* Test Strategy - outlining the scope, objectives, and phasing
* Module Unit Testing - HA app module UT
* Container-based Integration Testing - HA app full-flow isolated IT


## Test Strategy

### Scope

This test plan covers testing of the overall HA solution for the XRd Cloud Router within AWS, as described in [Functional Specification](functional_spec.md).
This includes isolated testing of the HA app itself (detailed in [HA App Design](app_design.md)).

More explicitly, the following types of testing are covered in this document:
* Static analysis
  * Standard static analysis run against the HA app code.
* Isolated testing (Module UT and container-based Integration Testing)
  * Testing focused on the HA app in isolation, giving comprehensive line coverage.
  * Includes testing of the HA container image creation.
* Performance testing
  * Verify failover time in the end-to-end setup.
* Vulnerability testing
  * Running a container image scanner on the HA container image.

Note that end-to-end IT is also performed (testing the full solution in a faithful environment with packets flowing through EKS in AWS), however this testing is considered out of scope of this document.


### Objectives

The goals of the testing covered in this plan correspond with the types of testing listed in the section above:
* Static analysis
  * Catch bugs in HA app early using type checking and linting.
* Isolated testing
  * At least 90% code coverage of the HA app, combining UT and IT coverage.
  * Verify all mainline and error flows.
  * Confidence in the robustness of the concurrency solution.
  * Verification that the container image build succeeds, and that metadata is correctly set.
  * Full automation of the tests.
  * Rapid iteration (fast tests, ease of running).
* Vulnerability testing
  * Catch known CVEs in the container image.

Note that it is not a goal to test functionality of dependencies outside the scope listed above, for the purpose of testing the overall HA solution.


### Test Approach

The different types of testing have different objectives as laid out in the previous section.
In particular:
* Module UT gives quick testing on a per-module level, allowing coverage of all code branches via mocking.
* Container-based IT gives quick testing with mocking of external interactions, providing testing of the full app flow in a convenient, performant environment.
* E2E IT gives confidence in the full solution in the deployment environment, although this is slower and harder to set up.

#### Mainline Testing

Mainline testing involves going through SA and mainline testing covered in Module UT and Container-based IT.

* Full static analysis of the HA app.
* Module UT:
  * Covering all modules (coverage collected).
  * Mainline success cases.
  * Error/misconfiguration cases.
* Container-based IT:
  * Requires infra setup for mocking AWS and telemetry interactions.
  * Faithful use of HA app, e.g. handling multiple telemetry notifications concurrently to perform multiple different actions.
  * Mainline and error/misconfiguration cases.
  * Dependency on the HA container image build being usable, although specific image testing is not required.
  * Code coverage data collected.

#### Container Image Testing

This phase covers all of the planned container image testing:
* Container-based IT:
  * Test container build.
  * Check image metadata.
  * Verify run as non-root.
* Vulnerability testing via image scanning.



## Module Unit Testing

### Overview

Module UT covers each of the HA app modules.
The test code can be found in [`tests/ut/`](/tests/ut/), see [Development](/README.md#development) for how to run.

The app is structured with external interactions isolated in their own modules, that is the 'telemetry' and 'aws' modules (see [HA App Design: Module Level Design](app_design.md#module-level-design)).


### Objectives

The general goal of Module UT is to test for coding errors in a quick and reliable manner, without dependencies on external factors such as the environment.

In the case of the HA app there is a relatively small amount of code logic, with the bulk of the work being done by third party libraries (`grpcio` for receiving telemetry events; `boto3` and `requests` for interacting with AWS).
As such, this phase of testing alone is not expected to necessarily achieve the code coverage goal, with somewhat more focus on testing the full flow in the Container-based IT (still in a controlled environment providing quick execution).


### Setup

The tests are implemented as a simple standalone Pytest suite, with no other dependencies.
Mocking is performed using Python's built-in `unittest.mock` package.

All module boundaries are mocked out, including the third-party `boto3` and `grpcio` APIs such that these are not dependencies within the tests.


### Default Strategy

The strategy is to achieve code coverage with minimal mocking of internal APIs, to avoid tightly coupling the test implementation to the code itself.
The tests should be relatively simple and always fast/reliable, and as such it is expected that threads are mocked out and thread entrypoints tested directly.

### Main Module

The main module contains the bulk of the HA app logic, handling telemetry state changes by updating the HA app state and triggering registered actions as required.

#### Module Objectives

The objective of this Module UT is to validate the flows:
* Startup (handling user config, initializing state)
* Handling notifications (update state, trigger actions)
* Periodic action updates (trigger actions if required)

#### Setup and Dependencies

The following APIs are mocked throughout this Module UT:
* AWS client
* Telemetry 'listen' API

Functions internal to the main module are not mocked - all flows can be validated by mocking the external APIs alone.

#### Module Strategy

Default strategy, with specifics given below.

The responsibilities of the main module to be tested in module UT are:
* User config parsing and validation
* Initialization
  * Creating the AWS client
  * Registering telemetry handlers
  * Entering the event loop
* Telemetry event handling
  * Activate AWS VIP action
  * Update AWS route table action
* Periodically triggering actions
The following error cases are also tested:
* Missing user config
* Invalid user config
  * No actions specified
  * Unsupported actions
  * Unexpected config fields
  * Multiple actions configured for a single VRID/interface pair
* Failure to create AWS client (app exits)
* Error when performing an action (app continues)


### Telemetry Module

The telemetry module wraps the grpcio library and generated protobuf modules for receiving self-describing GPB messages from XR.

There is minimal logic and state in this module, with it primarily serving as a clean API for the main module to interact with.

#### Module Objectives

The objective of this Module UT is verify that telemetry notifications are handled correctly when received, calling the registered handlers.

#### Setup and Dependencies

The protobuf modules must be generated to be imported by the telemetry module.
However, the grpcio module itself is mocked - handling of notifications is verified by directly invoking the API that would normally be called by the grpcio library.

#### Module Strategy

The telemetry module `listen()` API is called to verify the initialization flow.
For verifying the handling of notifications, an instance of the 'VRRPServicer' class is created directly, and the 'MdtDialout' method invoked directly.

Mocks are used for the handlers that get registered to make it easy to verify they are called correctly.


### AWS Module

The AWS module serves as a wrapper around the boto3 client initialization (connecting to the AWS metadata service) and the boto3 APIs that correspond to supported actions.

#### Module Objectives

The objective of this Module UT is to verify the expected calls are made in the scenarios:
* Initialize `boto3` client (using the `requests` library to connect to AWS metadata service)
* Assign VIP action
* Update route table action

#### Setup and Dependencies

The `boto3` and `requests` packages are mocked - the tests simply verify that the expected calls are made.

Mocking is used to prevent the creation of a separate thread for updating the AWS client, while giving access to the function that would be called by the thread for manual invocation in the tests.

#### Module Strategy

The initialization flow is verified by creating an instance of `AWSClient` and checking the calls made using `requests` and `boto3`.
This can then be used to verify the boto3 calls made as part of the supported actions.



## Container-based Integration Testing

### Overview

The Container-based IT exercises a single HA container instance within a mocked environment.
This contrasts to Module UT in that it uses the HA app unmodified (only external resources are mocked) and running in a container, and contrasts to E2E by focusing the testing on the HA app logic rather than testing the full XRd HA solution.

The Module UT and Container-based IT combined must achieve the code coverage goal.

The test code can be found in [`tests/it/`](/tests/it/), see [Development](/README.md#development) for how to run.


### Objectives

The aim of this phase of testing is to provide relatively fast and simple full-flow coverage of the HA app.
The testing is performed in a more faithful environment (running in a container) without modifications to the app itself.
This also serves to provide verification of the container image build.


### Setup

The two external interactions to be mocked are AWS and telemetry events.

The setup is as follows:
* HA app runs in a container, as intended in deployment scenarios
* AWS interactions are mocked using the [`moto` package](https://docs.getmoto.org/) (in server mode)
* Telemetry notifications are simulated using [`grpcio`](https://grpc.io/docs/languages/python/) (the same library used by the HA app)

The tests can be run on any host that supports running containers with Docker or Podman.
Pytest is used as the testing framework, and the [`python_on_whales` library](https://gabrieldemarmiesse.github.io/python-on-whales/) is used for managing the required containers.

Code coverage can be collected by installing the [`coverage` package](https://coverage.readthedocs.io/) into the HA container, modifying the entrypoint to use `coverage run`, and storing the resulting coverage data file in a persistent volume.


### Default Strategy

This is a form of integration testing with all modules together in the HA container.
The strategy is to seek code coverage of any module API boundaries not covered in Module UT.
This is done by creating test cases based on end-to-end functionality and subsequently verifying that the appropriate coverage has been achieved.


### Test Cases

The following lists the cases to be tested within Container-based IT:
* Image creation:
  * Building the HA container image
  * Verify container image metadata
* Receiving telemetry notifications:
  * Receive initial 'active' notification on configured subnet, trigger action
  * Receive 'non-active' notification on configured subnet, do nothing
  * Receive 'active' notification on subnet that is not configured, do nothing
  * Receive 'active' notification on subnet already considered active, do nothing
  * Receive 'active' notification on subnet previously considered inactive, trigger configured action
  * Receive 'active' notification after reconnect on subnet previously considered active, trigger configured action
* Performing AWS actions:
  * Trigger AWS 'activate VIP' action
  * Trigger AWS 'update route table' action
* Concurrency:
  * Add a delay into the AWS action flow and verify actions are handled concurrently
  * Verify periodic AWS client refresh
* Error cases:
  * Action failure should result in an error being logged, no exit
  * Unexpected telemetry notification should be ignored



## Helm Chart Testing

Testing of the Helm chart is split into three phases:
1. A Module UT-style phase: input values are templated, and specific fields in the output manifests are checked.
1. An IT-style phase: input values are templated, output manifests are applied to a K8s cluster, and properties of various resources in this cluster are checked.
1. End-to-end testing of the entire HA application.

The test code can be found in [`chart/tests/`](/chart/tests/), see [`chart/tests/README.md`](/chart/tests/README.md) for how to run.


### Phase 1 - Module UT

The goal of this phase is to exercise the chart templating logic in an isolated environment with fast iteration.

The following test tools are used:
* [Helm](https://helm.sh/) is used for linting ("static analysis") and templating.
* [Bats](https://github.com/bats-core/bats-core) is used as the test framework.
* `yq` is used to parse relevant fields in the output YAML.

The test strategy is to provide input values, run the Helm templating engine to produce output manifests, and check properties of these manifests.
This strategy is a common approach to unit-testing Helm charts, refer to the [Consul Helm chart](https://github.com/hashicorp/consul-helm) for an example.

A Dockerfile is provided to define the test environment.
The tests are run in this test environment via Github actions as part of a pre-commit check in the open-source XRd Helm repository.


### Phase 2 - IT

The goal of this test phase is to check that installing and upgrading the Helm chart with specific input values has the expected effect on the state of the Kubernetes cluster.

#### Setup

The Helm chart IT is not expected to test any behavior of the HA application or XRd itself, and therefore the container images need not be the actual HA application or XRd images.
Instead the HA application and XRd container images are "stubbed", and Alpine images are used.

The following test tools are used:
* [Bats](https://github.com/bats-core/bats-core) is used as the test framework.
* [Helm](https://helm.sh/) is used for lifecycle operations (install, upgrade, uninstall).
* [Kind](https://kind.sigs.k8s.io) is used as a lightweight Kubernetes cluster.
* Kubectl is used to verify the state of the Kubernetes cluster.

#### Strategy

The test strategy is to provide input values, install, upgrade, or uninstall the Helm chart, and check various properties of the Kubernetes cluster to verify that it is in the expected state.

Kubernetes is considered "trusted"; it is assumed in most cases that applying a correct manifest results in the expected cluster state.
This means that the scope of the IT is fairly narrow, with most of the testing covered in the Module UT phase.

#### Test Cases

The following are notable test cases:
* Installing the Helm chart with the default values results in the HA application Pod listening on a certain target port, exposed by a Service on a certain exposed port.
* HA application configuration specified in the Helm chart is correctly mounted at the expected location in the HA application container.
* The HA application Pod is affined to the same worker node as its corresponding XRd Pod.
* Upgrading the HA application version results in a restart of the HA application.
* Upgrading the HA application configuration results in a restart of the HA application.

Many of the test cases do not require the XRd Pod to be running and therefore the XRd subchart is disabled in the parent Helm chart.

#### Automation Considerations

Because there is no dependency on an XRd image, the IT is included in the repo alongside the Helm chart in this repository.
It is automated via Github actions.

The IT must be run against a Kind cluster; the Kind Github action maintained by Helm is used to setup this cluster in automation.
