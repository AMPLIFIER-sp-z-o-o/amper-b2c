from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes

from amplifier.settings import DEBUG
from apps.api.permissions import HasUserAPIKey

from .serializers import StockImportItemSerializer, StockLocationImportItemSerializer
from .tasks import (
    import_stock_locations,
    import_stock_locations_task,
    import_stocks,
    import_stocks_task,
    start_new_import_process,
)
from .names import STOCKS_LOCATION_MODEL_NAME, STOCKS_MODEL_NAME


def _dispatch(sync_task, async_task, data, object_type: str):
    if data:
        import_process_id = start_new_import_process(object_type)
        if DEBUG:
            sync_task(data, import_process_id)
        else:
            async_task.delay(data, import_process_id)
    return HttpResponse(None, status=status.HTTP_201_CREATED)


@extend_schema(tags=["connector"], request=StockLocationImportItemSerializer(many=True), responses={201: None})
@api_view(["POST"])
@permission_classes([HasUserAPIKey])
def import_stock_locations_view(request):
    serializer = StockLocationImportItemSerializer(data=request.data, many=True)
    serializer.is_valid(raise_exception=True)
    payload = [dict(item) for item in serializer.validated_data]
    return _dispatch(import_stock_locations, import_stock_locations_task, payload, STOCKS_LOCATION_MODEL_NAME)


@extend_schema(tags=["connector"], request=StockImportItemSerializer(many=True), responses={201: None})
@api_view(["POST"])
@permission_classes([HasUserAPIKey])
def import_stocks_view(request):
    serializer = StockImportItemSerializer(data=request.data, many=True)
    serializer.is_valid(raise_exception=True)
    payload = [dict(item) for item in serializer.validated_data]
    return _dispatch(import_stocks, import_stocks_task, payload, STOCKS_MODEL_NAME)