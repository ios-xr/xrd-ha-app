# XRd HA App Helm chart tests

## Prerequisites

The following dependencies are required for both the unit tests and the integration tests:

- [Bats](https://github.com/bats-core/bats-core)
- [Bats support](https://github.com/bats-core/bats-support)
- [Bats assert](https://github.com/bats-core/bats-assert)
- [Helm](https://helm.sh)
- [yq](https://github.com/mikefarah/yq)

The unit tests also require:

- [yamllint](https://github.com/adrienverge/yamllint)
- [kubeconform](https://github.com/yannh/kubeconform)

The integration tests also require:

- [Bats DETIK](https://github.com/bats-core/bats-detik)
- [kubectl](https://kubernetes.io/docs/reference/kubectl)

And must be run against a [kind](https://kind.sigs.k8s.io) cluster, which can be launched using:

```
kind create cluster --config it/kind.yaml
```

## Running the tests in a container

A [Dockerfile](Dockerfile) is provided which defines a container image which includes all test dependencies.

The unit tests can be run using any container manager.  For example, using Docker:

```
docker build . -t ha-app-chart-tests
docker run -v "$PWD/..:/chart" ha-app-chart-tests bats tests/ut
```

The integration tests are run against a kind cluster.  Kind has stable support for Docker, and so it is easiest to run the container using Docker:

```
docker run -it --rm \
    -v "$PWD/..:/chart" \
    -v "/var/run/docker.sock:/var/run/docker.sock" \
    --net host \
    <container-image>
```

The kind cluster can be launched from within the container; the kind Docker container nodes are run on the host (Docker-out-of-Docker):

```
kind create cluster --config tests/it/kind.yaml
kind export kubeconfig --name integration-tests
```

The tests can then be run via:

```
bats tests/it
```

Teardown the cluster using:

```
kind delete cluster --name integration-tests
```
