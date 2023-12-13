#!/usr/bin/env bats

bats_load_library "bats-assert/load.bash"
bats_load_library "bats-detik/detik.bash"
bats_load_library "bats-support/load.bash"

load "utils.bash"

export DETIK_CLIENT_NAME="kubectl"
export DETIK_CLIENT_NAMESPACE="integration-tests"

setup_file () {
    kubectl delete namespace integration-tests --ignore-not-found
    kubectl create namespace integration-tests
    kubectl config set-context --current --namespace=integration-tests

    cd "$(chart_dir)" || exit
    helm dependency update .
}

teardown_file () {
    kubectl delete namespace integration-tests --ignore-not-found
    kubectl config set-context --current --namespace=default
}

teardown () {
    helm uninstall "$(release_name)"
    kubectl wait --for=delete --timeout=1m pod -l "app.kubernetes.io/instance=$(release_name)"
}

@test "Expected resources are deployed" {
    echo "# Install Helm chart"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --wait \
        --timeout=1m

    verify "there is 1 StatefulSet named '$(release_name)'"
    verify "there is 1 Deployment named 'xrd-ha-app-$(release_name)'"
    verify "there is 1 Pod named '$(release_name)-xrd-0'"
    verify "there is 1 Pod named 'xrd-ha-app-$(release_name)-*'"
    verify "there is 1 Service named 'xrd-ha-app-$(release_name)'"
    verify "there is 1 ServiceAccount named 'xrd-ha-app-$(release_name)'"
}

@test "Config is mounted correctly" {
    echo "# Install Helm chart with 'haApp.config=foo'"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --set 'haApp.config=foo' \
        --wait \
        --timeout=1m

    echo "# Assert the HA Pod exists"
    verify "there is 1 Pod named 'xrd-ha-app-$(release_name)'"
    name=$(kubectl get pod \
        -l "app.kubernetes.io/instance=$(release_name),app.kubernetes.io/name=xrd-ha-app" \
        -o yaml | yq -e '.items[0].metadata.name')

    echo "# Check mounted config has expected permissions"
    run -0 kubectl exec "$name" -- stat -L /etc/ha_app/config.yaml
    assert_output --partial "Access: (0644/-rw-r--r--)"

    echo "# Check mounted config has expected content"
    run -0 kubectl exec "$name" -- cat /etc/ha_app/config.yaml
    assert_output "foo"
}

@test "Config can be set via '--set-file'" {
    echo "# Write temporary config file"
    tempfile=$(mktemp)
    cat <<-EOF > "$tempfile"
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
	EOF

    echo "# Install Helm chart with '--set-file haApp.config=<tempfile>'"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --set-file "haApp.config=$tempfile" \
        --wait \
        --timeout=1m

    echo "# Assert the HA Pod exists"
    verify "there is 1 Pod named 'xrd-ha-app-$(release_name)'"
    name=$(kubectl get pod \
        -l "app.kubernetes.io/instance=$(release_name),app.kubernetes.io/name=xrd-ha-app" \
        -o yaml | yq -e '.items[0].metadata.name')

    echo "# Check mounted config has expected content"
    kubectl exec "$name" -- cat /etc/ha_app/config.yaml | tee | diff "$tempfile" -

    rm -f "$tempfile"
}

@test "Config upgrade rolls the Deployment" {
    echo "# Install Helm chart with 'haApp.config=foo'"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --set 'haApp.config=foo' \
        --wait \
        --timeout=1m

    echo "# Assert the HA Pod exists"
    verify "there is 1 Pod named 'xrd-ha-app-$(release_name)-*'"
    name=$(kubectl get pod \
        -l "app.kubernetes.io/instance=$(release_name),app.kubernetes.io/name=xrd-ha-app" \
        -o yaml | yq -e '.items[0].metadata.name')

    echo "# Check mounted config is expected"
    run -0 kubectl exec "$name" -- cat /etc/ha_app/config.yaml
    assert_output "foo"

    echo "# Upgrade Helm chart with 'haApp.config=bar'"
    helm upgrade "$(release_name)" . \
        --reuse-values \
        --set 'haApp.config=bar' \
        --wait \
        --timeout=1m

    echo "# Wait for the previous Pod to terminate"
    kubectl wait --for=delete --timeout=1m pod "$name"

    echo "# Assert the HA Pod exists"
    verify "there is 1 Pod named 'xrd-ha-app-$(release_name)-*'"
    name=$(kubectl get pod \
        -l "app.kubernetes.io/instance=$(release_name),app.kubernetes.io/name=xrd-ha-app" \
        -o yaml | yq -e '.items[0].metadata.name')

    echo "# Check mounted config is expected"
    run -0 kubectl exec "$name" -- cat /etc/ha_app/config.yaml
    assert_output "bar"
}

@test "HA Pod is scheduled to same node as XRd Pod" {
    echo "# Install Helm chart with XRd scheduled to integration-tests-worker"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --set-json 'xrd.nodeSelector={"kubernetes.io/hostname": "integration-tests-worker"}' \
        --wait \
        --timeout=1m

    echo "# Assert HA Pod is scheduled to integration-tests-worker"
    verify "'.spec.nodeName' is 'integration-tests-worker' for Pod named 'xrd-ha-app-$(release_name)-*'"

    echo "# Uninstall Helm chart"
    helm uninstall "$(release_name)"

    echo "# Wait for Pods to delete"
    kubectl wait --for=delete --timeout=1m pod -l "app.kubernetes.io/instance=$(release_name)"

    echo "# Install Helm chart with XRd scheduled to integration-tests-worker2"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --set-json 'xrd.nodeSelector={"kubernetes.io/hostname": "integration-tests-worker2"}' \
        --wait \
        --timeout=1m

    echo "# Assert HA Pod is scheduled to integration-tests-worker2"
    verify "'.spec.nodeName' is 'integration-tests-worker2' for Pod named 'xrd-ha-app-$(release_name)-*'"
}

@test "ServiceAccount token is mounted correctly" {
    echo "# Install Helm chart"
    helm install "$(release_name)" . \
        -f "${BATS_TEST_DIRNAME}/default_values.yaml" \
        --wait \
        --timeout=1m

    echo "# Assert the HA Pod exists"
    verify "there is 1 Pod named 'xrd-ha-app-$(release_name)-*'"
    name=$(kubectl get pod \
        -l "app.kubernetes.io/instance=$(release_name),app.kubernetes.io/name=xrd-ha-app" \
        -o yaml | yq -e '.items[0].metadata.name')

    echo "# Check ServiceAccount token is mounted"
    run -0 kubectl exec "$name" -- stat -L /var/run/secrets/kubernetes.io/serviceaccount/token
    assert_output --partial "Access: (0600/-rw-------)"
}
