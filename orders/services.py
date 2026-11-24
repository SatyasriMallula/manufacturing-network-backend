from .models import Order, OrderStatusHistory


def create_order_from_award(rfq, recipient, created_by):
    quote = recipient.quote
    order = Order.objects.create(
        rfq=rfq,
        quote=quote,
        buyer_organization=rfq.buyer_organization,
        vendor_organization=recipient.vendor_organization,
        component=recipient.component,
        created_by=created_by,
        title=rfq.title,
        quantity=rfq.quantity,
        unit_of_measurement=rfq.unit_of_measurement,
        unit_price=quote.unit_price,
        total_price=quote.total_price,
        currency=quote.currency,
        delivery_days=quote.delivery_days,
    )
    OrderStatusHistory.objects.create(
        order=order, from_status="", to_status=order.status,
        changed_by=created_by, note="Order placed from awarded RFQ",
    )
    return order