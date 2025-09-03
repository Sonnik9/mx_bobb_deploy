import asyncio
import time
from typing import *
from a_config import *
from b_context import BotContext
from b_constructor import PositionVarsSetup
from b_network import NetworkManager
from API.TG.tg_parser import TgBotWatcherAiogram
from API.TG.tg_notifier import TelegramNotifier
from API.TG.tg_buttons import TelegramUserInterface
from API.MX.mx import MexcClient
from API.MX.streams import MxFuturesOrderWS
from TRADING.entry import EntryControl
from TRADING.exit import ExitControl
from TRADING.tp import TPControl
from aiogram import Bot, Dispatcher

from c_sync import Synchronizer
from c_log import ErrorHandler, log_time
from c_utils import Utils, FileManager, validate_direction, tp_levels_generator, parse_range_key
import traceback
import os

def force_exit(*args):
    print("💥 Принудительное завершение процесса")
    os._exit(1)  # немедленно убивает процесс


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

    def _start_usual_context(self):
        if not validate_direction(self.direction):
            return False     
           
        if USE_CACHE:
            self.cache_file_manager = FileManager(info_handler=self.info_handler)

        return True

    async def _start_user_context(self, chat_id: int):
        """Инициализация юзер-контекста (сессии, клиентов, стримов и контролов)"""

        user_context = self.context.users_configs[chat_id]
        mexc_cfg = user_context.get("config", {}).get("MEXC", {})

        proxy_url  = mexc_cfg.get("proxy_url")
        api_key    = mexc_cfg.get("api_key")
        api_secret = mexc_cfg.get("api_secret")
        u_id       = mexc_cfg.get("u_id")

        # print("♻️ Пересоздаём user_context сессию")

        # --- Чистим старый connector ---
        if hasattr(self, "connector") and self.connector:
            await self.connector.shutdown_session()
            self.connector = None

        # --- Создаём новый connector ---
        self.connector = NetworkManager(
            context=self.context,
            info_handler=self.info_handler,
            proxy_url=proxy_url
        )
        self.connector.start_ping_loop()

        # --- MEXC client ---
        self.mx_client = MexcClient(
            context=self.context,
            connector=self.connector,
            info_handler=self.info_handler,
            api_key=api_key,
            api_secret=api_secret,
            token=u_id,
        )

        # --- Order stream ---
        self.order_stream = MxFuturesOrderWS(
            api_key=api_key,
            api_secret=api_secret,
            context=self.context,
            info_handler=self.info_handler,
            proxy_url=proxy_url
        )
        asyncio.create_task(self.order_stream.start())  # запускаем только новый

        # --- Вспомогалки ---
        self.utils = Utils(
            context=self.context,
            info_handler=self.info_handler,
            preform_message=self.notifier.preform_message,
            chat_id=chat_id
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
            mx_client=self.mx_client,
            preform_message=self.notifier.preform_message,
            utils=self.utils,
            direction=self.direction,
            chat_id=chat_id
        )

        self.exit = ExitControl(
            context=self.context,
            info_handler=self.info_handler,
            mx_client=self.mx_client,
            preform_message=self.notifier.preform_message,
            direction=self.direction,
            chat_id=chat_id
        )

        self.sync = Synchronizer(
            context=self.context,
            info_handler=self.info_handler,
            set_pos_defaults=self.pos_setup.set_pos_defaults,
            pnl_report=self.utils.pnl_report,
            mx_client=self.mx_client,
            preform_message=self.notifier.preform_message,
            positions_update_frequency=POSITIONS_UPDATE_FREQUENCY,
            exit=self.exit,
            use_cache=USE_CACHE,
            chat_id=chat_id
        )

        self.tp_control = TPControl(
            context=self.context,
            info_handler=self.info_handler,
            mx_client=self.mx_client,
            preform_message=self.notifier.preform_message,
            utils=self.utils,
            direction=self.direction,
            tp_control_frequency=TP_CONTROL_FREQUENCY,
            chat_id=chat_id
        )

        # --- Заворачиваем внешние методы в обработчик ошибок ---
        self.info_handler.wrap_foreign_methods(self)

    async def handle_signal(
        self,
        chat_id,
        symbol: str,
        cap: float,                          
        last_timestamp: str,
        debug_label: str,
    ) -> None:
        try:
            # print(f"{symbol} cap: {cap}")

            # ==== Финансовые настройки пользователя ====
            fin_settings = self.context.users_configs[chat_id]["config"]["fin_settings"]
            # pprint(fin_settings)

            # Переводим строки диапазонов в кортежи
            fin_settings["tp_cap_dep"] = {
                parse_range_key(k): v for k, v in fin_settings.get("tp_cap_dep", {}).items()
            }

            # Генерируем новые tp_levels
            new_tp_levels = tp_levels_generator(
                cap=cap,
                tp_order_volume=fin_settings.get("tp_order_volume"),
                tp_cap_dep=fin_settings["tp_cap_dep"],
                use_default=fin_settings.get("use_default_tp")
            )
            fin_settings["tp_levels"] = new_tp_levels

            # pprint(fin_settings)

            # ==== Установка позиции по умолчанию ====
            if not self.pos_setup.set_pos_defaults(symbol, self.direction, self.instruments_data):
                return

            # Ждем, пока обновятся позиции
            await self.context.position_updated_event.wait()
            self.context.position_updated_event.clear()

            in_position = self.context.position_vars.get(symbol, {}).get(self.direction, {}).get("in_position", False)
            if in_position:
                self.is_any_position = True 
                return

            # ==== Отправка сигнала ====
            signal_body = {"symbol": symbol, "cur_time": last_timestamp}
            # print(signal_body)

            self.notifier.preform_message(
                chat_id=chat_id,
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
            # ==== TP Control ====
            symbol_data = self.context.position_vars.get(symbol)
            if symbol_data:  # проверка, чтобы не было KeyError
                if debug_label not in self.tp_tasks or self.tp_tasks[debug_label].done():
                    self.tp_tasks[debug_label] = asyncio.create_task(self.tp_control.tp_control_flow(
                        symbol=symbol,
                        symbol_data=symbol_data,
                        sign=1 if self.direction == "LONG" else -1,
                        debug_label=debug_label,
                    ))
            else:
                print(f"[WARNING] TP control skipped: symbol {symbol} not in position_vars yet")    

    async def _run_iteration(self) -> None:
        """Одна итерация торговли (от старта до стопа)."""
        # print("[CORE] Iteration started")

        # --- Проверяем базовый контекст ---
        if not self._start_usual_context():
            self.context.stop_bot_iteration = True
            print("[DEBUG] Usual context start failed, iteration stopped")
            return
        # print("[DEBUG] Usual context initialized successfully")

        # --- Перебор пользователей ---
        for num, (chat_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
            # print(f"[DEBUG] Processing user {num} | chat_id: {chat_id}")
            
            if num > 1:
                self.info_handler.debug_info_notes(
                    f"Бот настроен только для одного пользователя! "
                    f"Для текущего chat_id: {chat_id} опция торговли недоступна. {log_time()}"
                )
                continue

            try:
                # --- Запуск контекста пользователя ---
                # print(f"[DEBUG] Starting user context for chat_id: {chat_id}")
                await self._start_user_context(chat_id=chat_id)

                # --- Дебаг MEXC настройки ---
                user_config: Dict[str, Any] = self.context.users_configs.get(chat_id, {})
                mexc_cfg: Dict[str, Any] = user_config.get("config", {}).get("MEXC", {})
                # print(f"[DEBUG] MEXC config for user {chat_id}: {mexc_cfg}")

                required_keys = ["api_key", "api_secret", "u_id", "proxy_url"]
                for key in required_keys:
                    if key not in mexc_cfg or mexc_cfg[key] is None:
                        print(f"[WARNING] MEXC {key} not set for user {chat_id}")

            except Exception as e:
                err_msg = f"[ERROR] Failed to start user context for chat_id {chat_id}: {e}"
                self.info_handler.debug_error_notes(err_msg, is_print=True)
                continue

        # --- Получаем инструменты с биржи ---
        try:
            self.instruments_data = await self.mx_client.get_instruments()
            if self.instruments_data:
                # print(f"[DEBUG] Instruments fetched: {len(self.instruments_data)} items")
                pass
            else:
                self.info_handler.debug_error_notes(f"[ERROR] Failed to fetch instruments: {e}", is_print=True)

        except Exception as e:
            self.info_handler.debug_error_notes(f"[ERROR] Failed to fetch instruments: {e}", is_print=True)

        # --- Запуск наблюдателей ---
        self.tg_watcher.register_handler(tag=TEG_ANCHOR)
        if not USE_CACHE:
            self.cache_file_manager = {}
        # --- Запускаем positions_flow_manager ---
        if not self.positions_task or self.positions_task.done():
            self.positions_task = asyncio.create_task(
                self.sync.positions_flow_manager(cache_file_manager=self.cache_file_manager)
            )

        await self.context.orders_updated_event.wait()
        self.context.orders_updated_event.clear()
        # print("[DEBUG] Order update event cleared, entering main signal loop")

        # --- Основной цикл итерации ---
        while not self.context.stop_bot_iteration and not self.context.stop_bot:
            try:
                signal_tasks_val = self.context.message_cache[-SIGNAL_PROCESSING_LIMIT:] if self.context.message_cache else None
                if not signal_tasks_val:
                    # print("[DEBUG] No signal tasks available")
                    await asyncio.sleep(MAIN_CYCLE_FREQUENCY)
                    continue

                for signal_item in signal_tasks_val:
                    if not signal_item:
                        continue

                    message, last_timestamp = signal_item
                    if not (message and last_timestamp):
                        # print("[DEBUG] Invalid signal item, skipping")
                        continue

                    msg_key = f"{last_timestamp}_{hash(message)}"
                    if msg_key in self.context.tg_timing_cache:
                        continue
                    self.context.tg_timing_cache.add(msg_key)

                    parsed_msg, all_present = self.tg_watcher.parse_tg_message(message)
                    if not all_present:
                        print(f"[DEBUG] Parse error: {parsed_msg}")
                        continue

                    symbol = parsed_msg.get("symbol")
                    cap = parsed_msg.get("cap")
                    if self.base_symbol and symbol != self.base_symbol:
                        continue

                    debug_label = f"{symbol}_{self.direction}"
                    diff_sec = time.time() - (last_timestamp / 1000)
                    # print(f"[DEBUG] {debug_label} diff sec: {diff_sec:.2f}")

                    if diff_sec < SIGNAL_TIMEOUT:
                        for num, (chat_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
                            if num > 1:
                                continue
                            asyncio.create_task(
                                self.handle_signal(
                                    chat_id=chat_id,
                                    symbol=symbol,
                                    cap=cap,
                                    last_timestamp=last_timestamp,
                                    debug_label=debug_label
                                )
                            )

            except Exception as e:
                err_msg = f"[ERROR] main loop: {e}\n" + traceback.format_exc()
                self.info_handler.debug_error_notes(err_msg, is_print=True)

            finally:
                try:
                    for num, (chat_id, user_cfg) in enumerate(self.context.users_configs.items(), start=1):
                        if num > 1:
                            continue
                        await self.notifier.send_report_batches(chat_id=chat_id, batch_size=1)
                except Exception as e:
                    err_msg = f"[ERROR] main finally block: {e}\n" + traceback.format_exc()
                    self.info_handler.debug_error_notes(err_msg, is_print=True)

                await asyncio.sleep(MAIN_CYCLE_FREQUENCY)


    async def run_forever(self, debug: bool = False):
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

        while not self.context.stop_bot:
            if debug: print("[CORE] Новый цикл run_forever, обнуляем флаги итерации")
            self.context.start_bot_iteration = False
            self.context.stop_bot_iteration = False

            # ждём нажатия кнопки START
            if debug: print("[CORE] Ожидание кнопки START...")
            while not self.context.start_bot_iteration and not self.context.stop_bot:
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
                await self._shutdown_iteration(debug=debug)
                if debug: print("[CORE] Очистка ресурсов завершена")
            except Exception as e:
                self.info_handler.debug_error_notes(f"[CORE] Ошибка при shutdown итерации: {e}", is_print=True)

            # если была локальная остановка — ждём нового START
            if self.context.stop_bot_iteration:
                self.info_handler.debug_info_notes("[CORE] Перезапуск по кнопке STOP", is_print=True)
                if debug: print("[CORE] Ожидание следующего START после STOP")
                continue

        if debug: print("[CORE] run_forever finished")

    async def _shutdown_iteration(self, debug: bool = True):
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
        if getattr(self, "order_stream", None):
            try:
                await asyncio.wait_for(self.order_stream.disconnect(), timeout=5)
            except Exception as e:
                if debug:
                    print(f"[CORE] order_stream.disconnect() error: {e}")
            finally:
                self.order_stream = None

        # --- Connector ---
        if getattr(self, "connector", None):
            try:
                await asyncio.wait_for(self.connector.shutdown_session(), timeout=5)
            except Exception as e:
                if debug:
                    print(f"[CORE] connector.shutdown_session() error: {e}")
            finally:
                self.context.session = None
                self.connector = None

        for key, task in list(self.tp_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tp_tasks.clear()

        # --- Сброс прочих ссылок ---
        self.mx_client = None
        self.sync = None
        self.tp_control = None
        self.utils = None
        self.pos_setup = None
        self.entry = None
        self.exit = None

        self.context.position_vars = {}

        # if debug:
        #     print("[CORE] Iteration shutdown complete")

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