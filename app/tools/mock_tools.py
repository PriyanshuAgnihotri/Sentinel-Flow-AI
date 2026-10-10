from app.schemas.workflow import OrderStatusArgs, RefundArgs, TicketArgs, DeleteAccountArgs

# Deliberately deterministic mock data; replace with authenticated service integrations.
ORDERS = {"#12345": {"status": "shipped", "eta": "2026-10-13"}, "ORD-100": {"status": "processing", "eta": "2026-10-15"}}

def get_order_status(order_id: str) -> dict:
    args = OrderStatusArgs(order_id=order_id)
    order = ORDERS.get(args.order_id.upper()) or ORDERS.get(args.order_id)
    if not order:
        return {"found": False, "order_id": args.order_id}
    return {"found": True, "order_id": args.order_id, **order}

def create_support_ticket(subject: str, description: str, priority: str = "normal") -> dict:
    args = TicketArgs(subject=subject, description=description, priority=priority)
    # In production this ID comes from the ticketing system.
    return {"ticket_id": "TKT-DEMO-001", "subject": args.subject, "priority": args.priority, "status": "created"}

def issue_refund(order_id: str, amount: float) -> dict:
    args = RefundArgs(order_id=order_id, amount=amount)
    raise PermissionError(f"Refund for {args.order_id} requires an approved human decision")

def delete_user_account(user_id: str) -> dict:
    DeleteAccountArgs(user_id=user_id)
    raise PermissionError("Account deletion is disabled in the demo and always requires a verified approval workflow")
