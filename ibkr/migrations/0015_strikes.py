# Generated by Django 5.1.3 on 2024-12-23 12:31

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ibkr", "0014_alter_placeorder_price_alter_systemdata_time_frame"),
    ]

    operations = [
        migrations.CreateModel(
            name="Strikes",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
                ("contract_id", models.CharField(max_length=255)),
                ("strike_price", models.FloatField()),
                ("month", models.CharField(max_length=20)),
                ("last_price", models.FloatField()),
                ("maturity_date", models.CharField(max_length=8)),
                ("is_valid", models.BooleanField(default=False)),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
