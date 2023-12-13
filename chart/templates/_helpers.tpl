{{- define "xrd-ha-app.name" -}}
{{ .Values.haApp.name | default .Chart.Name | trimSuffix "-" }}
{{- end -}}

{{- define "xrd-ha-app.fullname" -}}
{{ printf "%s-%s" (include "xrd-ha-app.name" .) .Release.Name | trimSuffix "-" }}
{{- end -}}

{{- define "xrd-ha-app.labels.standard" -}}
app.kubernetes.io/name: {{ include "xrd-ha-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}
