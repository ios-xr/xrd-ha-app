#!/usr/bin/env bats

load "utils.bash"

export TEMPLATE_UNDER_TEST="templates/deployment.yaml"

setup_file () {
    cd "$(chart_dir)" || exit
    helm dependency update .
}

@test "Deployment name consists of the release name and the chart name" {
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

@test "Recommended Pod labels are set" {
    template
    assert_query_equal '.spec.template.metadata.labels."app.kubernetes.io/name"' "xrd-ha-app"
    assert_query_equal '.spec.template.metadata.labels."app.kubernetes.io/instance"' "release-name"
    assert_query_equal '.spec.template.metadata.labels."app.kubernetes.io/managed-by"' "Helm"
    assert_query '.spec.template.metadata.labels | has("app.kubernetes.io/version")'
    assert_query '.spec.template.metadata.labels | has("helm.sh/chart")'
}

@test "Global labels can be added" {
    template --set 'global.labels.foo=bar' --set 'global.labels.baz=baa'
    assert_query_equal '.metadata.labels.foo' "bar"
    assert_query_equal '.metadata.labels.baz' "baa"
    assert_query_equal '.spec.template.metadata.labels.foo' "bar"
    assert_query_equal '.spec.template.metadata.labels.baz' "baa"
}

@test "Pod labels can be added" {
    template --set 'haApp.labels.foo=bar' --set 'haApp.labels.baz=baa'
    assert_query_equal '.spec.template.metadata.labels.foo' "bar"
    assert_query_equal '.spec.template.metadata.labels.baz' "baa"
}

@test "Global labels and Pod labels can be added at the same time" {
    template --set 'global.labels.foo=bar' --set 'haApp.labels.baz=baa'
    assert_query_equal '.metadata.labels.foo' "bar"
    assert_query_equal '.spec.template.metadata.labels.foo' "bar"
    assert_query_equal '.spec.template.metadata.labels.baz' "baa"
}

@test "Match labels are correct" {
    template
    assert_query_equal '.spec.selector.matchLabels."app.kubernetes.io/name"' "xrd-ha-app"
    assert_query_equal '.spec.selector.matchLabels."app.kubernetes.io/instance"' "release-name"
}

@test "Config checksum annotation is set" {
    template
    assert_query_equal '.spec.template.metadata.annotations.config-checksum' "761adf8d97e15214e4da44effe63bc331092f597e3089818d5825c87444b1f27"
}

@test "Config checksum annotation updates when config is set" {
    template --set 'haApp.config=foo'
    assert_query_equal '.spec.template.metadata.annotations.config-checksum' "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
}

@test "Config checksum annotation updates when config is set via '--set-file'" {
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

    template --set-file "haApp.config=$tempfile"
    assert_query_equal '.spec.template.metadata.annotations.config-checksum' "4b4c8ae76a45949a902560b29fcf837006bb2738410fd4224515cefe2ebbd66d"

    rm -f "$tempfile"
}

@test "Pod annotations can be added" {
    template --set 'haApp.annotations.foo=bar' --set 'haApp.annotations.baz=baa'
    assert_query_equal '.spec.template.metadata.annotations.foo' "bar"
    assert_query_equal '.spec.template.metadata.annotations.baz' "baa"
}

@test "Pod consists of a single container" {
    template
    assert_query_equal '.spec.template.spec.containers | length' "1"
    assert_query_equal '.spec.template.spec.containers[0].name' "main"
}

@test "Container image cannot be null" {
    run ! helm template . --set 'xrd.enabled=false' -s "$TEMPLATE_UNDER_TEST"
}

@test "Container image tag is latest" {
    template
    assert_query_equal '.spec.template.spec.containers[0].image' "ecr/xrd-ha-app:latest"
}

@test "Container image tag can be set" {
    template --set 'haApp.image.tag=1.0.0'
    assert_query_equal '.spec.template.spec.containers[0].image' "ecr/xrd-ha-app:1.0.0"
}

@test "Container image pull policy is Always" {
    template
    assert_query_equal '.spec.template.spec.containers[0].imagePullPolicy' "Always"
}

@test "Container image pull policy can be set" {
    template --set 'haApp.image.pullPolicy=IfNotPresent'
    assert_query_equal '.spec.template.spec.containers[0].imagePullPolicy' "IfNotPresent"
}

@test "Container image pull secrets can be set" {
    template --set-json 'haApp.image.pullSecrets=[{"name": "secret0"}, {"name": "secret1"}]'
    assert_query_equal '.spec.template.spec.imagePullSecrets | length' "2"
    assert_query_equal '.spec.template.spec.imagePullSecrets[0].name' "secret0"
    assert_query_equal '.spec.template.spec.imagePullSecrets[1].name' "secret1"
}

@test "Container image pull secrets can be set globally" {
    template --set-json 'global.image.pullSecrets=[{"name": "secret0"}, {"name": "secret1"}]'
    assert_query_equal '.spec.template.spec.imagePullSecrets | length' "2"
    assert_query_equal '.spec.template.spec.imagePullSecrets[0].name' "secret0"
    assert_query_equal '.spec.template.spec.imagePullSecrets[1].name' "secret1"
}

@test "Container image pull secrets are merged with those set globally" {
    template \
        --set-json 'global.image.pullSecrets=[{"name": "secret0"}]' \
        --set-json 'haApp.image.pullSecrets=[{"name": "secret1"}]'
    assert_query_equal '.spec.template.spec.imagePullSecrets | length' "2"
    assert_query_equal '.spec.template.spec.imagePullSecrets[0].name' "secret0"
    assert_query_equal '.spec.template.spec.imagePullSecrets[1].name' "secret1"
}

@test "Config volume is correctly mounted" {
    template
    assert_query_equal '.spec.template.spec.containers[0].volumeMounts | length' "1"
    assert_query_equal '.spec.template.spec.containers[0].volumeMounts[0].name' "config"
    assert_query_equal '.spec.template.spec.containers[0].volumeMounts[0].mountPath' "/etc/ha_app"
    assert_query_equal '.spec.template.spec.containers[0].volumeMounts[0].readOnly' "true"
}

@test "Pod node selector can be set" {
    template --set 'haApp.nodeSelector.name=alpha'
    assert_query_equal '.spec.template.spec.nodeSelector.name' "alpha"
}

@test "Pod is affined to the same node as the corresponding XRd Pod" {
    template
    assert_query_equal '.spec.template.spec.affinity.podAffinity.requiredDuringSchedulingIgnoredDuringExecution | length' "1"
    assert_query_equal '.spec.template.spec.affinity.podAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].labelSelector.matchLabels."app.kubernetes.io/instance"' "release-name"
    assert_query_equal '.spec.template.spec.affinity.podAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].labelSelector.matchLabels."app.kubernetes.io/name"' "xrd"
    assert_query_equal '.spec.template.spec.affinity.podAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].topologyKey' "kubernetes.io/hostname"
}

@test "Pod affinity can be overridden" {
    template --set 'haApp.nodeSelector.name=alpha'
    assert_query_equal '.spec.template.spec.nodeSelector.name' "alpha"
}

@test "Pod affinity can be overridden to null" {
    template --set 'haApp.affinity=null'
    assert_query '.spec.template.spec.affinity | not'
}

@test "Pod tolerations can be set" {
    template --set-json 'haApp.tolerations=[{"key": "key1", "operator": "Equal", "value": "value1", "effect": "NoSchedule"}]'
    assert_query_equal '.spec.template.spec.tolerations | length' "1"
    assert_query_equal '.spec.template.spec.tolerations[0].key' "key1"
    assert_query_equal '.spec.template.spec.tolerations[0].operator' "Equal"
    assert_query_equal '.spec.template.spec.tolerations[0].value' "value1"
    assert_query_equal '.spec.template.spec.tolerations[0].effect' "NoSchedule"
}

@test "Pod refers to the correct ServiceAccount" {
    template
    assert_query_equal '.spec.template.spec.serviceAccountName' "xrd-ha-app-release-name"
}

@test "Pod security context is unprivileged" {
    template
    assert_query_equal '.spec.template.spec.securityContext.runAsNonRoot' "true"
    assert_query_equal '.spec.template.spec.securityContext.runAsUser' "1000"
}

@test "Pod security context can be set" {
    template --set 'haApp.podSecurityContext.runAsGroup=1000'
    assert_query_equal '.spec.template.spec.securityContext.runAsNonRoot' "true"
    assert_query_equal '.spec.template.spec.securityContext.runAsUser' "1000"
    assert_query_equal '.spec.template.spec.securityContext.runAsGroup' "1000"
}

@test "Pod security context can be set to null" {
    template --set 'haApp.podSecurityContext=null'
    assert_query '.spec.template.spec.securityContext | not'
}

@test "Container security context can be set" {
    template --set 'haApp.containerSecurityContext.main.privileged=true'
    assert_query_equal '.spec.template.spec.containers[0].securityContext.privileged' "true"
}

@test "Resources can be set" {
    template --set 'haApp.resources.requests.memory=2Gi'
    assert_query_equal '.spec.template.spec.containers[0].resources.requests.memory' "2Gi"
}
