from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("components", "0005_rename_product_to_component"),
        ("rfqs", "0005_remove_quote_decided_at_remove_quote_status"),
    ]

    operations = [
        migrations.RenameField(
            model_name="rfqrecipient",
            old_name="product",
            new_name="component",
        ),
    ]
