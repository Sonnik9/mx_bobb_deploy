from typing import *

# --- CORE ---   
SYMBOL: str = None   # "OP" | другой токен | None -- будет брать из сообщения  

# --------- RISK ---------------
QUOTE_ASSET: str = "USDT"
DIRECTION: str = "LONG"
TEG_ANCHOR: str = "UPBIT LISTING"              

TG_BOT_TOKEN: str = "7976740718:AAE1xBujUM26JfvefRr1hkcA12yfUC9e9qk" # bot token
TG_GROUP_ID: str = "-1002653345160" # id группы откуда парсить сигнал
# TG_BOT_TOKEN: str = "8304645115:AAE5HKrTclLDoRmE5W60vLRurbEH_fm-qyU" # -- токен бота (test)
# TG_GROUP_ID: str = "-1003053085303" # -- id группы откуда парсить сигнал (test)

# //
CAP_MULTIPLITER_TRUE: bool = False           # задействуем механизм зависомостей капы от множителя размера
MULTIPLITER_TYPE: int = 1                    # 1-- увеличиваем за счет маржи; 2 -- за счет плеча
CAP_DEP: dict = {                        
    (0, 500_000): 1.0,   
    (500_000, 1_000_000): 2.0,
    (1_000_000, float('inf')): 3.0,
}

# -- UTILS ---
TIME_ZONE: str = "UTC"
SLIPPAGE_PCT: float = 0.02 # % -------------------- поправка для расчетов PnL
SIGNAL_TIMEOUT: float = 10 # sec ------------------ время в течение которого сиглал актуален
PRECISION: int = 28 # ------------------------------точность расчетов decimal (нужно для особо малых чисел)

# --- SYSTEM ---
TG_UPDATE_FREQUENCY: float = 1.0 # sec
POSITIONS_UPDATE_FREQUENCY: float = 1.0 # sec
MAIN_CYCLE_FREQUENCY: float = 1.0 # sec
TP_CONTROL_FREQUENCY: float = 0.25 # sec
SIGNAL_PROCESSING_LIMIT: int = 5 # ----------------- ограничивает количество одновременной обработки сигналов
PING_URL = "https://contract.mexc.com/api/v1/contract/ping"
PING_INTERVAL = 10  # сек # -- ping сессии. Дергаем для контроля и оживления
USE_CACHE = False  # для деплоя лучше False

# /
# ----- параметры сонной паузы между установкой лимитных ордеров ------------
BASE_PAUSE = 1.0           # стартовая пауза
NOISE = 0.5                # рандомная добавка от 0 до NOISE
INCREMENT = 0.5            # прибавка каждые 2 ордера

# --- STYLES ---
HEAD_WIDTH = 35
HEAD_LINE_TYPE = "" #  либо "_"
FOOTER_WIDTH = 35
FOOTER_LINE_TYPE = "" #  либо "_"
EMO_SUCCESS = "🟢"
EMO_LOSE = "🔴"
EMO_ZERO = "⚪"
EMO_ORDER_FILLED = "🤞"


# ------- BUTTON DEFAULT SETTINGS ------
RANGE_KEYS = ["0-500", "500-1000", "1000+"]
TP_LEVELS_DEFAULT: List[Tuple[float, float]] = [  # дефолтная линейка тейк-профитов (процент , объём в %)
    (3, 20),
    (7, 20),
    (10, 20),
    (15, 20),
    (20, 20)
]
INIT_USER_CONFIG = {
    "config": {
        "MEXC": {
            "proxy_url": None, # формат: http://zmEnP8Af:F7i34xHB@45.10.108.116:64762  (логин-пароль-адрес-порт)
            "api_key": "",
            "api_secret": "",
            "u_id": ""
            # "api_key": "mx0vglqofJZUljkoYU",
            # "api_secret": "c6700595729849759d4e89989a7e0ecc",
            # "u_id": "WEB242b9e58e0e4f2d55f184870de2a16a520bf1d3969a7240c821b19d308abf91b"
        },
        "fin_settings": {
            "margin_size": None,
            "margin_mode": 2,
            "leverage": 5,
            "sl": 3.0,
            "sl_type": 2,
            # "tp_cap_dep": {rk: [] for rk in RANGE_KEYS},                                     
            "tp_cap_dep": {"0-500": [10, 25, 50, 75, 100],
                "500-1000": [5, 10, 15, 20, 30],
                "1000+": [3, 7, 10, 15, 20],
            },

            "use_default_tp": True,
            "tp_order_volume": 20,
            "tp_levels": [x for x in TP_LEVELS_DEFAULT.copy() if x]
        }
    },
    "_await_field": None # system
}
