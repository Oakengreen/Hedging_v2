import MetaTrader5 as mt5
import pandas as pd

def get_pip_value(symbol):
    """
    Hämtar pipvärdet för en given symbol.
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info:
        return symbol_info.trade_tick_value
    return None

def calculate_gain_in_dollars(lot_size, pip_gain, pip_value):
    """
    Beräknar vinsten i dollar för en given order.

    :param lot_size: Lotstorlek.
    :param pip_gain: Pip-vinsten för ordern.
    :param pip_value: Pipvärdet i kontovaluta.
    :return: Vinsten i dollar.
    """
    return lot_size * pip_gain * pip_value

def calculate_trade_parameters(symbol, account_size, target_gain_percent, number_of_pips,
                               initial_stop_percent, initial_stop_level,
                               top_up_levels1, top_up_levels2, top_up_levels3):
    """
    Beräknar tradingparametrar såsom TP, SL och lotstorlekar.
    """
    point = mt5.symbol_info(symbol).point
    pip_value = get_pip_value(symbol)
    current_price = mt5.symbol_info_tick(symbol).ask
    points_per_pip_value = number_of_pips / 10 if mt5.symbol_info(symbol).digits == 5 else number_of_pips

    spread_in_pips = (mt5.symbol_info_tick(symbol).ask - mt5.symbol_info_tick(symbol).bid) / point / 10

    # Total Gain Target
    total_gain = (account_size * target_gain_percent) / 100

    # TP-nivåer
    buy_tp = current_price + number_of_pips * point * points_per_pip_value
    sell_tp = current_price - number_of_pips * point * points_per_pip_value

    # Adjust pips based on digits
    number_of_pips_adjusted = number_of_pips / 10 if mt5.symbol_info(symbol).digits == 5 else number_of_pips
    initial_stop_level_adjusted = initial_stop_level / 10 if mt5.symbol_info(symbol).digits == 5 else initial_stop_level

    # Beräkna initial lot size
    loss_in_dollars = (initial_stop_percent / 100) * account_size
    initial_lot_size = round(loss_in_dollars / (initial_stop_level_adjusted * pip_value), 2)

    # STOP-nivåer baserat på top_up_levels
    stop_levels_buy = [
        current_price + (buy_tp - current_price) * (top_up_levels1 / 100),
        current_price + (buy_tp - current_price) * (top_up_levels2 / 100),
        current_price + (buy_tp - current_price) * (top_up_levels3 / 100),
    ]
    stop_levels_sell = [
        current_price - (current_price - sell_tp) * (top_up_levels1 / 100),
        current_price - (current_price - sell_tp) * (top_up_levels2 / 100),
        current_price - (current_price - sell_tp) * (top_up_levels3 / 100),
    ]

    # Pip gains
    pip_gains = {
        'initial': number_of_pips_adjusted - spread_in_pips,
        'stop_1': number_of_pips_adjusted * (1 - top_up_levels1 / 100) - spread_in_pips,
        'stop_2': number_of_pips_adjusted * (1 - top_up_levels2 / 100) - spread_in_pips,
        'stop_3': number_of_pips_adjusted * (1 - top_up_levels3 / 100) - spread_in_pips,
    }

    # Lot storlekar
    gain_in_dollars_initial = calculate_gain_in_dollars(initial_lot_size, pip_gains['initial'], pip_value)
    gain_in_dollars_stop_1 = ((total_gain - gain_in_dollars_initial) * top_up_levels1) / (
                top_up_levels1 + top_up_levels2 + top_up_levels3)
    gain_in_dollars_stop_2 = ((total_gain - gain_in_dollars_initial) * top_up_levels2) / (
                top_up_levels1 + top_up_levels2 + top_up_levels3)
    gain_in_dollars_stop_3 = ((total_gain - gain_in_dollars_initial) * top_up_levels3) / (
                top_up_levels1 + top_up_levels2 + top_up_levels3)

    lots_stop_1 = gain_in_dollars_stop_1 / (pip_gains['stop_1'] * pip_value)
    lots_stop_2 = gain_in_dollars_stop_2 / (pip_gains['stop_2'] * pip_value)
    lots_stop_3 = gain_in_dollars_stop_3 / (pip_gains['stop_3'] * pip_value)

    return {
        "pip_value": pip_value,
        "spread_in_pips": spread_in_pips,
        "initial_lot_size": initial_lot_size,
        "lots": (lots_stop_1, lots_stop_2, lots_stop_3),
        "pip_gains": pip_gains,
        "current_price": current_price,
        "buy_tp": buy_tp,
        "sell_tp": sell_tp,
        "total_gain": total_gain,
        "stop_levels_buy": stop_levels_buy,
        "stop_levels_sell": stop_levels_sell
    }

def prepare_orders(symbol, params):
    """
    Förbereder alla data som krävs för att skicka ordrar.

    :param symbol: Handelsymbol (t.ex. EURUSD).
    :param params: Dictionary med beräknade tradingparametrar.
    :return: Lista med ordrar att skickas.
    """
    current_price = params["current_price"]
    initial_lot_size = params["initial_lot_size"]
    lots_stop_1, lots_stop_2, lots_stop_3 = params["lots"]
    buy_tp = params["buy_tp"]
    sell_tp = params["sell_tp"]

    orders = []

    # Lägg BUY marknadsorder
    orders.append({
        "symbol": symbol,
        "type": "BUY",
        "price": current_price,
        "lot_size": initial_lot_size,
        "tp": buy_tp
    })

    # Lägg SELL marknadsorder
    orders.append({
        "symbol": symbol,
        "type": "SELL",
        "price": current_price,
        "lot_size": initial_lot_size,
        "tp": sell_tp
    })

    # Lägg BUY STOP-ordrar
    for i, lot_size in enumerate([lots_stop_1, lots_stop_2, lots_stop_3]):
        orders.append({
            "symbol": symbol,
            "type": "BUY_STOP",
            "price": params["stop_levels_buy"][i],
            "lot_size": lot_size,
            "tp": buy_tp
        })

    # Lägg SELL STOP-ordrar
    for i, lot_size in enumerate([lots_stop_1, lots_stop_2, lots_stop_3]):
        orders.append({
            "symbol": symbol,
            "type": "SELL_STOP",
            "price": params["stop_levels_sell"][i],
            "lot_size": lot_size,
            "tp": sell_tp
        })

    return orders
