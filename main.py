import asyncio
import time
from typing import *

from a_config import *
from b_context import BotContext, UserInstances
from b_constructor import PositionVarsSetup
from b_network import NetworkManager
from API.TG.tg_parser import TgBotWatcherAiogram
from API.TG.tg_notifier import TelegramNotifier
from API.TG.tg_buttons import TelegramUserInterface
from API.MX.mx import MexcClient, MexcPublic
from API.MX.streams import MxFuturesOrderWS
# from API.MX.mx_bypass.api import MexcFuturesAPI
from TRADING.entry import EntryControl
from TRADING.exit import ExitControl
from TRADING.tp import TPControl
from aiogram import Bot, Dispatcher
import json

from c_sync import Synchronizer
from c_log import ErrorHandler, log_time
from c_utils import Utils, FileManager, validate_direction, tp_levels_generator
import traceback
import os

SIGNAL_REPEAT_TIMEOUT = 5

def force_exit(*args):
    print("💥 Принудительное завершение процесса")
    os._exit(1)  # немедленно убивает процесс

def save_to_json(data: Optional[dict], filename="data.json"):
    """
    Сохраняет словарь/список в JSON-файл с отступами.

    :param data: dict или list – данные для сохранения
    :param filename: str – путь до файла (например, '/home/user/data.json')
    """
    try:
        # Убедимся, что директория существует
        # os.makedirs(os.path.dirname(filename), exist_ok=False)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Файл сохранён: {filename}")
    except Exception as e:
        print(f"Ошибка при сохранении: {e}")


class Core:
    def __init__(self):
        self.context = BotContext()
        self.info_handler = ErrorHandler()
        self.bot = Bot(token=TG_BOT_TOKEN)
        self.dp = Dispatcher()
        self.tg_watcher = None
        self.notifier = None
        self.tg_interface = None  # позже инициализируем
        self.positions_task = None
        self.tp_tasks = {}

        self.base_symbol = SYMBOL + "_" + QUOTE_ASSET if SYMBOL is not None else None
        self.direction = DIRECTION.strip().upper()
        self.context.pos_loaded_cache = {}
        self.instruments_data = {}        

    def _start_validation(self):
        if not validate_direction(self.direction):
            return False     
           
        if USE_CACHE:
            self.cache_file_manager = FileManager(info_handler=self.info_handler)

        return True
    
    def _start_common_context(self):

        # --- Вспомогалки ---
        # print(self.utils)
        self.mx_public = MexcPublic(context=self.context)

        self.utils = Utils(
            context=self.context,
            info_handler=self.info_handler,
            preform_message=self.notifier.preform_message
        )

        self.pos_setup = PositionVarsSetup(
            context=self.context,
            info_handler=self.info_handler,
            parse_precision=self.utils.parse_precision
        )

        # --- Торговые контролы ---
        self.entry = EntryControl(
            context=self.context,
            info_handler=self.info_handler,            
            preform_message=self.notifier.preform_message,
            utils=self.utils,
            direction=self.direction,
        )

        self.exit = ExitControl(
            context=self.context,
            info_handler=self.info_handler,
            preform_message=self.notifier.preform_message,
            direction=self.direction,
        )

        self.sync = Synchronizer(
            context=self.context,
            info_handler=self.info_handler,
            set_pos_defaults=self.pos_setup.set_pos_defaults,
            pnl_report=self.utils.pnl_report,
            preform_message=self.notifier.preform_message,
            positions_update_frequency=POSITIONS_UPDATE_FREQUENCY,
            exit=self.exit,
            use_cache=USE_CACHE,
        )

        self.tp_control = TPControl(
            context=self.context,
            info_handler=self.info_handler,
            preform_message=self.notifier.preform_message,
            utils=self.utils,
            direction=self.direction,
            tp_control_frequency=TP_CONTROL_FREQUENCY,
        )

    async def _start_user_context(self, user_id: int):
        """Инициализация юзер-контекста (сессии, клиентов, стримов и контролов)"""

        user_context = self.context.users_configs[user_id]
        mexc_cfg = user_context.get("config", {}).get("MEXC", {})

        proxy_url = mexc_cfg.get("proxy_url")
        api_key = mexc_cfg.get("api_key")
        api_secret = mexc_cfg.get("api_secret")
        u_id = mexc_cfg.get("u_id")

        # 🔹 Создаём или получаем UserInstances
        if user_id not in self.context.users_instances:
            self.context.users_instances[user_id] = UserInstances()

        user_instance = self.context.users_instances[user_id]

        # --- Чистим старый connector ---
        if user_instance.connector is not None:
            await user_instance.connector.shutdown_session()
            user_instance.connector = None

        # --- Создаём новый connector ---
        user_instance.connector = NetworkManager(
            context=self.context,
            info_handler=self.info_handler,
            proxy_url=proxy_url
        )
        user_instance.connector.start_ping_loop()

        # --- Создаём MEXC client ---
        user_instance.mx_client = MexcClient(
            context=self.context,
            connector=user_instance.connector,
            info_handler=self.info_handler,
            api_key=api_key,
            api_secret=api_secret,
            token=u_id,
        )

        # --- Создаём Order stream ---
        user_instance.order_stream = MxFuturesOrderWS(
            api_key=api_key,
            api_secret=api_secret,
            context=self.context,
            info_handler=self.info_handler,
            proxy_url=proxy_url
        )
        asyncio.create_task(user_instance.order_stream.start())

        # --- Запуск наблюдателей Telegram ---
        self.tg_watcher.register_handler(tag=TEG_ANCHOR)
        if not USE_CACHE:
            self.cache_file_manager = {}

        # --- Запуск positions_flow_manager ---
        if not self.positions_task or self.positions_task.done():
            self.positions_task = asyncio.create_task(
                self.sync.positions_flow_manager(cache_file_manager=self.cache_file_manager)
            )

        # --- Ожидание события обновления ордеров ---
        orders_event = self.context.context_vars[user_id]["orders_updated_event"]
        await orders_event.wait()
        orders_event.clear()
        print("[DEBUG] Order update event cleared, entering main signal loop")

        # --- Оборачиваем внешние методы в обработчик ошибок ---
        self.info_handler.wrap_foreign_methods(self)

    async def handle_signal(
        self,
        user_id,
        symbol: str,
        cap: float,
        last_timestamp: str,
        debug_label: str,
        lock
    ) -> None:
        
        async with lock:
            try:
                # ==== Финансовые настройки пользователя ====
                fin_settings = self.context.users_configs[user_id]["config"]["fin_settings"]

                # Генерируем новые tp_levels
                new_tp_levels = tp_levels_generator(
                    cap=cap,
                    tp_order_volume=fin_settings.get("tp_order_volume"),
                    tp_cap_dep=fin_settings["tp_levels"]
                )
                fin_settings["tp_levels_gen"] = new_tp_levels

                # ==== Установка позиции по умолчанию ====
                if not self.pos_setup.set_pos_defaults(symbol, self.direction, self.instruments_data):
                    return

                # Ждём, пока первый апдейт позиций не произойдёт
                while not self.sync._first_update_done:
                    # self.info_handler.debug_info_notes(f"[handle_signal] Waiting for first positions update for {symbol}")
                    await asyncio.sleep(0.1)

                pos_data = self.context.position_vars.get(symbol, {}).get(self.direction, {})

                # Защита 1: уже в позиции (по данным биржи)
                if pos_data.get("in_position"):
                    pos_data["preexisting"] = True
                    self.info_handler.debug_info_notes(
                        f"[handle_signal] Skip: already in_position {symbol} {self.direction}"
                    )
                    return

                # ==== Отправка сигнала ====
                signal_body = {"symbol": symbol, "cur_time": last_timestamp}
                self.notifier.preform_message(
                    user_id=user_id,
                    marker="signal",
                    body=signal_body,
                    is_print=True
                )

                await self.entry.entry_template(
                    symbol=symbol,
                    cap=cap,
                    debug_label=debug_label
                )

            finally:
                pass


    async def _run_iteration(self) -> None:
        """Одна итерация торговли (от старта до стопа)."""
        print("[CORE] Iteration started")

        # --- Перебор пользователей ---
        for num, (user_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
            # print(f"[DEBUG] Processing user {num} | user_id: {user_id}")

            try:
                await self._start_user_context(user_id=user_id)

                # --- Дебаг MEXC настройки ---
                user_config: Dict[str, Any] = self.context.users_configs.get(user_id, {})
                mexc_cfg: Dict[str, Any] = user_config.get("config", {}).get("MEXC", {})
                # print(f"[DEBUG] MEXC config for user {user_id}: {mexc_cfg}")

                required_keys = ["api_key", "api_secret", "u_id", "proxy_url"]
                for key in required_keys:
                    if key not in mexc_cfg or mexc_cfg[key] is None:
                        print(f"[WARNING] MEXC {key} not set for user {user_id}")

            except Exception as e:
                err_msg = f"[ERROR] Failed to start user context for user_id {user_id}: {e}"
                self.info_handler.debug_error_notes(err_msg, is_print=True)
                continue

        instrume_update_interval = 300.0
        last_instrume_time = time.monotonic()
        first_signal = False

        while not self.context.stop_bot:
            try:
                signal_tasks_val = self.context.message_cache[-SIGNAL_PROCESSING_LIMIT:] if self.context.message_cache else None
                if not signal_tasks_val:
                    await asyncio.sleep(MAIN_CYCLE_FREQUENCY)
                    continue

                for signal_item in signal_tasks_val:
                    if not signal_item:
                        continue

                    message, last_timestamp = signal_item
                    if not (message and last_timestamp):
                        print("[DEBUG] Invalid signal item, skipping")
                        continue

                    msg_key = f"{last_timestamp}_{hash(message)}"
                    if msg_key in self.context.tg_timing_cache:
                        continue
                    self.context.tg_timing_cache.add(msg_key)

                    parsed_msg, all_present = self.tg_watcher.parse_tg_message(message)
                    # print(parsed_msg)
                    if not all_present:
                        print(f"[DEBUG] Parse error: {parsed_msg}")
                        continue

                    symbol = parsed_msg.get("symbol")
                    cap = parsed_msg.get("cap")
                    debug_label = f"{symbol}_{self.direction}"
                    if self.base_symbol and symbol != self.base_symbol:
                        continue

                    diff_sec = time.time() - (last_timestamp / 1000)

                    for num, (user_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
                        if not self.context.context_vars[user_id]["stop_bot_iteration"]:

                            if diff_sec < SIGNAL_TIMEOUT:

                                # если замок уже существует для msg_key, пропускаем
                                if msg_key in self.context.signal_locks:
                                    continue

                                # создаём замок и оставляем его навсегда
                                cur_lock = self.context.signal_locks[msg_key] = asyncio.Lock()
                                first_signal = True

                                asyncio.create_task(self.handle_signal(
                                    user_id=user_id,
                                    symbol=symbol,
                                    cap=cap,
                                    last_timestamp=last_timestamp,
                                    debug_label=debug_label,
                                    lock=cur_lock
                                ))

            except Exception as e:
                err_msg = f"[ERROR] main loop: {e}\n" + traceback.format_exc()
                self.info_handler.debug_error_notes(err_msg, is_print=True)

            finally:
                # ==== TP Control ====
                if first_signal:
                    symbol_data = self.context.position_vars.get(symbol)
                    if symbol_data:  # проверка, чтобы не было KeyError
                        if debug_label not in self.tp_tasks or self.tp_tasks[debug_label].done():
                            self.tp_tasks[debug_label] = asyncio.create_task(
                                self.tp_control.tp_control_flow(
                                    symbol=symbol,
                                    symbol_data=symbol_data,
                                    sign=1 if self.direction == "LONG" else -1,
                                    debug_label=debug_label,
                                )
                            )
                    else:
                        print(f"[WARNING] TP control skipped: symbol {symbol} not in position_vars yet")

                try:
                    for num, (user_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
                        await self.notifier.send_report_batches(user_id=user_id, batch_size=1)
                except Exception as e:
                    err_msg = f"[ERROR] main finally block: {e}\n" + traceback.format_exc()
                    self.info_handler.debug_error_notes(err_msg, is_print=True)

                now = time.monotonic()

                # обновление кэша
                if now - last_instrume_time >= instrume_update_interval:
                    try:
                        self.instruments_data = await self.mx_client.self.mx_public()
                        if not self.instruments_data:
                            self.info_handler.debug_error_notes(f"[ERROR] Failed to fetch instruments: {e}", is_print=True)

                    except Exception as e:
                        self.info_handler.debug_error_notes(f"[ERROR] Failed to fetch instruments: {e}", is_print=True)

                    last_instrume_time = now

                await asyncio.sleep(MAIN_CYCLE_FREQUENCY)

    async def run_forever(self, debug: bool = True):
        """Основной перезапускаемый цикл Core."""
        if debug: print("[CORE] run_forever started")

        # Запуск Telegram UI один раз
        if self.tg_interface is None:
            self.tg_watcher = TgBotWatcherAiogram(
                dp=self.dp,
                channel_id=TG_GROUP_ID,
                context=self.context,
                info_handler=self.info_handler
            )
            self.tg_watcher.register_handler(tag=TEG_ANCHOR)

            self.tg_interface = TelegramUserInterface(
                bot=self.bot,
                dp=self.dp,
                context=self.context,
                info_handler=self.info_handler,
            )

            self.notifier = TelegramNotifier(
                bot=self.bot,
                context=self.context,
                info_handler=self.info_handler
            )

            await self.tg_interface.run()  # polling стартует уже с зарегистрированными хендлерами

        self._start_common_context()

        # --- Получаем инструменты с биржи ---
        try:
            self.instruments_data = await self.mx_client.self.mx_public()
            if self.instruments_data:
                # save_to_json(self.instruments_data)
                print(f"[DEBUG] Instruments fetched: {len(self.instruments_data)} items")
                pass
            else:
                self.info_handler.debug_error_notes(f"[ERROR] Failed to fetch instruments: {e}", is_print=True)

        except Exception as e:
            self.info_handler.debug_error_notes(f"[ERROR] Failed to fetch instruments: {e}", is_print=True)
        # return

        # --- Проверяем базовый контекст ---
        if not self._start_validation():
            for num, (user_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
                self.context.context_vars[user_id]["stop_bot_iteration"] = True
            print("[DEBUG] Usual context start failed, iteration stopped")
            return
        # print("[DEBUG] Usual context initialized successfully")

        while not self.context.stop_bot:
            for num, (user_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
                if debug: print(f"[CORE] Новый цикл run_forever для {user_id}, обнуляем флаги итерации")
                self.context.context_vars[user_id]["start_bot_iteration"] = False
                self.context.context_vars[user_id]["stop_bot_iteration"] = False

                # ждём нажатия кнопки START
                if debug: print("[CORE] Ожидание кнопки START...")
                while not self.context.context_vars[user_id]["start_bot_iteration"] and not self.context.stop_bot:
                    await asyncio.sleep(0.3)

                if self.context.stop_bot:
                    if debug: print("[CORE] Stop флаг поднят, выходим из run_forever")
                    break

                # запускаем итерацию торговли
                try:
                    if debug: print("[CORE] Запуск торговой итерации (_run_iteration)...")
                    await self._run_iteration()
                    if debug: print("[CORE] Торговая итерация завершена")
                except Exception as e:
                    self.info_handler.debug_error_notes(f"[CORE] Ошибка в итерации: {e}", is_print=True)

                # очищаем ресурсы итерации
                try:
                    if debug: print("[CORE] Очистка ресурсов итерации (_shutdown_iteration)...")
                    await self._shutdown_iteration(user_id=user_id, debug=debug)
                    if debug: print("[CORE] Очистка ресурсов завершена")
                except Exception as e:
                    self.info_handler.debug_error_notes(f"[CORE] Ошибка при shutdown итерации: {e}", is_print=True)

                # если была локальная остановка — ждём нового START
                if self.context.context_vars[user_id]["stop_bot_iteration"]:
                    self.info_handler.debug_info_notes("[CORE] Перезапуск по кнопке STOP", is_print=True)
                    if debug: print("[CORE] Ожидание следующего START после STOP")
                    continue

        if debug: print("[CORE] run_forever finished")

    async def _shutdown_iteration(self, user_id: str, debug: bool = True):
        """Закрывает итерационные ресурсы и обнуляет инстансы."""

        # --- Остановка цикла positions_flow_manager ---
        if self.positions_task:
            self.positions_task.cancel()
            try:
                await self.positions_task
            except asyncio.CancelledError:
                if debug:
                    print("[CORE] positions_flow_manager cancelled")
            self.positions_task = None

        # --- Order stream ---
        if "order_stream" in self.context.users_instances[user_id]:
            try:
                await asyncio.wait_for(self.context.users_instances[user_id]["order_stream"].disconnect(), timeout=5)
            except Exception as e:
                if debug:
                    print(f"[CORE] order_stream.disconnect() error: {e}")
            finally:
                self.context.users_instances[user_id]["order_stream"] = None

        # --- Connector ---
        if "connector" in self.context.users_instances[user_id]:
            try:
                await asyncio.wait_for(self.context.users_instances[user_id]["connector"].shutdown_session(), timeout=5)
            except Exception as e:
                if debug:
                    print(f"[CORE] connector.shutdown_session() error: {e}")
            finally:
                self.context.context_vars[user_id]["session"] = None
                self.context.users_instances[user_id]["connector"] = None

        for key, task in list(self.tp_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tp_tasks.clear()

        # --- Сброс прочих ссылок ---
        self.context.users_instances[user_id]["mx_client"] = None
        self.sync = None
        self.tp_control = None
        self.utils = None
        self.pos_setup = None
        self.entry = None
        self.exit = None

        self.context.position_vars = {}


async def main():
    instance = Core()
    try:
        # ставим таймаут на работу, чтобы любой зависший таск не блокировал forever
        await asyncio.wait_for(instance.run_forever(), timeout=None)
    except asyncio.CancelledError:
        print("🚨 CancelledError caught")
    finally:
        print("♻️ Cleaning up iteration")
        instance.context.stop_bot = True
        await instance._shutdown_iteration()

if __name__ == "__main__":
    # жёсткое убийство через Ctrl+C / kill
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("💥 Force exit")
    os._exit(1)