import django.db.models.deletion
import rfqs.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rfqs", "0006_rename_product_to_component"),
        ("uploads", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rfqattachment",
            name="file",
            field=models.FileField(blank=True, null=True, upload_to=rfqs.models.rfq_attachment_path),
        ),
        migrations.AddField(
            model_name="rfqattachment",
            name="file_asset",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rfq_attachment",
                to="uploads.fileasset",
            ),
        ),
    ]
