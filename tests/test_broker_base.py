"""The broker interface's handling of orders whose outcome we cannot know."""

from tb_utils.broker.base import BrokerAdapter, BrokerOrderInfo, OrderResult, OrderSide, OrderStatus


def test_an_order_result_is_not_unknown_unless_the_adapter_says_so():
    assert OrderResult("1", OrderStatus.PENDING).outcome_unknown is False
    assert (
        OrderResult(
            "", OrderStatus.REJECTED, message="timed out", outcome_unknown=True
        ).outcome_unknown
        is True
    )


def test_a_broker_that_cannot_be_asked_returns_none_not_an_empty_list():
    """None means "cannot verify"; an empty list would wrongly mean "nothing was placed"."""

    # The method needs no state, so it can be called without building a full adapter.
    assert BrokerAdapter.find_orders(None, "optexec:1", ["X"]) is None  # type: ignore[arg-type]


def test_broker_order_info_carries_what_is_needed_to_book_a_fill():
    info = BrokerOrderInfo(
        "A1", "NIFTY26NOV0322800CE", OrderSide.BUY, OrderStatus.FILLED, 65, 190.5
    )
    assert (info.order_id, info.symbol, info.side, info.filled_quantity, info.avg_fill_price) == (
        "A1",
        "NIFTY26NOV0322800CE",
        OrderSide.BUY,
        65,
        190.5,
    )
