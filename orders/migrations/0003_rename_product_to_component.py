from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_orderreview"),
        ("components", "0005_rename_product_to_component"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="product",
            new_name="component",
        ),
    ]
