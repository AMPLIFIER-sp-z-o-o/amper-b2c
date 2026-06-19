from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Deliver pending Live Assisted Sales outbox events to LAS (durable event relay)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Max rows to deliver this pass.")

    def handle(self, *args, **options):
        from apps.live_assisted_sales.client import relay_pending_outbox

        delivered = relay_pending_outbox(limit=options["limit"])
        self.stdout.write(f"Delivered {delivered} outbox event(s).")
