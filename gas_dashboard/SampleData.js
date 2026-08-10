// smm3-sample デプロイ専用の固定データ（2026-08-10時点の本番実データをスナップショット）。
// isSampleDeployment()がtrueの時だけCode.js側から参照される。健全性(health)・リブート履歴(reboot)は
// 実機が存在しないため架空の値に差し替え済み。今日/週/月/瞬時数値は実際の値を凍結表示している
// （ダッシュボードの見た目のサンプルとして提示する目的で、ユーザー合意のうえ実数値を使用）。

var SAMPLE_SNAPSHOT = {
  "current": {
    "watt": 664,
    "amp": 8,
    "muted": false,
    "updatedAt": "2026-08-10T12:00:00.000Z"
  },
  "cuml": {
    "created": "2026-08-10 16:00:00",
    "collect": "2026-07-23 00:00:00",
    "e_energy": 733,
    "monthly_e_energy": 276,
    "charge": 9639,
    "type": "cuml"
  },
  "today": {
    "today": [
      0.5,
      0.3,
      0.4,
      0.2,
      0.2,
      0.2,
      0.2,
      0.2,
      0.1,
      0.2,
      0.2,
      0.2,
      0.2,
      0.2,
      0.3,
      0.4,
      0.3,
      0.3,
      0.4,
      0.5,
      0.3,
      0.2,
      0.2,
      0.3,
      0.3,
      0.1,
      0.2,
      0.1,
      0.2,
      0.4,
      0.5,
      0.4,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    "yesterday": [
      0.3,
      0.2,
      0.2,
      0.3,
      0.2,
      0.2,
      0.2,
      0.3,
      0.2,
      0.1,
      0.1,
      0.2,
      0.1,
      0.2,
      0.1,
      0.3,
      0.2,
      0.2,
      0.3,
      0.5,
      0.4,
      0.5,
      0.4,
      0.4,
      0.4,
      0.5,
      0.5,
      0.4,
      0.3,
      0.3,
      0.2,
      0.2,
      0.3,
      0.2,
      0.6,
      0.9,
      0.8,
      0.8,
      0.6,
      0.6,
      0.5,
      0.3,
      0.5,
      0.3,
      0.3,
      0.3,
      0.4,
      0.3
    ]
  },
  "week": {
    "today": 8.7,
    "days": [
      {
        "date": "8/9",
        "sub": 9.2,
        "total": 16.6
      },
      {
        "date": "8/8",
        "sub": 10.7,
        "total": 14.4
      },
      {
        "date": "8/7",
        "sub": 9.7,
        "total": 15.3
      },
      {
        "date": "8/6",
        "sub": 8.3,
        "total": 15.8
      },
      {
        "date": "8/5",
        "sub": 7.5,
        "total": 12.8
      },
      {
        "date": "8/4",
        "sub": 5.9,
        "total": 10.7
      },
      {
        "date": "8/3",
        "sub": 6.5,
        "total": 9.9
      }
    ],
    "avgSub": 8.26,
    "avgTotal": 13.64
  },
  "month": {
    "today": 8.7,
    "days": [
      {
        "date": "8/9",
        "sub": 9.2,
        "total": 16.6
      },
      {
        "date": "8/8",
        "sub": 10.7,
        "total": 14.4
      },
      {
        "date": "8/7",
        "sub": 9.7,
        "total": 15.3
      },
      {
        "date": "8/6",
        "sub": 8.3,
        "total": 15.8
      },
      {
        "date": "8/5",
        "sub": 7.5,
        "total": 12.8
      },
      {
        "date": "8/4",
        "sub": 5.9,
        "total": 10.7
      },
      {
        "date": "8/3",
        "sub": 6.5,
        "total": 9.9
      },
      {
        "date": "8/2",
        "sub": 15.8,
        "total": 22.1
      },
      {
        "date": "8/1",
        "sub": 11.7,
        "total": 20.1
      },
      {
        "date": "7/31",
        "sub": 9.1,
        "total": 12.5
      },
      {
        "date": "7/30",
        "sub": 7.1,
        "total": 15.2
      },
      {
        "date": "7/29",
        "sub": 7.8,
        "total": 12.9
      },
      {
        "date": "7/28",
        "sub": 6.6,
        "total": 11.2
      },
      {
        "date": "7/27",
        "sub": 7.6,
        "total": 13.4
      },
      {
        "date": "7/26",
        "sub": 12.6,
        "total": 17.8
      },
      {
        "date": "7/25",
        "sub": 9.4,
        "total": 13.4
      },
      {
        "date": "7/24",
        "sub": 6.8,
        "total": 12.6
      },
      {
        "date": "7/23",
        "sub": 12.7,
        "total": 21
      },
      {
        "date": "7/22",
        "sub": 11.5,
        "total": 23.2
      },
      {
        "date": "7/21",
        "sub": 11.4,
        "total": 22.1
      },
      {
        "date": "7/20",
        "sub": 11.4,
        "total": 20.2
      },
      {
        "date": "7/19",
        "sub": 9.9,
        "total": 13
      },
      {
        "date": "7/18",
        "sub": 7.5,
        "total": 12.6
      },
      {
        "date": "7/17",
        "sub": 8.1,
        "total": 13.3
      },
      {
        "date": "7/16",
        "sub": 4.6,
        "total": 10.5
      },
      {
        "date": "7/15",
        "sub": 9.2,
        "total": 15.4
      },
      {
        "date": "7/14",
        "sub": 7.9,
        "total": 14
      },
      {
        "date": "7/13",
        "sub": 6.8,
        "total": 11.6
      },
      {
        "date": "7/12",
        "sub": 9.6,
        "total": 15.8
      },
      {
        "date": "7/11",
        "sub": 11.3,
        "total": 16.4
      }
    ],
    "avgSub": 9.14,
    "avgTotal": 15.19
  },
  "tables": {
    "ytdy": {
      "rows": [
        {
          "hour": 0,
          "today": 0.8,
          "avg": 0.5,
          "diff": 0.3
        },
        {
          "hour": 1,
          "today": 0.6,
          "avg": 0.5,
          "diff": 0.1
        },
        {
          "hour": 2,
          "today": 0.4,
          "avg": 0.4,
          "diff": 0
        },
        {
          "hour": 3,
          "today": 0.4,
          "avg": 0.5,
          "diff": -0.1
        },
        {
          "hour": 4,
          "today": 0.3,
          "avg": 0.3,
          "diff": 0
        },
        {
          "hour": 5,
          "today": 0.4,
          "avg": 0.3,
          "diff": 0.1
        },
        {
          "hour": 6,
          "today": 0.4,
          "avg": 0.3,
          "diff": 0.1
        },
        {
          "hour": 7,
          "today": 0.7,
          "avg": 0.4,
          "diff": 0.3
        },
        {
          "hour": 8,
          "today": 0.6,
          "avg": 0.4,
          "diff": 0.2
        },
        {
          "hour": 9,
          "today": 0.9,
          "avg": 0.8,
          "diff": 0.1
        },
        {
          "hour": 10,
          "today": 0.5,
          "avg": 0.9,
          "diff": -0.4
        },
        {
          "hour": 11,
          "today": 0.5,
          "avg": 0.8,
          "diff": -0.3
        },
        {
          "hour": 12,
          "today": 0.4,
          "avg": 0.9,
          "diff": -0.5
        },
        {
          "hour": 13,
          "today": 0.3,
          "avg": 0.9,
          "diff": -0.6
        },
        {
          "hour": 14,
          "today": 0.6,
          "avg": 0.6,
          "diff": 0
        },
        {
          "hour": 15,
          "today": 0.9,
          "avg": 0.4,
          "diff": 0.5
        },
        {
          "hour": 16,
          "today": 0,
          "avg": 0.5,
          "diff": null
        },
        {
          "hour": 17,
          "today": 0,
          "avg": 1.5,
          "diff": null
        },
        {
          "hour": 18,
          "today": 0,
          "avg": 1.6,
          "diff": null
        },
        {
          "hour": 19,
          "today": 0,
          "avg": 1.2,
          "diff": null
        },
        {
          "hour": 20,
          "today": 0,
          "avg": 0.8,
          "diff": null
        },
        {
          "hour": 21,
          "today": 0,
          "avg": 0.8,
          "diff": null
        },
        {
          "hour": 22,
          "today": 0,
          "avg": 0.6,
          "diff": null
        },
        {
          "hour": 23,
          "today": 0,
          "avg": 0.7,
          "diff": null
        }
      ],
      "totalToday": 8.7,
      "totalAvg": 16.6,
      "ratio": 52
    },
    "avg7": {
      "rows": [
        {
          "hour": 0,
          "today": 0.8,
          "avg": 0.56,
          "diff": 0.24
        },
        {
          "hour": 1,
          "today": 0.6,
          "avg": 0.51,
          "diff": 0.09
        },
        {
          "hour": 2,
          "today": 0.4,
          "avg": 0.34,
          "diff": 0.06
        },
        {
          "hour": 3,
          "today": 0.4,
          "avg": 0.39,
          "diff": 0.01
        },
        {
          "hour": 4,
          "today": 0.3,
          "avg": 0.33,
          "diff": -0.03
        },
        {
          "hour": 5,
          "today": 0.4,
          "avg": 0.33,
          "diff": 0.07
        },
        {
          "hour": 6,
          "today": 0.4,
          "avg": 0.37,
          "diff": 0.03
        },
        {
          "hour": 7,
          "today": 0.7,
          "avg": 0.53,
          "diff": 0.17
        },
        {
          "hour": 8,
          "today": 0.6,
          "avg": 0.67,
          "diff": -0.07
        },
        {
          "hour": 9,
          "today": 0.9,
          "avg": 0.63,
          "diff": 0.27
        },
        {
          "hour": 10,
          "today": 0.5,
          "avg": 0.57,
          "diff": -0.07
        },
        {
          "hour": 11,
          "today": 0.5,
          "avg": 0.53,
          "diff": -0.03
        },
        {
          "hour": 12,
          "today": 0.4,
          "avg": 0.54,
          "diff": -0.14
        },
        {
          "hour": 13,
          "today": 0.3,
          "avg": 0.59,
          "diff": -0.29
        },
        {
          "hour": 14,
          "today": 0.6,
          "avg": 0.57,
          "diff": 0.03
        },
        {
          "hour": 15,
          "today": 0.9,
          "avg": 0.5,
          "diff": 0.4
        },
        {
          "hour": 16,
          "today": 0,
          "avg": 0.69,
          "diff": null
        },
        {
          "hour": 17,
          "today": 0,
          "avg": 0.93,
          "diff": null
        },
        {
          "hour": 18,
          "today": 0,
          "avg": 0.87,
          "diff": null
        },
        {
          "hour": 19,
          "today": 0,
          "avg": 0.8,
          "diff": null
        },
        {
          "hour": 20,
          "today": 0,
          "avg": 0.67,
          "diff": null
        },
        {
          "hour": 21,
          "today": 0,
          "avg": 0.6,
          "diff": null
        },
        {
          "hour": 22,
          "today": 0,
          "avg": 0.59,
          "diff": null
        },
        {
          "hour": 23,
          "today": 0,
          "avg": 0.54,
          "diff": null
        }
      ],
      "totalToday": 8.7,
      "totalAvg": 13.65,
      "ratio": 64
    },
    "avg30": {
      "rows": [
        {
          "hour": 0,
          "today": 0.8,
          "avg": 0.63,
          "diff": 0.17
        },
        {
          "hour": 1,
          "today": 0.6,
          "avg": 0.55,
          "diff": 0.05
        },
        {
          "hour": 2,
          "today": 0.4,
          "avg": 0.38,
          "diff": 0.02
        },
        {
          "hour": 3,
          "today": 0.4,
          "avg": 0.37,
          "diff": 0.03
        },
        {
          "hour": 4,
          "today": 0.3,
          "avg": 0.37,
          "diff": -0.07
        },
        {
          "hour": 5,
          "today": 0.4,
          "avg": 0.37,
          "diff": 0.03
        },
        {
          "hour": 6,
          "today": 0.4,
          "avg": 0.4,
          "diff": 0
        },
        {
          "hour": 7,
          "today": 0.7,
          "avg": 0.58,
          "diff": 0.12
        },
        {
          "hour": 8,
          "today": 0.6,
          "avg": 0.68,
          "diff": -0.08
        },
        {
          "hour": 9,
          "today": 0.9,
          "avg": 0.71,
          "diff": 0.19
        },
        {
          "hour": 10,
          "today": 0.5,
          "avg": 0.69,
          "diff": -0.19
        },
        {
          "hour": 11,
          "today": 0.5,
          "avg": 0.67,
          "diff": -0.17
        },
        {
          "hour": 12,
          "today": 0.4,
          "avg": 0.63,
          "diff": -0.23
        },
        {
          "hour": 13,
          "today": 0.3,
          "avg": 0.62,
          "diff": -0.32
        },
        {
          "hour": 14,
          "today": 0.6,
          "avg": 0.6,
          "diff": 0
        },
        {
          "hour": 15,
          "today": 0.9,
          "avg": 0.58,
          "diff": 0.32
        },
        {
          "hour": 16,
          "today": 0,
          "avg": 0.72,
          "diff": null
        },
        {
          "hour": 17,
          "today": 0,
          "avg": 0.9,
          "diff": null
        },
        {
          "hour": 18,
          "today": 0,
          "avg": 0.92,
          "diff": null
        },
        {
          "hour": 19,
          "today": 0,
          "avg": 0.85,
          "diff": null
        },
        {
          "hour": 20,
          "today": 0,
          "avg": 0.79,
          "diff": null
        },
        {
          "hour": 21,
          "today": 0,
          "avg": 0.72,
          "diff": null
        },
        {
          "hour": 22,
          "today": 0,
          "avg": 0.76,
          "diff": null
        },
        {
          "hour": 23,
          "today": 0,
          "avg": 0.7,
          "diff": null
        }
      ],
      "totalToday": 8.7,
      "totalAvg": 15.19,
      "ratio": 57
    }
  },
  "health": {
    "status": "ok",
    "lastSeenAt": "2026-08-10T12:00:00.000Z",
    "ageSec": 12,
    "lastType": "inst",
    "thresholdSec": 600
  },
  "settings": {
    "warnAmp": 30,
    "contractAmp": 40
  },
  "reboot": {
    "count": 5,
    "log": [
      {
        "n": 1,
        "at": "2026-08-01T00:00:00.000Z",
        "cause": 1,
        "gapMin": null
      },
      {
        "n": 2,
        "at": "2026-08-03T09:12:00.000Z",
        "cause": 2,
        "gapMin": 3132
      },
      {
        "n": 3,
        "at": "2026-08-05T21:40:00.000Z",
        "cause": 2,
        "gapMin": 3628
      },
      {
        "n": 4,
        "at": "2026-08-08T06:05:00.000Z",
        "cause": 2,
        "gapMin": 3505
      },
      {
        "n": 5,
        "at": "2026-08-10T07:31:00.000Z",
        "cause": 2,
        "gapMin": 3086
      }
    ]
  }
};
