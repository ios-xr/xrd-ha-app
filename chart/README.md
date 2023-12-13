# XRd HA App Helm Chart

This directory contains the XRd HA app Helm chart for deploying and configuring the XRd HA app on Kubernetes.

## Prerequisites

[Helm](https://helm.sh) must be installed and configured for your Kubernetes cluster.  Please refer to the [Helm documentation](https://helm.sh/docs) to get started.

## Usage

Install the Helm chart by passing the local path of this directory to `helm install`:

```
helm install -g $PWD -f <your-values-file>
```

Note that the chart is *not* packaged or stored in a chart repository.

### Parameters

All configuration parameters are documented in the [default values file](values.yaml).  In particular, note that:

* `haApp.image.repository` is a required value.
* `haApp.serviceAccount.annotations` must contain an `eks.amazonaws.com/role-arn` annotation, with value set to the HA app IAM role ARN as described [here](/README.md#amazon-eks-setup).

Configuration parameters for the XRd vRouter subchart are documented in the [XRd vRouter default values file](https://github.com/ios-xr/xrd-helm/blob/main/charts/xrd-vrouter/values.yaml).

Note that XR Telemetry configuration is dependent on properties of the HA app Service:

* The destination address must be set to `haApp.service.clusterIP`.  Be aware that there are caveats to Service ClusterIP allocation as detailed in the [Kubernetes documentation](https://kubernetes.io/docs/concepts/services-networking/cluster-ip-allocation/).
* The destination port must be set to `haApp.service.exposedPort`.

An [example values file template](example_values.yaml) is provided which describes the minimal HA app and XR configuration required.
