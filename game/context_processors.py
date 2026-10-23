def pending_trades(request):
    """Trade offers waiting for the player's answer, for the badge on the Friends nav link."""
    user = request.user
    return {"incoming_trades": user.trades_received.count() if user.is_authenticated else 0}
