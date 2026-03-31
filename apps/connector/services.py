from .models import Connector


def resolve_external_ids(object_type: str, external_ids) -> dict[str, str]:
    return {
        connector.external_id: connector.internal_id
        for connector in Connector.objects.filter(object_type=object_type, external_id__in=external_ids)
    }
