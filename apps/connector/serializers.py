from rest_framework import serializers


class StockLocationImportItemSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=500)
    name = serializers.CharField(max_length=200)


class StockImportItemSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=500)
    product_external_id = serializers.CharField(max_length=500)
    stock_level_external_id = serializers.CharField(max_length=500)
    quantity = serializers.IntegerField(min_value=0)
