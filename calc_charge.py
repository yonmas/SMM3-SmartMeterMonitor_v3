class CalcCharge:

    def __init__(self,
                 base,    # 基本料金
                 rate1,   # 1段料金
                 rate2,   # 2段料金
                 rate3,   # 3段料金
                 saiene,  # 再エネ発電賦課金単価
                 nencho   # 燃料費調整単価
                 ):

        self.base = base
        self.rate1 = rate1
        self.rate2 = rate2
        self.rate3 = rate3
        self.saiene = saiene
        self.nencho = nencho

    def tepco(self, contract, power):
        """
        東京電力での電気料金計算（従量電灯B）
        2023.6.1 料金改定版

    基本料金                    base
        10A :   295.24円
        15A :   442.86円
        20A :   590.48円
        30A :   885.72円
        40A : 1,180.96円
        50A : 1,476.20円
        60A : 1,771.44円

        従量料金
        〜120lWh : 30.00円/kWh  rate1
        〜300kWh : 36.60円/kwh  rate2
        〜       : 40.69円/kwh  rate3

        燃料費調整単価（毎月更新）
        -11.21円/kWh            nencho

        再エネ発電賦課金（〜2024.4）
        1.40円/kWh              saiene

        電気料金（税込） = int(基本料金 + 従量料金 + 燃料費調整額) + int(再エネ発電賦課金)

        Parameters
        ----------
        contract : int（未使用）
            契約アンペア数
        power : float
            前回検針後の使用電力量（kWh）

        Returns
        -------
        fee: int
            電気料金
        """

        power = int(power)

        fee = self.base

        if power <= 120:
            fee += self.rate1 * power
        elif power <= 300:
            fee += self.rate1 * 120
            fee += self.rate2 * (power - 120)
        else:
            fee += self.rate1 * 120
            fee += self.rate2 * 180
            fee += self.rate3 * (power - 120 - 180)

        # 燃料費調整額・再エネ発電賦課金 加算
        fee += self.nencho * power + int(self.saiene * power)

        return int(fee)
