from django.db import migrations


def rename_content_types(apps, schema_editor, forward=True):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    database = schema_editor.connection.alias
    source_label, target_label = ("products", "components") if forward else ("components", "products")
    models = [
        ("product", "component", "product", "component"),
        ("productimage", "componentimage", "product image", "component image"),
        ("productdocument", "componentdocument", "product document", "component document"),
        (
            "productdocumentaccess",
            "componentdocumentaccess",
            "product document access",
            "component document access",
        ),
    ]
    if not forward:
        models = [(new, old, new_words, old_words) for old, new, old_words, new_words in models]

    for old_model, new_model, old_words, new_words in models:
        old_type = ContentType.objects.using(database).filter(
            app_label=source_label, model=old_model
        ).first()
        if old_type is None:
            continue
        if ContentType.objects.using(database).filter(
            app_label=target_label, model=new_model
        ).exists():
            raise RuntimeError(
                f"Content type {target_label}.{new_model} already exists; cannot rename safely."
            )

        old_type.app_label = target_label
        old_type.model = new_model
        old_type.save(using=database, update_fields=["app_label", "model"])

        for permission in Permission.objects.using(database).filter(content_type_id=old_type.pk):
            permission.codename = permission.codename.replace(old_model, new_model)
            permission.name = permission.name.replace(old_words, new_words)
            permission.save(using=database, update_fields=["codename", "name"])


class Migration(migrations.Migration):

    dependencies = [
        ("components", "0004_productdocumentaccess_rfq_delete_productreview"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Product",
            new_name="Component",
        ),
        migrations.RenameModel(
            old_name="ProductImage",
            new_name="ComponentImage",
        ),
        migrations.RenameModel(
            old_name="ProductDocument",
            new_name="ComponentDocument",
        ),
        migrations.RenameModel(
            old_name="ProductDocumentAccess",
            new_name="ComponentDocumentAccess",
        ),
        migrations.RenameField(
            model_name="componentimage",
            old_name="product",
            new_name="component",
        ),
        migrations.RenameField(
            model_name="componentdocument",
            old_name="product",
            new_name="component",
        ),
        migrations.AlterModelTable(
            name="component",
            table="components",
        ),
        migrations.AlterModelTable(
            name="componentimage",
            table="component_images",
        ),
        migrations.AlterModelTable(
            name="componentdocument",
            table="component_documents",
        ),
        migrations.RunPython(
            rename_content_types,
            reverse_code=lambda apps, schema_editor: rename_content_types(
                apps, schema_editor, forward=False
            ),
        ),
    ]
