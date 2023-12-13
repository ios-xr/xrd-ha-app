#!/usr/bin/env bats

load "utils.bash"

export TEMPLATE_UNDER_TEST="templates/service.yaml"

setup_file () {
    cd "$(chart_dir)" || exit
    helm dependency update .
}

@test "Service name consists of the release name and the chart name" {
    template
    assert_query_equal '.metadata.name' "xrd-ha-app-release-name"
}

@test "Namespace is default" {
    template
    assert_query_equal '.metadata.namespace' "default"
}

@test "Recommended labels are set" {
    template
    assert_query_equal '.metadata.labels."app.kubernetes.io/name"' "xrd-ha-app"
    assert_query_equal '.metadata.labels."app.kubernetes.io/instance"' "release-name"
    assert_query_equal '.metadata.labels."app.kubernetes.io/managed-by"' "Helm"
    assert_query '.metadata.labels | has("app.kubernetes.io/version")'
    assert_query '.metadata.labels | has("helm.sh/chart")'
}

@test "Global labels can be added" {
    template --set 'global.labels.foo=bar' --set 'global.labels.baz=baa'
    assert_query_equal '.metadata.labels.foo' "bar"
    assert_query_equal '.metadata.labels.baz' "baa"
}

@test "Exposed port and target port are set" {
    template
    assert_query_equal '.spec.ports | length' "1"
    assert_query_equal '.spec.ports[0].port' "50051"
    assert_query_equal '.spec.ports[0].targetPort' "50051"
}

@test "Exposed port can be overridden" {
    template --set 'haApp.service.exposedPort=12345'
    assert_query_equal '.spec.ports | length' "1"
    assert_query_equal '.spec.ports[0].port' "12345"
    assert_query_equal '.spec.ports[0].targetPort' "50051"
}

@test "Target port can be overridden" {
    template --set 'haApp.service.targetPort=12345'
    assert_query_equal '.spec.ports | length' "1"
    assert_query_equal '.spec.ports[0].port' "50051"
    assert_query_equal '.spec.ports[0].targetPort' "12345"
}

@test "IP address can be set" {
    template --set 'haApp.service.clusterIP="10.0.0.10"'
    assert_query_equal '.spec.clusterIP' "10.0.0.10"
}
