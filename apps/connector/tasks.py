from celery import shared_task
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Product, ProductStock, Warehouse

from .models import Connector, ImportProcess, ImportProcessDetails
from .names import PRODUCT_MODEL_NAME, STOCKS_LOCATION_MODEL_NAME, STOCKS_MODEL_NAME
from .services import resolve_external_ids


def start_new_import_process(object_type: str) -> int:
    return ImportProcess.objects.create(object_type=object_type).pk


def finish_import_process(import_process_id: int) -> None:
    ImportProcess.objects.filter(pk=import_process_id).update(date_finished=timezone.now())


def create_or_update_connector_entry(import_process_id: int, object_type: str, external_id: str, internal_id: int) -> None:
    Connector.objects.update_or_create(
        object_type=object_type,
        external_id=external_id,
        defaults={"internal_id": str(internal_id), "import_process_id": import_process_id},
    )


def _resolve_connector_targets(*, object_type: str, external_ids: set[str], model, field_name: str):
    external_to_internal = resolve_external_ids(object_type=object_type, external_ids=external_ids)
    missing = sorted(external_ids - set(external_to_internal.keys()))
    if missing:
        raise ValidationError({field_name: f"Unknown {object_type} external IDs: {', '.join(missing)}"})

    try:
        internal_ids = {int(value) for value in external_to_internal.values()}
    except (TypeError, ValueError) as exc:
        raise ValidationError({field_name: f"Invalid connector mapping for object type '{object_type}'"}) from exc

    objects_by_id = model.objects.in_bulk(internal_ids)
    stale = sorted(
        external_id
        for external_id, internal_id in external_to_internal.items()
        if int(internal_id) not in objects_by_id
    )
    if stale:
        raise ValidationError({field_name: f"Stale connector mappings for external IDs: {', '.join(stale)}"})

    return {external_id: objects_by_id[int(internal_id)] for external_id, internal_id in external_to_internal.items()}


def import_stock_locations(data: list[dict], import_process_id: int) -> None:
    with transaction.atomic():
        connectors_by_external_id = {
            connector.external_id: connector
            for connector in Connector.objects.filter(
                object_type=STOCKS_LOCATION_MODEL_NAME,
                external_id__in=[item["external_id"] for item in data],
            )
        }
        for item in data:
            ImportProcessDetails.objects.create(import_process_id=import_process_id, object_external_id=item["external_id"])
            connector = connectors_by_external_id.get(item["external_id"])
            warehouse = None
            if connector:
                warehouse = Warehouse.objects.filter(pk=int(connector.internal_id)).first()

            if warehouse is None:
                warehouse = Warehouse.objects.create(name=item["name"])
            elif warehouse.name != item["name"]:
                warehouse.name = item["name"]
                warehouse.save(update_fields=["name", "updated_at"])

            create_or_update_connector_entry(import_process_id, STOCKS_LOCATION_MODEL_NAME, item["external_id"], warehouse.pk)

    finish_import_process(import_process_id)


def import_stocks(data: list[dict], import_process_id: int) -> None:
    product_map = _resolve_connector_targets(
        object_type=PRODUCT_MODEL_NAME,
        external_ids={item["product_external_id"] for item in data},
        model=Product,
        field_name="product_external_id",
    )
    warehouse_map = _resolve_connector_targets(
        object_type=STOCKS_LOCATION_MODEL_NAME,
        external_ids={item["stock_level_external_id"] for item in data},
        model=Warehouse,
        field_name="stock_level_external_id",
    )

    with transaction.atomic():
        existing_stock_connectors = {
            connector.external_id: connector
            for connector in Connector.objects.filter(object_type=STOCKS_MODEL_NAME)
        }
        incoming_external_ids = {item["external_id"] for item in data}

        for item in data:
            ImportProcessDetails.objects.create(import_process_id=import_process_id, object_external_id=item["external_id"])

            product = product_map[item["product_external_id"]]
            warehouse = warehouse_map[item["stock_level_external_id"]]

            connector = existing_stock_connectors.get(item["external_id"])
            stock = None
            if connector:
                stock = ProductStock.objects.filter(pk=int(connector.internal_id)).first()
            if stock is None:
                stock = ProductStock.objects.filter(product=product, warehouse=warehouse).first()

            if stock is None:
                stock = ProductStock.objects.create(product=product, warehouse=warehouse, quantity=item["quantity"])
            else:
                previous_product_id = stock.product_id
                stock.product = product
                stock.warehouse = warehouse
                stock.quantity = item["quantity"]
                stock.save(update_fields=["product", "warehouse", "quantity", "updated_at"])
                if previous_product_id != product.pk:
                    Product.sync_total_stock(previous_product_id)

            create_or_update_connector_entry(import_process_id, STOCKS_MODEL_NAME, item["external_id"], stock.pk)

        stale_connectors = Connector.objects.filter(object_type=STOCKS_MODEL_NAME).exclude(external_id__in=incoming_external_ids)
        for connector in stale_connectors:
            stock = ProductStock.objects.filter(pk=int(connector.internal_id)).first()
            if stock:
                stock.delete()
            connector.delete()

    finish_import_process(import_process_id)


@shared_task(queue="default")
def import_stock_locations_task(data: list[dict], import_process_id: int) -> None:
    import_stock_locations(data, import_process_id)


@shared_task(queue="default")
def import_stocks_task(data: list[dict], import_process_id: int) -> None:
    import_stocks(data, import_process_id)