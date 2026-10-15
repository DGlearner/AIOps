from typing import Any

from crossst.domain.models.incident import Incident


def build_incident_context_from_record(incident: Incident) -> dict[str, Any]:
    return {
        "incident_id": incident.incident_id,
        "summary": incident.summary,
        "event_types": incident.event_types,
        "affected_hosts": incident.affected_hosts,
        "affected_services": incident.affected_services,
        "aggregate_key": incident.aggregate_key,
        "time_window_start": incident.time_window_start.isoformat(),
        "time_window_end": incident.time_window_end.isoformat(),
    }

