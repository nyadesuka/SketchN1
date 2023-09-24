import pandas as pd
import time
import ta
from datetime import timedelta
from binance.client import Client
import Api
from decimal import Decimal, ROUND_DOWN
class TradingBot:
    def __init__(self, api_key, secret_key, symbol, investment):
        self.client = Client(api_key, secret_key)
        self.symbol = symbol
        self.investment = investment
        self.pos_dict = {'in_position': False}
        self.min_price, self.max_price, self.tick_size = self.get_price_info()

    def get_price_info(self):
        # Fetch symbol information
        symbol_info = self.client.get_symbol_info(self.symbol)

        # Find the PRICE_FILTER filter
        price_filter = next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', symbol_info['filters']), None)
        if price_filter:
            min_price = float(price_filter['minPrice'])
            max_price = float(price_filter['maxPrice'])
            tick_size = float(price_filter['tickSize'])
            return min_price, max_price, tick_size
        else:
            raise ValueError("PRICE_FILTER not found in symbol info")

    def get_data(self):
        frame = pd.DataFrame(self.client.get_historical_klines(self.symbol, '15m', '3000 minutes UTC'))
        frame = frame.iloc[:, 0:5]
        frame.columns = ['Time', 'Open', 'High', 'Low', 'Close']
        frame.set_index('Time', inplace=True)
        frame.index = pd.to_datetime(frame.index, unit='ms')
        frame = frame.astype(float)
        return frame

    def calculate_indicators(self, df):
        df['SMA_50'] = ta.trend.sma_indicator(df.Close, window=50)
        df['stochrsi_k'] = ta.momentum.stochrsi_k(df.Close, window=10)
        df.dropna(inplace=True)
        df['Buy'] = (df.Close > df.SMA_50) & (df.stochrsi_k < 0.25) & (df.stochrsi_k > 0.15)
        return df

    def get_price(self):
        raw_price = float(self.client.get_symbol_ticker(symbol=self.symbol)['price'])
        rounded_price = round(raw_price, self.tick_size_precision())  # Round to tick size precision
        formatted_price = '{:.8f}'.format(rounded_price)
        reduced_price = float(formatted_price)
        return reduced_price

    def tick_size_precision(self):
        return int(-Decimal(str(self.tick_size)).as_tuple().exponent)


    def calculate_quantity(self):
        info = self.client.get_symbol_info(symbol=self.symbol)
        lot_filter = [i for i in info['filters'] if i['filterType'] == 'LOT_SIZE']
        if not lot_filter:
            raise ValueError("LOT_SIZE filter not found in symbol info")
        lot_size = float(lot_filter[0]['stepSize'])  # Use stepSize to determine precision
        max_qty = float(lot_filter[0]['maxQty'])
        price = self.get_price()
        calculated_qty = self.investment / price  # Now division should work as price is numeric
        qty = max(min(calculated_qty, max_qty), lot_size)
        qty = round(qty / lot_size) * lot_size
        return qty

    @staticmethod
    def right_rounding(lot_size):
        splitted = str(lot_size).split('.')
        if len(splitted) == 1:
            return 0
        elif float(splitted[0]) == 1:
            return 0
        else:
            return len(splitted[1])

    def buy(self):
        order = self.client.order_limit_buy(symbol=self.symbol,
                                            price=self.get_price(),
                                            quantity=self.calculate_quantity())
        print(order)
        self.pos_dict['in_position'] = True
        return order

    def sell(self, qty):
        order = self.client.create_order(symbol=self.symbol,
                                         side='SELL',
                                         type="MARKET",
                                         quantity=qty)
        print(order)
        self.pos_dict['in_position'] = False

    def check_buy(self):
        if not self.pos_dict["in_position"]:
            if self.df['Buy'].values.any():
                return True
        return False

    def check_sell(self, order):
        order_status = self.client.get_order(symbol=self.symbol, orderId=order['orderId'])
        if self.pos_dict['in_position']:
            if order_status['status'] == 'NEW':
                print('pending')
            elif order_status['status'] == 'FILLED':
                cond1 = self.df.Close.values > float(order_status['price'])
                cond2 = pd.to_datetime('now') >= pd.to_datetime(
                    order_status['updateTime'], unit='ms') + timedelta(minutes=150)
                if cond2 or cond1:
                    self.sell(order_status['origQty'])

    def run(self):
        while True:
            self.df = self.calculate_indicators(self.get_data())
            if self.check_buy():
                curr_order = self.buy()
            try:
                self.check_sell(curr_order)
            except:
                print('skip')
            time.sleep(25)

if __name__ == "__main__":
    api_key = Api.Api_key
    secret_key = Api.Secret_key
    symbol = "ETHUSDT"
    investment = 30

    trading_bot = TradingBot(api_key, secret_key, symbol, investment)
    trading_bot.run()
