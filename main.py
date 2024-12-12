import MetaTrader5 as mt5
from settings import (
    account_size,
    target_gain_percent,
    number_of_pips,
    initial_stop_level,
    initial_stop_percent,
    symbol,
    top_up_levels1,
    top_up_levels2,
    top_up_levels3,
)


def get_pip_value(symbol):
    """
    Calculate the pip value for a given symbol dynamically from MT5.
    """
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")

    contract_size = symbol_info.trade_contract_size
    point = symbol_info.point
    pip_value = contract_size * point
    return pip_value

def get_spread_in_pips(symbol):
    """
    Retrieve the spread in pips for a given symbol.
    """
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return None
    spread = mt5.symbol_info(symbol).spread
    point = mt5.symbol_info(symbol).point
    return spread * point

def calculate_pip_gain(number_of_pips, spread_in_pips, top_up_levels1, top_up_levels2, top_up_levels3):
    """
    Beräknar pip gain för initial order och stop orders.
    """
    pip_gains = {
        'initial': round(number_of_pips - spread_in_pips, 2),
        'stop_1': round(number_of_pips * (1 - (top_up_levels1 / 100)) - spread_in_pips, 2),
        'stop_2': round(number_of_pips * (1 - (top_up_levels2 / 100)) - spread_in_pips, 2),
        'stop_3': round(number_of_pips * (1 - (top_up_levels3 / 100)) - spread_in_pips, 2)
    }
    return pip_gains

def calculate_gain_in_dollars(lot_size, pip_gain, pip_value):
    """
    Calculate the gain in dollars for a given lot size and pip gain.
    """
    return round(lot_size * pip_gain * pip_value, 2)


def calculate_loss_in_dollars(initial_stop_percent, account_size):
    """
    Calculate the loss in dollars based on the risk percentage and account size.
    """
    return (initial_stop_percent / 100) * account_size


def place_market_order(symbol, action, lot_size, tp_distance, sl_distance, magic_number):
    """
    Places a market order (BUY/SELL) with TP and SL distances in pips.

    :param symbol: Trading symbol (e.g., "XAUUSD").
    :param action: "BUY" or "SELL".
    :param lot_size: Lot size for the market order.
    :param tp_distance: Distance to Take Profit in pips.
    :param sl_distance: Distance to Stop Loss in pips.
    :param magic_number: Magic number to identify the order.
    :return: Result of the order_send operation.
    """
    # Ensure the symbol is available
    if not mt5.symbol_select(symbol, True):
        print(f"Failed to select symbol {symbol}.")
        return None

    # Get the current price
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"Failed to retrieve tick data for {symbol}.")
        return None

    price = tick.ask if action == "BUY" else tick.bid
    point = mt5.symbol_info(symbol).point

    # Calculate TP and SL prices
    tp_price = price + (tp_distance * point) if action == "BUY" else price - (tp_distance * point)
    sl_price = price - (sl_distance * point) if action == "BUY" else price + (sl_distance * point)

    # Prepare the trade request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "tp": tp_price,
        "sl": sl_price,
        "deviation": 10,
        "magic": magic_number,
        "comment": f"{action} order via script",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    # Send the trade request
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to place {action} order: {result.retcode}")
        return None

    print(f"{action} order placed successfully: {result}")
    return result


def place_stop_orders(symbol, action, lot_sizes, tp_price, stop_levels, magic_number):
    """
    Places additional stop orders (BUY STOP / SELL STOP) with shared TP.

    :param symbol: Trading symbol (e.g., "XAUUSD").
    :param action: "BUY" or "SELL".
    :param lot_sizes: List of lot sizes for each stop order.
    :param tp_price: Take Profit price for all stop orders.
    :param stop_levels: List of price levels for stop orders.
    :param magic_number: Magic number to identify the orders.
    """
    for level, lot_size in zip(stop_levels, lot_sizes):
        # Determine the order type
        order_type = mt5.ORDER_TYPE_BUY_STOP if action == "BUY" else mt5.ORDER_TYPE_SELL_STOP

        # Prepare the stop order request
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": level,
            "tp": tp_price,
            "sl": 0.0,  # No SL for stop orders
            "deviation": 10,
            "magic": magic_number,
            "comment": f"{action} STOP order via script",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Send the request
        result = mt5.order_send(request)

        # Check if result is None
        if result is None:
            print(f"Failed to send {action} STOP order at level {level}. Result is None.")
            continue

        # Handle result and log response
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to place {action} STOP order at level {level}: {result.retcode}")
        else:
            print(f"{action} STOP order placed successfully at level {level}: {result}")


def calculate_initial_lot_size(loss_in_dollars, sl_distance, pip_value):
    """
    Calculate the initial lot size based on dollar loss, stop-loss distance, and pip value.
    :param loss_in_dollars: The maximum allowed dollar loss for the trade.
    :param sl_distance: Distance to stop-loss in pips.
    :param pip_value: Value of one pip for the symbol.
    :return: Lot size for the initial order.
    """
    return round(loss_in_dollars / (sl_distance * pip_value), 2)


def calculate_stop_levels(tp_distance, top_up_levels):
    """
    Calculate stop levels based on TP distance and percentage levels.
    """
    return [tp_distance * (level / 100) for level in top_up_levels]


def calculate_order_contributions(lot_size, tp_price, stop_levels, current_price, pip_value):
    """
    Calculate the profit contributions of all orders based on their distance to TP.
    """
    contributions = []

    market_order_distance = abs(tp_price - current_price)
    market_order_pips = market_order_distance / mt5.symbol_info(symbol).point
    contributions.append(round(lot_size * market_order_pips * pip_value, 2))

    for stop_level in stop_levels:
        stop_order_distance = abs(tp_price - stop_level)
        stop_order_pips = stop_order_distance / mt5.symbol_info(symbol).point
        contributions.append(round(lot_size * stop_order_pips * pip_value, 2))

    total_contribution = sum(contributions)
    return contributions, total_contribution


def print_order_contributions_with_be(contributions, lot_sizes, be_levels, total_contribution, direction):
    """
    Print the contributions, lot sizes, and BE levels for each order in a given direction (BUY/SELL).

    :param contributions: List of contributions in dollars for each order.
    :param lot_sizes: List of lot sizes for each order.
    :param be_levels: List of break-even levels in pips for stop orders.
    :param total_contribution: Total contribution in dollars.
    :param direction: Direction (e.g., "BUY" or "SELL").
    """
    print(f"\n{direction} Orders:")
    for i, (contribution, lot_size) in enumerate(zip(contributions, lot_sizes), start=1):
        # Include BE level if it's a stop order (not the initial market order)
        be_level = f"BE_Level_{i - 1}: {be_levels[i - 2]} pips" if i > 1 else ""
        print(f"  Order {i}: ${contribution:.2f} (Lot Size: {lot_size:.2f}) {be_level}")
    print(f"  Total {direction} Contribution: ${total_contribution:.2f}")


def calculate_stepped_lot_sizes(initial_lot_size, total_goal, tp_distance, pip_value, num_orders):
    """
    Calculate progressively increasing lot sizes to reach the total goal.

    :param initial_lot_size: Lot size for the initial market order.
    :param total_goal: Target profit in dollars.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :param num_orders: Total number of orders in one direction (including market and stop orders).
    :return: List of lot sizes for each order.
    """
    # Calculate the required contribution per pip for the total goal
    total_pip_value = total_goal / (tp_distance * pip_value)
    lot_sizes = [initial_lot_size]

    current_contribution = initial_lot_size * tp_distance * pip_value

    for i in range(num_orders - 1):
        # Remaining goal after previous contributions
        remaining_goal = total_goal - current_contribution

        # Remaining orders to contribute
        remaining_orders = num_orders - len(lot_sizes)

        # Calculate the required lot size for the next order
        next_lot_size = remaining_goal / (remaining_orders * tp_distance * pip_value)
        next_lot_size = max(next_lot_size, lot_sizes[-1])  # Ensure progressive increase
        lot_sizes.append(round(next_lot_size, 2))

        # Update the current contribution
        current_contribution += next_lot_size * tp_distance * pip_value

    return lot_sizes


def calculate_stepped_lot_sizes_exact(initial_lot_size, total_goal, tp_distance, pip_value, num_orders):
    """
    Calculate dynamically adjusted lot sizes to match the exact total goal.

    :param initial_lot_size: Lot size for the initial market order.
    :param total_goal: Target profit in dollars.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :param num_orders: Total number of orders in one direction (including market and stop orders).
    :return: List of lot sizes for each order.
    """
    lot_sizes = [initial_lot_size]
    current_total = initial_lot_size * tp_distance * pip_value

    for i in range(num_orders - 1):
        # Remaining goal after current contributions
        remaining_goal = total_goal - current_total

        # Calculate the required lot size for the next order
        next_lot_size = remaining_goal / ((num_orders - len(lot_sizes)) * tp_distance * pip_value)

        # Append and update total contribution
        lot_sizes.append(round(next_lot_size, 2))
        current_total += next_lot_size * tp_distance * pip_value

    # Final adjustment to ensure exact match
    final_adjustment = (total_goal - sum([lot * tp_distance * pip_value for lot in lot_sizes])) / (
                tp_distance * pip_value)
    lot_sizes[-1] += round(final_adjustment, 2)

    return lot_sizes


def calculate_be_levels(initial_lot_size, lot_sizes, tp_distance, pip_value):
    """
    Calculate the break-even levels for each stop order.

    :param initial_lot_size: Lot size for the initial market order.
    :param lot_sizes: List of lot sizes for stop orders.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :return: List of break-even levels in pips.
    """
    be_levels = []
    cumulative_profit = 0

    # Calculate BE levels for each stop order
    for i, lot_size in enumerate(lot_sizes, start=1):
        # Profit from previous orders
        cumulative_profit += initial_lot_size * tp_distance * pip_value

        # BE level for the current stop order
        be_level = cumulative_profit / (lot_size * pip_value)
        be_levels.append(round(be_level, 2))

    return be_levels


def verify_total_contribution(lot_sizes, tp_distance, pip_value):
    """
    Verify the total contribution from all orders matches the total goal.

    :param lot_sizes: List of lot sizes for all orders.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :return: Total contribution in dollars.
    """
    total_contribution = sum(lot_size * tp_distance * pip_value for lot_size in lot_sizes)
    return total_contribution


def calculate_contributions(lot_sizes, tp_distance, pip_value):
    """
    Calculate contributions in dollars for each order based on lot sizes.

    :param lot_sizes: List of lot sizes for all orders.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :return: List of contributions for each order and total contribution.
    """
    contributions = [round(lot_size * tp_distance * pip_value, 2) for lot_size in lot_sizes]
    total_contribution = round(sum(contributions), 2)
    return contributions, total_contribution


def main():
    # Ensure MetaTrader 5 is initialized
    if not mt5.initialize():
        print("MetaTrader 5 initialization failed. Ensure the terminal is running.")
        raise RuntimeError("Failed to initialize MetaTrader 5")

    try:
        # Fetch spread and pip value
        spread_in_pips = get_spread_in_pips(symbol)
        if spread_in_pips is None:
            raise RuntimeError("Failed to retrieve spread in pips.")
        pip_value = get_pip_value(symbol)
        if pip_value is None:
            raise RuntimeError("Failed to retrieve pip value.")
        print(f"Spread in pips for {symbol}: {spread_in_pips:.2f}")
        print(f"Pip value for {symbol}: {pip_value:.2f}")

        # Calculate total goal and loss in dollars
        total_gain = (account_size * target_gain_percent) / 100
        print(f"Total Goal (Profit Target): ${total_gain:.2f}")
        loss_in_dollars = calculate_loss_in_dollars(initial_stop_percent, account_size)

        # Calculate initial lot size
        initial_lot_size = calculate_initial_lot_size(
            loss_in_dollars=loss_in_dollars,
            sl_distance=initial_stop_level,
            pip_value=pip_value
        )
        print(f"Initial Lot Size: {initial_lot_size:.2f}")

        # Calculate pip gains
        pip_gains = calculate_pip_gain(number_of_pips, spread_in_pips, top_up_levels1, top_up_levels2, top_up_levels3)

        # Calculate gains in dollars for each level
        gain_in_dollars_initial = calculate_gain_in_dollars(initial_lot_size, pip_gains['initial'], pip_value)
        gain_in_dollars_stop_1 = ((total_gain - gain_in_dollars_initial) * top_up_levels1) / (
                top_up_levels1 + top_up_levels2 + top_up_levels3)
        gain_in_dollars_stop_2 = ((total_gain - gain_in_dollars_initial) * top_up_levels2) / (
                top_up_levels1 + top_up_levels2 + top_up_levels3)
        gain_in_dollars_stop_3 = ((total_gain - gain_in_dollars_initial) * top_up_levels3) / (
                top_up_levels1 + top_up_levels2 + top_up_levels3)

        # Calculate lot sizes for stop orders
        lots_stop_1 = gain_in_dollars_stop_1 / (pip_gains['stop_1'] * pip_value)
        lots_stop_2 = gain_in_dollars_stop_2 / (pip_gains['stop_2'] * pip_value)
        lots_stop_3 = gain_in_dollars_stop_3 / (pip_gains['stop_3'] * pip_value)

        # Combine lot sizes into a list
        lot_sizes = [initial_lot_size, lots_stop_1, lots_stop_2, lots_stop_3]

        # Calculate break-even levels for each stop order
        be_levels = calculate_be_levels(
            initial_lot_size=initial_lot_size,
            lot_sizes=lot_sizes[1:],  # Exclude the initial order
            tp_distance=number_of_pips,
            pip_value=pip_value
        )

        # Print calculated lot sizes and BE levels
        print("\n--- BUY Orders ---")
        buy_tp_price = mt5.symbol_info_tick(symbol).ask + (number_of_pips * mt5.symbol_info(symbol).point)
        print_order_contributions_with_be(
            contributions=[
                gain_in_dollars_initial,
                gain_in_dollars_stop_1,
                gain_in_dollars_stop_2,
                gain_in_dollars_stop_3
            ],
            lot_sizes=lot_sizes,
            be_levels=be_levels,
            total_contribution=total_gain,
            direction="BUY"
        )

        print("\n--- SELL Orders ---")
        sell_tp_price = mt5.symbol_info_tick(symbol).bid - (number_of_pips * mt5.symbol_info(symbol).point)
        print_order_contributions_with_be(
            contributions=[
                gain_in_dollars_initial,
                gain_in_dollars_stop_1,
                gain_in_dollars_stop_2,
                gain_in_dollars_stop_3
            ],
            lot_sizes=lot_sizes,
            be_levels=be_levels,
            total_contribution=total_gain,
            direction="SELL"
        )

        # Confirm before placing orders
        confirm = input("\nDo you want to proceed with placing the orders? (Y/N): ").strip().upper()
        if confirm == "Y":
            print("Proceeding to place orders...")

            # Place initial market orders
            place_market_order(symbol, "BUY", lot_sizes[0], number_of_pips, initial_stop_level, 1001)
            place_market_order(symbol, "SELL", lot_sizes[0], number_of_pips, initial_stop_level, 1002)

            # Place STOP orders
            stop_levels_buy = [
                mt5.symbol_info_tick(symbol).ask + (top_up_levels1 * mt5.symbol_info(symbol).point),
                mt5.symbol_info_tick(symbol).ask + (top_up_levels2 * mt5.symbol_info(symbol).point),
                mt5.symbol_info_tick(symbol).ask + (top_up_levels3 * mt5.symbol_info(symbol).point)
            ]
            stop_levels_sell = [
                mt5.symbol_info_tick(symbol).bid - (top_up_levels1 * mt5.symbol_info(symbol).point),
                mt5.symbol_info_tick(symbol).bid - (top_up_levels2 * mt5.symbol_info(symbol).point),
                mt5.symbol_info_tick(symbol).bid - (top_up_levels3 * mt5.symbol_info(symbol).point)
            ]

            place_stop_orders(symbol, "BUY", lot_sizes[1:], buy_tp_price, stop_levels_buy, 1001)
            place_stop_orders(symbol, "SELL", lot_sizes[1:], sell_tp_price, stop_levels_sell, 1002)

            print("All orders have been placed successfully.")
        else:
            print("Order placement canceled by user.")

    finally:
        pass



if __name__ == "__main__":
    main()
