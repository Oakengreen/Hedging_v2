import MetaTrader5 as mt5
import threading
import time
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

    #print(f"{action} order placed successfully: {result}")
    return result


def adjust_volume(symbol, volume):
    """
    Adjust the lot size (volume) to the nearest valid step for the given symbol.

    :param symbol: Trading symbol (e.g., "XAUUSD").
    :param volume: Original volume to adjust.
    :return: Adjusted volume.
    """
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")

    volume_step = symbol_info.volume_step
    volume_min = symbol_info.volume_min
    volume_max = symbol_info.volume_max

    # Adjust volume to nearest multiple of volume_step and round to two decimals
    adjusted_volume = round(round(volume / volume_step) * volume_step, 2)

    # Ensure volume is within min/max limits
    if adjusted_volume < volume_min:
        adjusted_volume = volume_min
    elif adjusted_volume > volume_max:
        adjusted_volume = volume_max

    return adjusted_volume


def place_stop_orders(symbol, action, lot_sizes, tp_price, stop_levels, be_levels, magic_number):
    """
    Place stop orders with SL based on BE levels.

    :param symbol: Trading symbol (e.g., "XAUUSD").
    :param action: "BUY" or "SELL".
    :param lot_sizes: List of lot sizes for stop orders.
    :param tp_price: Take Profit price for the orders.
    :param stop_levels: Validated stop levels.
    :param be_levels: Break-even levels for SL calculation.
    :param magic_number: Magic number to identify the orders.
    """
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")
    point = mt5.symbol_info(symbol).point
    current_price = tick.ask if action == "BUY" else tick.bid

    for level, lot_size, be_level in zip(stop_levels, lot_sizes, be_levels):
        # Determine SL price based on BE level
        sl_price = (current_price - (be_level * point)) if action == "BUY" else (current_price + (be_level * point))

        # Determine order type
        order_type = mt5.ORDER_TYPE_BUY_STOP if action == "BUY" else mt5.ORDER_TYPE_SELL_STOP

        # Prepare the stop order request
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": round(lot_size, 2),
            "type": order_type,
            "price": level,
            "tp": tp_price,
            "sl": sl_price,
            "deviation": 10,
            "magic": magic_number,
            "comment": f"{action} STOP order via script",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        #print("\nAttempting to place STOP order:")
        #print(f"  Action: {action}")
        #print(f"  Lot Size: {lot_size}")
        #print(f"  SL: {sl_price}")
        #print(f"  TP: {tp_price}")
        #print(f"  Comment: {request['comment']}")
        #print(f"  Request Data: {request}")

        # Send the request
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to place {action} STOP order at level {level:.2f}: {result.retcode}")
        else:
            print(f"{action} STOP order placed successfully at level {level:.2f}: {result}")


def calculate_initial_lot_size(loss_in_dollars, sl_distance, pip_value):
    """
    Calculate the initial lot size based on dollar loss, stop-loss distance, and pip value.
    :param loss_in_dollars: The maximum allowed dollar loss for the trade.
    :param sl_distance: Distance to stop-loss in pips.
    :param pip_value: Value of one pip for the symbol.
    :return: Lot size for the initial order.
    """
    return round(loss_in_dollars / (sl_distance * pip_value), 2)


def calculate_stop_levels(symbol, action, top_up_levels, number_of_pips):
    """
    Calculate and validate stop levels for a given symbol and action.
    """
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")

    min_stop_distance = symbol_info.trade_stops_level * symbol_info.point

    current_price = tick.ask if action == "BUY" else tick.bid

    # Calculate raw stop levels
    raw_levels = [
        current_price + (level / 100 * number_of_pips * symbol_info.point) if action == "BUY" else
        current_price - (level / 100 * number_of_pips * symbol_info.point)
        for level in top_up_levels
    ]

    # Validate levels against min stop distance
    valid_levels = []
    for level in raw_levels:
        distance_from_current_price = abs(level - current_price) / symbol_info.point  # Convert to pips
        print(f"Checking level {level:.2f}: Distance from current price = {distance_from_current_price:.2f} pips")
        if abs(level - current_price) >= min_stop_distance:
            valid_levels.append(round(level, symbol_info.digits))
        else:
            print(f"Invalid stop level {level:.2f}: Distance ({distance_from_current_price:.2f} pips) < Minimum ({min_stop_distance / symbol_info.point:.2f} pips)")
    print(f"Validated Levels: {valid_levels}")
    return valid_levels


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


def print_order_contributions_with_be(contributions, lot_sizes, be_levels, total_contribution, direction, sl_levels, symbol):
    """
    Print the contributions, lot sizes, BE levels, and SL levels for each order in a given direction (BUY/SELL).
    """
    symbol_info = mt5.symbol_info(symbol)
    print(f"\n--- {direction} Orders ---\n")
    for i, (contribution, lot_size) in enumerate(zip(contributions, lot_sizes), start=1):
        # Include BE level if it's a stop order (not the initial market order)
        be_level_text = f"BE_Level_{i - 1}: {be_levels[i - 2]:.2f} pips" if i > 1 else ""

        # Correctly display SL levels in pips
        sl_level_text = f"SL_Level: {sl_levels[i - 1] / symbol_info.point:.1f} pips" if i <= len(sl_levels) else "SL_Level: N/A"

        print(f"  Order {i}: ${contribution:.2f} (Lot Size: {lot_size:.2f}) {be_level_text} {sl_level_text}")
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


def validate_stop_levels(symbol, stop_levels):
    """
    Validate that stop levels are within the acceptable range for the symbol.
    """
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")

    min_stop_distance = symbol_info.trade_stops_level * symbol_info.point

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")

    valid_levels = []
    for level in stop_levels:
        if abs(level - tick.bid) >= min_stop_distance and abs(level - tick.ask) >= min_stop_distance:
            valid_levels.append(level)
        else:
            print(f"Invalid stop level {level:.2f}: below minimum stop distance.")
    return valid_levels


def calculate_sl_levels(current_price, stop_levels, symbol_info):
    """
    Calculate SL levels in pips based on the stop levels and current price.

    :param current_price: Current price of the symbol.
    :param stop_levels: List of stop levels in price points.
    :param symbol_info: MetaTrader 5 symbol information.
    :return: List of SL levels in pips.
    """
    point = symbol_info.point
    sl_levels = [round(abs(current_price - level) / point, 2) for level in stop_levels]
    return sl_levels


def cancel_stop_orders(pending_orders, magic_number):
    """
    Cancel all STOP orders with a specific magic number.

    :param pending_orders: List of pending orders.
    :param magic_number: Magic number to identify STOP orders to cancel.
    """
    for order in pending_orders:
        if order.magic == magic_number:
            print(f"Canceling STOP order at price {order.price} with magic number {magic_number}...")

            # Prepare cancel request
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order.ticket,
                "magic": magic_number,
                "symbol": order.symbol,
                "comment": "Cancel STOP order via script",
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to cancel STOP order {order.ticket}: {result.retcode}")
            else:
                print(f"Successfully canceled STOP order {order.ticket}")


def start_order_monitoring(symbol, magic_number_buy, magic_number_sell, check_interval=1):
    """
    Start a threaded monitoring process for stop-out events.

    :param symbol: Trading symbol (e.g., "XAUUSD").
    :param magic_number_buy: Magic number for BUY orders.
    :param magic_number_sell: Magic number for SELL orders.
    :param check_interval: Time interval (in seconds) to check orders.
    """

    def monitor_orders():
        print("Monitoring orders for stop-out events (threaded)...")
        while True:
            # Fetch all open positions and pending orders
            positions = mt5.positions_get(symbol=symbol)
            pending_orders = mt5.orders_get(symbol=symbol)

            if positions is None or pending_orders is None:
                print("Failed to fetch positions or pending orders.")
                break

            # Group positions by magic number
            active_magic_numbers = {pos.magic for pos in positions}

            # Check for missing market orders
            if magic_number_buy not in active_magic_numbers:
                print(
                    f"Market BUY order with magic number {magic_number_buy} is no longer active. Canceling related STOP orders...")
                cancel_stop_orders(pending_orders, magic_number_buy)

            if magic_number_sell not in active_magic_numbers:
                print(
                    f"Market SELL order with magic number {magic_number_sell} is no longer active. Canceling related STOP orders...")
                cancel_stop_orders(pending_orders, magic_number_sell)

            # Wait before next check
            time.sleep(check_interval)

    # Start monitoring in a separate thread
    monitoring_thread = threading.Thread(target=monitor_orders, daemon=True)
    monitoring_thread.start()
    print("Order monitoring started in a background thread.")


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

        # Retrieve current prices and symbol info
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")
        current_price_buy = tick.ask
        current_price_sell = tick.bid

        # Hämta aktuellt pris
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")
        current_price = tick.ask  # Antag BUY-riktning för initiala beräkningar

        # Beräkna TP-nivåer för BUY och SELL
        buy_tp_price = current_price + (number_of_pips * symbol_info.point)
        sell_tp_price = current_price - (number_of_pips * symbol_info.point)

        # Validering av nivåer
        stop_levels_buy = calculate_stop_levels(symbol, "BUY", [top_up_levels1, top_up_levels2, top_up_levels3],
                                                number_of_pips)
        stop_levels_sell = calculate_stop_levels(symbol, "SELL", [top_up_levels1, top_up_levels2, top_up_levels3],
                                                 number_of_pips)

        # Logga validerade nivåer
        print(f"Validated BUY Stop Levels: {stop_levels_buy}")
        print(f"Validated SELL Stop Levels: {stop_levels_sell}")

        # Beräkna SL-nivåer i pips
        sl_levels_buy = [(level - tick.ask) / symbol_info.point for level in stop_levels_buy]
        sl_levels_sell = [(tick.bid - level) / symbol_info.point for level in stop_levels_sell]

        print(f"SL Levels in pips for BUY: {[round(level, 2) for level in sl_levels_buy]}")
        print(f"SL Levels in pips for SELL: {[round(level, 2) for level in sl_levels_sell]}")

        # Utskrift
        print("\n--- BUY Orders ---")
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
            direction="BUY",
            sl_levels=sl_levels_buy,
            symbol=symbol  # Lägg till symbol här
        )

        print("\n--- SELL Orders ---")
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
            direction="SELL",
            sl_levels=sl_levels_sell,
            symbol=symbol  # Lägg till symbol här
        )

        # Confirm before placing orders
        confirm = input("\nDo you want to proceed with placing the orders? (Y/N): ").strip().upper()
        if confirm == "Y":
            print("Proceeding to place orders...")

            # Place initial market orders
            place_market_order(symbol, "BUY", lot_sizes[0], number_of_pips, initial_stop_level, 1001)
            place_market_order(symbol, "SELL", lot_sizes[0], number_of_pips, initial_stop_level, 1002)

            place_stop_orders(symbol, "BUY", lot_sizes[1:], buy_tp_price, stop_levels_buy, be_levels, 1001)
            place_stop_orders(symbol, "SELL", lot_sizes[1:], sell_tp_price, stop_levels_sell, be_levels, 1002)

            start_order_monitoring(symbol, magic_number_buy=1001, magic_number_sell=1002)

            print("All orders have been placed successfully.")
        else:
            print("Order placement canceled by user.")

    finally:
        pass


if __name__ == "__main__":
    main()
