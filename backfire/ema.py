import pandas as pd
import ema_logic
import numpy as np
from datetime import datetime
from datetime import timedelta

class AccountBalances:
    usd = 0
    btc = 0
    def sub_btc(self, btc_amt):
        self.btc -= btc_amt
    def sub_usd(self, usd_amt):
        self.usd -= usd_amt
    def add_btc(self, btc_amt):
        self.btc += btc_amt
    def add_usd(self, usd_amt):
        self.usd += usd_amt
    def set_usd(self, new_bal):
        self.usd = new_bal
    def set_btc(self, new_bal):
        self.btc = new_bal

class BacktestSettings:
    upper_window = 0
    def set_upper_window(self, val):
        self.upper_window = val
    lower_window = 0
    def set_lower_window(self, val):
        self.lower_window = val
    factor_high = 0
    def set_factor_high(self, val):
        self.factor_high = val
    factor_low = 0
    def set_factor_low(self, val):
        self.factor_low = val
    buy_pct_usd = 0
    def set_buy_pct_usd(self, val):
        self.buy_pct_usd = val
    sell_pct_btc = 0
    def set_sell_pct_btc(self, val):
        self.sell_pct_btc = val
    principle_btc = 0
    def set_principle_btc(self, val):
        self.principle_btc = val
    principle_usd = 0
    def set_principle_usd(self, val):
        self.principle_usd = val
    min_usd = 0
    def set_min_usd(self, val):
        self.min_usd = val
    min_btc = 0
    def set_min_btc(self, val):
        self.min_btc = val
    start_date = 0
    def set_start_date(self, val):
        self.start_date = val
    end_date = 0
    def set_end_date(self, val):
        self.end_date = val


def run_backtest(df, desired_outputs, bt):
    bal = AccountBalances()
    bal.set_usd(bt.principle_usd)
    fills = []
    for row in list(zip(df['timestamp'], df['close'], df['buy_signal'], df['sell_signal'])):
        price = row[1]
        if row[2] == 1 and (bal.usd * bt.buy_pct_usd) > bt.min_usd:
            value_usd = bal.usd * bt.buy_pct_usd
            value_btc = value_usd / price
            value_btc = value_btc - (value_btc * .001)
            bal.add_btc(value_btc)
            bal.sub_usd(value_usd)
            fills.append(create_fill(row[0], 'buy', price, value_btc, value_usd))
        if row[3] == 1 and (bal.btc * bt.sell_pct_btc) > bt.min_btc:
            value_btc = bal.btc * bt.sell_pct_btc
            value_usd = price * value_btc
            value_usd = value_usd - (value_usd * .001)
            bal.add_usd(value_usd)
            bal.sub_btc(value_btc)
            fills.append(create_fill(row[0], 'sell', price, value_btc, value_usd))
    num_fills = len(fills)
    result = {
            "n_fills": num_fills,
            "upper_window": bt.upper_window, 
            "lower_window": bt.lower_window,
            "upper_factor": bt.factor_high, 
            "lower_factor": bt.factor_low,
            "buy_pct_usd": bt.buy_pct_usd,
            "sell_pct_btc": bt.sell_pct_btc, 
            "usd_bal": bal.usd, 
            "btc_bal": bal.btc
            }
    if desired_outputs == "both":
        fills = pd.DataFrame(fills)
        return result, fills
    else:
        return result


def create_fill(my_time, my_side, btc_price, btc_val, usd_val):
    result = {}
    result['timestamp'] = my_time
    result['side'] = my_side
    result['price'] = btc_price
    result['btc_val'] = btc_val
    result['usd_val'] = usd_val
    return(result)

# returns a time in the past with correct offset so the ema line can calculate correctly before our
# actual backtestin start date.
# the formula is: start_time - (base_length * ema_period_lenght) as minutes
# we should probably do a check here somewhere in the future to prevent times in the past which
# are beyond our available data set.
def get_start_time_for_ema(ema_length, start_time):
	# base multiplier for our ema length
	base_length = 100 
	
	# start date is offset into the past by the ema length * base length
	new_start = datetime.strptime(start_time, "%Y-%m-%d") - pd.DateOffset(minutes=(ema_length * base_length))

	# return the new date as a str
	return str(new_start)


def prep_data(raw_data, start_time, end_time):
    #raw_data = pd.read_csv('~/coinbase_data.csv')
    raw_data['timestamp'] = pd.to_datetime(raw_data.timestamp)
    trimmed_df = raw_data[raw_data.timestamp >= start_time]
    trimmed_df = trimmed_df[trimmed_df.timestamp <= end_time]
    trimmed_df = trimmed_df.reset_index(drop = True)
    day_df = trimmed_df.groupby(trimmed_df['timestamp'].dt.date).agg({'open':'first',  'high': max, 'low': min, 'close':'last',}).reset_index()
    return(day_df, trimmed_df)


def single_backtest(df, bt):
    final_close = df.tail(2)[0:1]['close'].values[0]
    hodl_usd = (bt.principle_usd / df[0:1]['close'].values[0]) * final_close
    hodl_roi = (hodl_usd - bt.principle_usd) / bt.principle_usd

    df = ema_logic.set_signals(df, bt)
    # trim results and ignore fills below on our start date:
    df = df[pd.to_datetime(df.timestamp) >= pd.to_datetime(bt.start_date)] 
    results, my_fills = run_backtest(df, 'both', bt)
    my_fills = fills_running_bal(my_fills, bt)
    results['hodl_roi'] = hodl_roi
    results['sd'] = bt.start_date# df.timestamp.min()
    results['ed'] = bt.end_date # df.timestamp.max()
    results['final_bal'] = results['usd_bal'] + (final_close * results['btc_bal'])
    results['roi'] = (results['final_bal'] - bt.principle_usd) / bt.principle_usd
    return(df, results, my_fills)

def run_multi(df, my_result_type, bt, my_data):
    bt.set_upper_window(my_data[0])
    bt.set_lower_window(my_data[1])
    bt.set_factor_high(my_data[2])
    bt.set_factor_low(my_data[3])
    bt.set_buy_pct_usd(my_data[4])
    bt.set_sell_pct_btc(my_data[5])

    df = ema_logic.set_signals(df, bt)
    # trim results and ignore fills below on our start date:
    df = df[pd.to_datetime(df.timestamp) >= pd.to_datetime(bt.start_date)] 
    df = df[(df['sell_signal']==1) | (df['buy_signal'] == 1)]
    result = run_backtest(df, my_result_type, bt)
    return(result)

def fills_running_bal(fills_df, bt):
    if len(fills_df) > 0:
        fills_df['p_usd'] = bt.principle_usd
        fills_df['p_btc'] = bt.principle_btc
        fills_df['btc_val'] = np.where(fills_df['side'] == 'sell', fills_df['btc_val'] * -1, fills_df['btc_val'])
        fills_df['usd_val'] = np.where(fills_df['side'] == 'buy', fills_df['usd_val'] * -1, fills_df['usd_val'])
        fills_df['bal_btc'] = fills_df.btc_val.cumsum() + bt.principle_btc
        fills_df['bal_usd'] = fills_df.usd_val.cumsum() + bt.principle_usd
        fills_df['running_bal'] = (fills_df['bal_btc'] * fills_df['price']) + fills_df['bal_usd']
    else:
        print("WARNING: Fills DataFrame is empty")
    return(fills_df)

