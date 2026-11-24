from django.contrib import admin
from .models import Component, ComponentImage, ComponentDocument


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    pass


@admin.register(ComponentImage)
class ComponentImageAdmin(admin.ModelAdmin):
    pass


@admin.register(ComponentDocument)
class ComponentDocumentAdmin(admin.ModelAdmin):
    pass
