from django.contrib import admin
from .models import Order, OrderReview, OrderStatusHistory

admin.site.register(Order)
admin.site.register(OrderStatusHistory)
admin.site.register(OrderReview)