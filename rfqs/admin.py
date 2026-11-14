from django.contrib import admin
from .models import RFQ, RFQRecipient, RFQAttachment

admin.site.register(RFQ)
admin.site.register(RFQRecipient)
admin.site.register(RFQAttachment)