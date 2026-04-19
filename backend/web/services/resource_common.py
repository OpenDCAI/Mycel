"""Compatibility shell for shared resource helper functions."""

from backend import resource_common as _resource_common

CATALOG = _resource_common.CATALOG
CatalogEntry = _resource_common.CatalogEntry
aggregate_provider_telemetry = _resource_common.aggregate_provider_telemetry
empty_capabilities = _resource_common.empty_capabilities
metric = _resource_common.metric
resolve_card_cpu_metric = _resource_common.resolve_card_cpu_metric
resolve_console_url = _resource_common.resolve_console_url
resolve_instance_capabilities = _resource_common.resolve_instance_capabilities
resolve_provider_name = _resource_common.resolve_provider_name
resolve_provider_type = _resource_common.resolve_provider_type
thread_owners = _resource_common.thread_owners
to_resource_metrics = _resource_common.to_resource_metrics
to_resource_status = _resource_common.to_resource_status
