import MetaTrader5 as mt5
from settings import (
    account_size,
    target_gain_percent,
    number_of_pips,
    initial_stop_level,
    magic_number_buy,
    magic_number_sell,
    symbol,
    top_up_levels1,
    top_up_levels2,
    top_up_levels3,
)


def get_pip_value(symbol):
    """
    Calculate the pip value for a given symbol dynamically from MT5.

    :param symbol: Trading symbol (e.g., "XAUUSD").
    :return: Pip value in account currency.
    """
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Failed to retrieve symbol info for {symbol}.")

    # Contract size (e.g., 100,000 for Forex, 1 for indices, etc.)
    contract_size = symbol_info.trade_contract_size

    # Point size (e.g., 0.0001 for EURUSD, 0.01 for XAUUSD)
    point = symbol_info.point

    # Tick value (value of a 1-point price movement)
    tick_value = contract_size * point

    # Pip value is based on tick value
    return tick_value

def place_stop_orders(symbol, action, lot_size, tp_price, stop_levels, magic_number):
    """
    Places additional stop orders (BUY STOP / SELL STOP) with shared TP.
    """
    for level in stop_levels:
        # Order type
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
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to place {action} STOP order at level {level}: {result.retcode}")
        else:
            print(f"{action} STOP order placed successfully at level {level}: {result}")

def place_market_order(symbol, action, lot_size, tp_distance, sl_distance, magic_number):
    """
    Places a market order (BUY/SELL) with TP and SL distances in pips.
    """
    # Ensure symbol is available
    if not mt5.symbol_select(symbol, True):
        print(f"Failed to select symbol {symbol}.")
        return None

    # Get current prices
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"Failed to retrieve tick data for {symbol}.")
        return None

    price = tick.ask if action == "BUY" else tick.bid
    point = mt5.symbol_info(symbol).point

    # Calculate TP and SL prices
    tp_price = price + (tp_distance * point) if action == "BUY" else price - (tp_distance * point)
    sl_price = price - (sl_distance * point) if action == "BUY" else price + (sl_distance * point)

    # Prepare the request
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

    # Send the request
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to place {action} order: {result.retcode}")
        return None

    print(f"{action} order placed successfully: {result}")
    return result

def calculate_lot_size_per_order(account_size, target_gain_percent, tp_distance, pip_value, num_orders):
    """
    Calculate the lot size per order to achieve the target gain percentage.
    """
    # Calculate the target gain in dollars
    target_gain_dollars = account_size * (target_gain_percent / 100)

    # Calculate the lot size per order
    lot_size = round(target_gain_dollars / (num_orders * tp_distance * pip_value), 2)
    return lot_size

def calculate_stop_levels(tp_distance, top_up_levels):
    """
    Calculate stop levels based on TP distance and percentage levels.
    """
    return [tp_distance * (level / 100) for level in top_up_levels]

def get_spread(symbol):
    """
    Calculate the spread for the given symbol.
    """
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")
    return tick.ask - tick.bid

def calculate_correct_lot_size(account_size, target_gain_percent, tp_distances, pip_value):
    """
    Calculate the correct lot size to meet the target gain based on distances to TP.

    :param account_size: Account size in dollars.
    :param target_gain_percent: Target gain as a percentage of account size.
    :param tp_distances: List of distances to TP for all orders.
    :param pip_value: Value of one pip for the symbol.
    :return: Correct lot size.
    """
    total_goal = account_size * (target_gain_percent / 100)

    # Sum up the total pips from all orders
    total_pips = sum(tp_distances)

    # Calculate the lot size
    lot_size = round(total_goal / (total_pips * pip_value), 2)
    return lot_size

def calculate_order_profits(lot_size, tp_distance, pip_value):
    """
    Calculate the profit contribution of an order in dollars.
    """
    return lot_size * tp_distance * pip_value

def calculate_and_confirm_orders(account_size, target_gain_percent, lot_size, tp_distance, pip_value, num_orders):
    """
    Calculate total goal and individual contributions for BUY and SELL orders,
    and confirm before placing orders.
    """
    # Calculate total goal
    goal = account_size * (target_gain_percent / 100)

    # Calculate individual contributions
    order_profit = calculate_order_profits(lot_size, tp_distance, pip_value)
    total_profit = order_profit * num_orders

    # Print calculations for review
    print("\n--- Profit Calculation ---")
    print(f"Total Goal (BUY/SELL): ${goal:.2f}")
    print(f"Profit per Order: ${order_profit:.2f}")
    print(f"Total Profit from {num_orders} Orders: ${total_profit:.2f}")

    # Confirm before placing orders
    confirm = input("\nDo you want to proceed with placing the orders? (Y/N): ").strip().upper()
    return confirm == "Y"

def calculate_order_contributions(lot_size, tp_price, stop_levels, current_price, pip_value):
    """
    Calculate the profit contributions of all orders based on their distance to TP.

    :param lot_size: Lot size for all orders.
    :param tp_price: Take Profit price.
    :param stop_levels: List of stop order prices.
    :param current_price: Current price (entry price of the market order).
    :param pip_value: Value of one pip for the symbol.
    :return: List of contributions for each order and the total contribution.
    """
    contributions = []

    # Market order contribution
    market_order_distance = abs(tp_price - current_price)
    market_order_pips = market_order_distance / mt5.symbol_info(symbol).point
    contributions.append(round(lot_size * market_order_pips * pip_value, 2))

    # Stop orders contributions
    for stop_level in stop_levels:
        stop_order_distance = abs(tp_price - stop_level)
        stop_order_pips = stop_order_distance / mt5.symbol_info(symbol).point
        contributions.append(round(lot_size * stop_order_pips * pip_value, 2))

    total_contribution = sum(contributions)
    return contributions, total_contribution

def calculate_lot_size_to_reach_target(account_size, target_gain_percent, tp_distance, pip_value, num_orders):
    """
    Calculate the lot size per order to achieve the target gain if all orders reach TP.

    :param account_size: Account size in dollars.
    :param target_gain_percent: Target gain as a percentage of account size.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :param num_orders: Total number of orders in one direction (e.g., BUY or SELL).
    :return: Lot size per order.
    """
    # Calculate total gain in dollars
    total_gain = account_size * (target_gain_percent / 100)

    # Calculate lot size
    lot_size = round(total_gain / (num_orders * tp_distance * pip_value), 2)
    return lot_size

def display_and_confirm_order_profits(account_size, target_gain_percent, lot_size, tp_distance, pip_value, num_orders):
    """
    Display profit contributions for each order and confirm before placing orders.

    :param account_size: Account size in dollars.
    :param target_gain_percent: Target gain as a percentage of account size.
    :param lot_size: Lot size for the orders.
    :param tp_distance: Distance to TP in pips.
    :param pip_value: Value of one pip for the symbol.
    :param num_orders: Total number of orders in one direction.
    :return: Boolean indicating whether to proceed with placing orders.
    """
    # Calculate total goal
    goal = account_size * (target_gain_percent / 100)

    # Calculate contributions and total profit
    contributions, total_profit = calculate_order_contributions(lot_size, tp_distance, pip_value, num_orders)

    # Display profit calculation
    print("\n--- Profit Contributions ---")
    print(f"Total Goal: ${goal:.2f}")
    print(f"Profit per Order: ${contributions[0]:.2f}")
    print(f"Total Profit from {num_orders} Orders: ${total_profit:.2f}")
    print("\nIndividual Contributions:")
    for i, contribution in enumerate(contributions, 1):
        print(f"Order {i}: ${contribution:.2f}")

    # Confirm
    confirm = input("\nDo you want to proceed with placing the orders? (Y/N): ").strip().upper()
    return confirm == "Y"

def print_order_contributions(contributions, lot_sizes, total_contribution, direction):
    """
    Print the contributions and lot sizes for each order in a given direction (BUY/SELL).

    :param contributions: List of contributions in dollars for each order.
    :param lot_sizes: List of lot sizes for each order.
    :param total_contribution: Total contribution in dollars.
    :param direction: Direction (e.g., "BUY" or "SELL").
    """
    print(f"\n{direction} Orders:")
    for i, (contribution, lot_size) in enumerate(zip(contributions, lot_sizes), 1):
        print(f"  Order {i}: ${contribution:.2f} (Lot Size: {lot_size:.2f})")
    print(f"  Total {direction} Contribution: ${total_contribution:.2f}")

def main():
    # Ensure MetaTrader 5 is initialized
    if not mt5.initialize():
        print("MetaTrader 5 initialization failed. Ensure the terminal is running.")
        raise RuntimeError("Failed to initialize MetaTrader 5")

    try:
        # Retrieve pip value dynamically
        pip_value = get_pip_value(symbol)
        print(f"Pip Value for {symbol}: {pip_value}")

        # Calculate total_goal
        total_goal = account_size * (target_gain_percent / 100)
        print(f"Total Goal (Profit Target): ${total_goal:.2f}")

        # Adjust distances for pips
        tp_distance = number_of_pips
        sl_distance = initial_stop_level

        # Total number of orders per direction (market + 3 stop orders)
        num_orders = 4

        # Calculate lot size per order to meet target gain
        lot_size = calculate_lot_size_to_reach_target(
            account_size, target_gain_percent, tp_distance, pip_value, num_orders
        )

        # Define percentage levels from settings
        top_up_levels = [top_up_levels1, top_up_levels2, top_up_levels3]

        # Get current price and spread
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            raise RuntimeError(f"Failed to retrieve tick data for {symbol}.")
        spread = get_spread(symbol)
        current_price = tick.ask  # Assuming we're working with BUY orders first

        # Calculate stop levels
        stop_distances = calculate_stop_levels(tp_distance, top_up_levels)
        stop_levels_buy = [current_price + (distance * mt5.symbol_info(symbol).point) + spread for distance in stop_distances]
        stop_levels_sell = [current_price - (distance * mt5.symbol_info(symbol).point) - spread for distance in stop_distances]

        # Calculate contributions for BUY and SELL
        buy_tp_price = current_price + (tp_distance * mt5.symbol_info(symbol).point)
        buy_contributions, buy_total = calculate_order_contributions(
            lot_size, buy_tp_price, stop_levels_buy, current_price, pip_value
        )

        sell_tp_price = current_price - (tp_distance * mt5.symbol_info(symbol).point)
        sell_contributions, sell_total = calculate_order_contributions(
            lot_size, sell_tp_price, stop_levels_sell, current_price, pip_value
        )

        # Print contributions and lot sizes
        lot_sizes_buy = [lot_size for _ in range(num_orders)]  # Example: constant lot size
        lot_sizes_sell = [lot_size for _ in range(num_orders)]  # Example: constant lot size

        print_order_contributions(buy_contributions, lot_sizes_buy, buy_total, "BUY")
        print_order_contributions(sell_contributions, lot_sizes_sell, sell_total, "SELL")

        # Confirm before placing orders
        confirm = input("\nDo you want to proceed with placing the orders? (Y/N): ").strip().upper()
        if confirm != "Y":
            print("Order placement canceled by user.")
            return

        # Place initial BUY and SELL orders
        buy_order = place_market_order(symbol, "BUY", lot_size, tp_distance, sl_distance, magic_number_buy)
        sell_order = place_market_order(symbol, "SELL", lot_size, tp_distance, sl_distance, magic_number_sell)

        if not buy_order or not sell_order:
            print("Failed to place initial orders. Stopping script.")
            return

        # Place stop orders
        place_stop_orders(symbol, "BUY", lot_size, buy_tp_price, stop_levels_buy, magic_number_buy)
        place_stop_orders(symbol, "SELL", lot_size, sell_tp_price, stop_levels_sell, magic_number_sell)

    finally:
        # Keep MT5 connection open
        pass

# Execute the script
if __name__ == "__main__":
    main()
