class CalcCharge:

    """
    電気料金計算計算関数
    
    東京電力:
        tepco                   従量電灯B
        tepco_smartlife_s       スマートライフS
    
    中部電力: ※祝祭日料金には対応していません。

        chubu_smartlife         スマートライフプラン（スタンダード）
        chubu_smartlife_asa     スマートライフプラン（朝とく）
        chubu_smartlife_yoru    スマートライフプラン（夜とく）

    """


    def __init__(self,
                 base,    # 基本料金
                 rate1,   # 1段料金 / 昼間：午前6時〜翌午前1時
                 rate2,   # 2段料金 / 夜間：午前1時〜午前6時
                 rate3,   # 3段料金 / 未使用
                 nencho,  # 燃料費調整単価
                 saiene,  # 再エネ発電賦課金単価
                 start    # 集計に当日を算入するか否か : 当日を含む集計 = 0,　前日までの集計 = 1
                 ):

        self.base = base
        self.rate1 = rate1
        self.rate2 = rate2
        self.rate3 = rate3
        self.nencho = nencho
        self.saiene = saiene
        self.start = start


    def tepco(self, contract, hourly_power, day, UNIT):
        """
        東京電力: 従量電灯B
        2024.4.1 料金改定版

        基本料金                 base
        10A :   311.75円
        15A :   467.63円
        20A :   623.50円
        30A :   935.25円
        40A : 1,247.00円
        50A : 1,558.75円
        60A : 1,870.50円

        従量料金
        〜120lWh : 29.80円/kWh  rate1
        〜300kWh : 36.40円/kwh  rate2
        〜       : 40.49円/kwh  rate3

        燃料費調整単価（毎月更新）
        -9.21円/kWh             nencho

        再エネ発電賦課金（〜2025.4）
        3.49円/kWh              saiene

        電気料金（税込） = int(基本料金 + 従量料金 + 燃料費調整額) + int(再エネ発電賦課金)

        Parameters
        ----------
        contract : int（未使用）
            契約アンペア数
        hourly_power : float
            料金計算期間の1時間ごとの使用電力量（kWh）: リスト
        day : int
            曜日番号 （0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日）

        Returns
        -------
        fee: int
            電気料金
        """

        power = 0
        for days_ago in range(self.start, len(hourly_power)):
            power += sum(hourly_power[days_ago])
        power = int(power * UNIT)

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

        return int(fee), int(power)


    def tepco_smartlife_s(self, contract, hourly_power, day, UNIT):
        """
        東京電力: スマートライフS
        2024.4.1 料金改定版

        基本料金                 base
        10A あたりの単価 : 311.75円

        従量料金
        昼間:午前6時〜翌午前1時 : 35.76円/kWh  rate1
        夜間:午前1時〜午前6時   : 27.86円/kwh  rate2

        燃料費調整単価（毎月更新）
        -9.21円/kWh             nencho

        再エネ発電賦課金（〜2025.4）
        3.49円/kWh              saiene

        電気料金（税込） = int(基本料金 + 従量料金 + 燃料費調整額) + int(再エネ発電賦課金)

        Parameters
        ----------
        contract : int
            契約アンペア数
        hourly_power : float
            料金計算期間の1時間ごとの使用電力量（kWh）: リスト
        day : int
            曜日番号 （0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日）

        Returns
        -------
        fee: int
            電気料金
        """

        # 集計時間帯の指定
        range1 = range(0, 1)   # 時間帯1: 0時 〜  1時 / rate1
        range2 = range(1, 6)   # 時間帯2: 1時 〜  6時 / rate2
        range3 = range(6, 24)  # 時間帯3: 6時 〜 24時 / rate1
        
        # 時間帯ごとの使用電力量の集計
        power1 = 0
        power2 = 0
        power3 = 0
        
        for days_ago in range(self.start, len(hourly_power)):
            power1 += sum(hourly_power[days_ago][i] for i in range1) * UNIT
            power2 += sum(hourly_power[days_ago][i] for i in range2) * UNIT
            power3 += sum(hourly_power[days_ago][i] for i in range3) * UNIT

        # 合計使用電力量
        power = power1 + power2 + power3

        # 料金計算
        fee = self.base * (contract / 10)  # 契約電力10Aごと
        fee += (power1 + power3) * self.rate1 + power2 * self.rate2
        
        # 燃料費調整額・再エネ発電賦課金 加算
        fee += self.nencho * power + int(self.saiene * power)

        return int(fee), int(power)


    def chubu_smartlife(self, contract, hourly_power, day, UNIT):
        """
        中部電力: スマートライフプラン（スタンダード）
        2024.4.1 料金改定版
        ※祝祭日料金には対応していません。

        基本料金                base
        10kVAまで   : 1,838.44円
        10kVA超過分 :   321.14円/1kVA

        従量料金
        デイタイム : 10時〜17時 : 38.80円/kWh  rate1 (土日はrate2)
        @ホームタイム : 8時〜10時、17時〜22時 : 28.61円/kwh  rate2
        ナイトタイム : 22時〜翌8時 : 16.52円/kWh  rate3

        燃料費調整単価（2024.5/毎月更新）
        0.04円/kWh             nencho

        再エネ発電賦課金（〜2025.4）
        3.49円/kWh              saiene

        電気料金（税込） = int(基本料金 + 従量料金 + 燃料費調整額) + int(再エネ発電賦課金)

        Parameters
        ----------
        contract : int
            契約アンペア数
        hourly_power : float
            料金計算期間の1時間ごとの使用電力量（kWh）: リスト
        day : int
            曜日番号 （0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日）

        Returns
        -------
        fee: int
            電気料金
        """

        # 集計時間帯の指定 : スマートライフプラン（スタンダード）
        range1 = range(0, 8)    # 時間帯1:  0時 〜  8時 / rate3
        range2 = range(8, 10)   # 時間帯2:  8時 〜 10時 / rate2
        range3 = range(10, 17)  # 時間帯3: 10時 〜 17時 / rate1 (土日は rate2)
        range4 = range(17, 22)  # 時間帯3: 17時 〜 22時 / rate2
        range5 = range(22, 24)  # 時間帯3: 22時 〜 24時 / rate3
        
        # 時間帯ごとの使用電力量の集計
        power1 = 0
        power2 = 0
        power3_weekday = 0
        power3_weekend = 0
        power4 = 0
        power5 = 0

        for days_ago in range(self.start, len(hourly_power)):
            power1 += sum(hourly_power[days_ago][i] for i in range1) * UNIT
            power2 += sum(hourly_power[days_ago][i] for i in range2) * UNIT
            if (day - days_ago) % 7 < 5:  # 平日
                power3_weekday += sum(hourly_power[days_ago][i] for i in range3) * UNIT
            else:  # 週末
                power3_weekend += sum(hourly_power[days_ago][i] for i in range3) * UNIT
            power4 += sum(hourly_power[days_ago][i] for i in range4) * UNIT
            power5 += sum(hourly_power[days_ago][i] for i in range5) * UNIT

        fee1 = power1 * self.rate3
        fee2 = power2 * self.rate2
        fee3 = power3_weekday * self.rate1 + power3_weekend * self.rate2
        fee4 = power4 * self.rate2
        fee5 = power5 * self.rate3

        # 合計使用電力量
        power = power1 + power2 + power3_weekday + power3_weekend + power4 + power5

        # 料金計算
        fee = self.base
        fee += fee1 + fee2 + fee3 + fee4 + fee5

        # 燃料費調整額・再エネ発電賦課金 加算
        fee += self.nencho * power + int(self.saiene * power)

        return int(fee), int(power)


    def chubu_smartlife_asa(self, contract, hourly_power, day, UNIT):
        """
        中部電力: スマートライフプラン（朝とく）
        2024.4.1 料金改定版
        ※祝祭日料金には対応していません。

        基本料金                base
        10kVAまで   : 1,838.44円
        10kVA超過分 :   321.14円/1kVA

        従量料金
        デイタイム : 10時〜17時 : 38.80円/kWh  rate1 (土日はrate2)
        @ホームタイム : 9時〜10時、17時〜23時 : 28.61円/kwh  rate2
        ナイトタイム : 23時〜翌9時 : 16.52円/kWh  rate3

        燃料費調整単価（2024.5/毎月更新）
        0.04円/kWh             nencho

        再エネ発電賦課金（〜2025.4）
        3.49円/kWh              saiene

        電気料金（税込） = int(基本料金 + 従量料金 + 燃料費調整額) + int(再エネ発電賦課金)

        Parameters
        ----------
        contract : int
            契約アンペア数
        hourly_power : float
            料金計算期間の1時間ごとの使用電力量（kWh）: リスト
        day : int
            曜日番号 （0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日）

        Returns
        -------
        fee: int
            電気料金
        """

        # 集計時間帯の指定 : スマートライフプラン（スタンダード）
        range1 = range(0, 9)    # 時間帯1:  0時 〜  9時 / rate3
        range2 = range(9, 10)   # 時間帯2:  9時 〜 10時 / rate2
        range3 = range(10, 17)  # 時間帯3: 10時 〜 17時 / rate1 (土日は rate2)
        range4 = range(17, 23)  # 時間帯3: 17時 〜 23時 / rate2
        range5 = range(23, 24)  # 時間帯3: 23時 〜 24時 / rate3
        
        # 時間帯ごとの使用電力量の集計
        power1 = 0
        power2 = 0
        power3_weekday = 0
        power3_weekend = 0
        power4 = 0
        power5 = 0

        for days_ago in range(self.start, len(hourly_power)):
            power1 += sum(hourly_power[days_ago][i] for i in range1) * UNIT
            power2 += sum(hourly_power[days_ago][i] for i in range2) * UNIT
            if (day - days_ago) % 7 < 5:  # 平日
                power3_weekday += sum(hourly_power[days_ago][i] for i in range3) * UNIT
            else:  # 週末
                power3_weekend += sum(hourly_power[days_ago][i] for i in range3) * UNIT
            power4 += sum(hourly_power[days_ago][i] for i in range4) * UNIT
            power5 += sum(hourly_power[days_ago][i] for i in range5) * UNIT

        fee1 = power1 * self.rate3
        fee2 = power2 * self.rate2
        fee3 = power3_weekday * self.rate1 + power3_weekend * self.rate2
        fee4 = power4 * self.rate2
        fee5 = power5 * self.rate3

        # 合計使用電力量
        power = power1 + power2 + power3_weekday + power3_weekend + power4 + power5

        # 料金計算
        fee = self.base
        fee += fee1 + fee2 + fee3 + fee4 + fee5
        
        # 燃料費調整額・再エネ発電賦課金 加算
        fee += self.nencho * power + int(self.saiene * power)

        return int(fee), int(power)


    def chubu_smartlife_yoru(self, contract, hourly_power, day, UNIT):
        """
        中部電力: スマートライフプラン（夜とく）
        2024.4.1 料金改定版
        ※祝祭日料金には対応していません。

        基本料金                base
        10kVAまで   : 1,838.44円
        10kVA超過分 :   321.14円/1kVA

        従量料金
        デイタイム : 10時〜17時 : 38.80円/kWh  rate1 (土日はrate2)
        @ホームタイム : 7時〜10時、17時〜21時 : 28.61円/kwh  rate2
        ナイトタイム : 21時〜翌7時 : 16.52円/kWh  rate3

        燃料費調整単価（2024.5/毎月更新）
        0.04円/kWh             nencho

        再エネ発電賦課金（〜2025.4）
        3.49円/kWh              saiene

        電気料金（税込） = int(基本料金 + 従量料金 + 燃料費調整額) + int(再エネ発電賦課金)

        Parameters
        ----------
        contract : int
            契約アンペア数
        hourly_power : float
            料金計算期間の1時間ごとの使用電力量（kWh）: リスト
        day : int
            曜日番号 （0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日）

        Returns
        -------
        fee: int
            電気料金
        """

        # 集計時間帯の指定 : スマートライフプラン（スタンダード）
        range1 = range(0, 7)    # 時間帯1:  0時 〜  7時 / rate3
        range2 = range(7, 10)   # 時間帯2:  7時 〜 10時 / rate2
        range3 = range(10, 17)  # 時間帯3: 10時 〜 17時 / rate1 (土日は rate2)
        range4 = range(17, 21)  # 時間帯3: 17時 〜 21時 / rate2
        range5 = range(21, 24)  # 時間帯3: 21時 〜 24時 / rate3
        
        # 時間帯ごとの使用電力量の集計
        power1 = 0
        power2 = 0
        power3_weekday = 0
        power3_weekend = 0
        power4 = 0
        power5 = 0

        for days_ago in range(self.start, len(hourly_power)):
            power1 += sum(hourly_power[days_ago][i] for i in range1) * UNIT
            power2 += sum(hourly_power[days_ago][i] for i in range2) * UNIT
            if (day - days_ago) % 7 < 5:  # 平日
                power3_weekday += sum(hourly_power[days_ago][i] for i in range3) * UNIT
            else:  # 週末
                power3_weekend += sum(hourly_power[days_ago][i] for i in range3) * UNIT
            power4 += sum(hourly_power[days_ago][i] for i in range4) * UNIT
            power5 += sum(hourly_power[days_ago][i] for i in range5) * UNIT

        fee1 = power1 * self.rate3
        fee2 = power2 * self.rate2
        fee3 = power3_weekday * self.rate1 + power3_weekend * self.rate2
        fee4 = power4 * self.rate2
        fee5 = power5 * self.rate3

        # 合計使用電力量
        power = power1 + power2 + power3_weekday + power3_weekend + power4 + power5

        # 料金計算
        fee = self.base
        fee += fee1 + fee2 + fee3 + fee4 + fee5
        
        # 燃料費調整額・再エネ発電賦課金 加算
        fee += self.nencho * power + int(self.saiene * power)

        return int(fee), int(power)
