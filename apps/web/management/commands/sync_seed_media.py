import os

import boto3
from botocore.exceptions import ClientError
from django.core.management.base import BaseCommand, CommandError

from apps.web.management.seed_media import (
    collect_seed_media_paths_from_generated_data,
    load_generated_seed_dict,
    resolve_local_seed_media_path,
)


class Command(BaseCommand):
    help = "Sync all media referenced by generated seed data from S3 to assets/seeds/generated/media"

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing files in assets/seeds/generated/media",
        )

    def handle(self, *args, **options):
        overwrite = options["overwrite"]

        media_paths = collect_seed_media_paths_from_generated_data()
        if not media_paths:
            self.stdout.write(self.style.WARNING("No seed media paths found in assets/seeds/generated."))
            return

        media_settings_data = load_generated_seed_dict("media_storage_settings_data.json")

        bucket_name = os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip() or media_settings_data.get(
            "aws_bucket_name", ""
        )
        aws_region = media_settings_data.get("aws_region", "eu-central-1")
        aws_location = str(media_settings_data.get("aws_location", "media") or "").strip("/")

        aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
        aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()

        if not bucket_name:
            raise CommandError("Missing AWS bucket name. Set AWS_STORAGE_BUCKET_NAME or seed config value.")

        if not aws_access_key or not aws_secret_key:
            raise CommandError("Missing AWS credentials. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )

        downloaded = 0
        skipped = 0
        missing = 0
        failed = 0
        missing_samples = []
        failed_samples = []

        for relative_path in media_paths:
            destination = resolve_local_seed_media_path(relative_path)
            if destination is None:
                failed += 1
                if len(failed_samples) < 10:
                    failed_samples.append(f"invalid destination path: {relative_path}")
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not overwrite:
                skipped += 1
                continue

            s3_key = f"{aws_location}/{relative_path}" if aws_location else relative_path

            try:
                s3_client.download_file(bucket_name, s3_key, str(destination))
                downloaded += 1
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in {"NoSuchKey", "404", "NotFound"}:
                    missing += 1
                    if len(missing_samples) < 10:
                        missing_samples.append(relative_path)
                    continue

                failed += 1
                if len(failed_samples) < 10:
                    failed_samples.append(f"{relative_path} ({error_code or 'ClientError'})")

        self.stdout.write(
            self.style.SUCCESS(
                "Seed media sync complete: "
                f"{downloaded} downloaded, {skipped} skipped, {missing} missing in S3, {failed} failed"
            )
        )

        if missing_samples:
            self.stdout.write("Missing sample paths:")
            for path in missing_samples:
                self.stdout.write(f"  - {path}")

        if failed_samples:
            self.stdout.write(self.style.WARNING("Failed sample paths:"))
            for path in failed_samples:
                self.stdout.write(self.style.WARNING(f"  - {path}"))