from django.db import models


class ImportProcess(models.Model):
    date_added = models.DateTimeField(auto_now_add=True)
    date_finished = models.DateTimeField(null=True, blank=True)
    object_type = models.CharField(max_length=100, blank=False, db_index=True)

    def __str__(self):
        return f"ImportProcess #{self.id} ({self.object_type})"


class ImportProcessDetails(models.Model):
    import_process = models.ForeignKey(ImportProcess, related_name="details", on_delete=models.CASCADE)
    object_external_id = models.CharField(max_length=500, blank=False, null=False)

    def __str__(self):
        return f"ImportProcessDetails #{self.id} ({self.object_external_id})"


class Connector(models.Model):
    import_process = models.ForeignKey(
        ImportProcess, related_name="connectors", on_delete=models.SET_NULL, null=True, blank=True
    )
    object_type = models.CharField(max_length=100, blank=False)
    internal_id = models.CharField(max_length=500, blank=False, null=False)
    external_id = models.CharField(max_length=500, blank=False, null=False, db_index=True)
    date_added = models.DateTimeField(auto_now_add=True)
    last_modification = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("object_type", "external_id")
        indexes = [models.Index(fields=["object_type", "internal_id"])]

    def __str__(self):
        return f"Connector {self.object_type}: {self.external_id} -> {self.internal_id}"
