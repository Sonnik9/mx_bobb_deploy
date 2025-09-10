from __future__ import annotations
from typing import *
from dataclasses import dataclass
import asyncio
import aiohttp

if TYPE_CHECKING:
    from b_network import NetworkManager
    from API.MX.mx import MexcClient
    from API.MX.streams import MxFuturesOrderWS


class UserConfigs(TypedDict, total=False):
    session: Optional[aiohttp.ClientSession]
    start_bot_iteration: bool
    stop_bot_iteration: bool
    bot_iteration_lock: asyncio.Lock
    position_updated_event: asyncio.Event
    orders_updated_event: asyncio.Event

@dataclass
class UserInstances:
    connector: Optional["NetworkManager"] = None
    mx_client: Optional["MexcClient"] = None
    order_stream: Optional["MxFuturesOrderWS"] = None


class BotContext:
    def __init__(self):
        """ Инициализируем глобальные структуры"""
        # //
        self.message_cache: list = []  # основной кеш сообщений
        self.tg_timing_cache: set = set()
        self.queues_msg: Dict = {}     

        self.context_vars: dict[int, UserConfigs] = {} # --
        self.users_configs: dict[int, Any] = {}
        self.users_instances: dict[int, UserInstances] = {} # --
        self.position_vars: dict = {}
        self.order_stream_data: dict = {}

        # //
        self.pos_loaded_cache = None
        self.instruments_data: dict = None        

        # self.bloc_async = asyncio.Lock()

        self.stop_bot: bool = False
        self.signal_locks: dict = {}