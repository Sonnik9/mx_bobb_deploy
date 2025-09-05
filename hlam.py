

# def format_config(cfg: dict, indent: int = 0) -> str:
#     lines = []
#     pad = "  " * indent
#     for k, v in cfg.items():
#         if isinstance(v, dict):
#             lines.append(f"{pad}• {k}:")
#             lines.append(format_config(v, indent + 1))
#         else:
#             lines.append(f"{pad}• {k}: {v}")
#     return "\n".join(lines)




    # @staticmethod
    # def parse_precision(symbols_info: dict, symbol: str) -> dict | None:
    #     """
    #     Возвращает настройки для qty и price в виде словаря:
    #     {
    #         "contract_precision": int,
    #         "price_precision": int,
    #         "contract_size": float,
    #         "price_unit": float,
    #         "vol_unit": float
    #     }
    #     Если символ не найден или данные пустые → None.
    #     """
    #     # if not symbols_info or "data" not in symbols_info:
    #     #     return None

    #     symbol_data = next((item for item in symbols_info if item.get("symbol") == symbol), None)
    #     if not symbol_data:
    #         return None

    #     return {
    #         "contract_precision": symbol_data.get("volScale", 3),
    #         "price_precision": symbol_data.get("priceScale", 2),
    #         "contract_size": float(symbol_data.get("contractSize", 1)),
    #         "price_unit": float(symbol_data.get("priceUnit", 0.01)),
    #         "vol_unit": float(symbol_data.get("volUnit", 1))
    #     }


# [{'positionId': 1020019273, 'symbol': 'AERO_USDT', 'positionType': 1, 'openType': 2, 'state': 3, 'holdVol': 0, 'frozenVol': 0, 'closeVol': 11, 'holdAvgPrice': 1.1881, 'holdAvgPriceFullyScale': '1.1881', 'openAvgPrice': 1.1881, 'openAvgPriceFullyScale': '1.1881', 'closeAvgPrice': 1.1883, 'liquidatePrice': 0.9947, 'oim': 0, 'im': 0, 'holdFee': 0, 'realised': -0.0825, 'leverage': 16, 'createTime': 1757072694000, 'updateTime': 1757072708000, 'autoAddIm': False, 'version': 8, 'profitRatio': -0.01, 'newOpenAvgPrice': 1.1881, 'newCloseAvgPrice': 1.1883, 'closeProfitLoss': 0.022, 'fee': -0.1045, 'positionShowStatus': 'CLOSED', 'deductFeeList': [], 'totalFee': 0.1045, 'zeroSaveTotalFeeBinance': 0, 'zeroTradeTotalFeeBinance': 0.1045}, {'positionId': 1020013260, 'symbol': 'AERO_USDT', 'positionType': 1, 'openType': 2, 'state': 3, 'holdVol': 0, 'frozenVol': 0, 'closeVol': 9, 'holdAvgPrice': 1.1934, 'holdAvgPriceFullyScale': '1.1934', 'openAvgPrice': 1.1934, 'openAvgPriceFullyScale': '1.1934', 'closeAvgPrice': 1.1914, 'liquidatePrice': 0.9526, 'oim': 0, 'im': 0, 'holdFee': 0, 'realised': -0.2658, 'leverage': 16, 'createTime': 1757072228000, 'updateTime': 1757072304000, 'autoAddIm': False, 'version': 8, 'profitRatio': -0.0393, 'newOpenAvgPrice': 1.1934, 'newCloseAvgPrice': 1.1914, 'closeProfitLoss': -0.18, 'fee': -0.0858, 'positionShowStatus': 'CLOSED', 'deductFeeList': [], 'totalFee': 0.0858, 'zeroSaveTotalFeeBinance': 0, 'zeroTradeTotalFeeBinance': 0.0858}], message=None)
# ♻️ Cleaning up iteration







    # async def pnl_report(
    #         self,
    #         symbol: str,
    #         pos_side: str,
    #         pos_data: dict,
    #         cur_price: float,
    #         label: str
    #     ):
    #     if cur_price is None:
    #         print(f"[REPORT][ERROR][{label}]: cur_price is None")
    #         return

    #     # sign = 1 для LONG, -1 для SHORT
    #     sign = {"LONG": 1, "SHORT": -1}.get(pos_side.upper())
    #     if sign is None:
    #         print(f"[REPORT][ERROR][{label}]:sign is None")
    #         return  

    #     entry_price = pos_data.get("entry_price")        
    #     if not entry_price:
    #         print(f"[REPORT][ERROR][{label}]:not entry_price or invest_usd")
    #         return

    #     # Корректируем цену с учётом проскальзывания
    #     cur_price_with_slippage = apply_slippage(
    #         price=cur_price,
    #         slippage_pct=SLIPPAGE_PCT,
    #         pos_side=pos_side
    #     )

    #     # % PnL
    #     pnl_pct = (cur_price_with_slippage - entry_price) / entry_price * 100 * sign

    #     # $ PnL
    #     qty = pos_data.get("vol_assets")  # кол-во монет в позиции
    #     pnl_usdt = qty * (cur_price_with_slippage - entry_price) * sign
    #     # ///

    #     time_in_deal = None
    #     cur_time = int(time.time() * 1000)
    #     if pos_data.get("c_time"):
    #         time_in_deal = cur_time - pos_data.get("c_time")

    #     leverage = pos_data.get("leverage", 1)

    #     body = {
    #         "symbol": symbol,
    #         # "pos_side": pos_side,
    #         "pnl_pct": pnl_pct * leverage,
    #         "pnl_usdt": pnl_usdt,
    #         "cur_time": cur_time,
    #         "time_in_deal": format_duration(time_in_deal)
    #     }
    
    #     self.preform_message(
    #         chat_id=self.chat_id,
    #         marker="report",
    #         body=body,
    #         is_print=True
    #     )


# import time 

# print(((time.time()* 1000) - 1757086745000)/1000)



# import asyncio

# async def main():
#     instance = MexcFuturesAPI("WEB242b9e58e0e4f2d55f184870de2a16a520bf1d3969a7240c821b19d308abf91b")
#     try:
#         # ставим таймаут на работу, чтобы любой зависший таск не блокировал forever
#         r = await asyncio.wait_for(instance.get_futures_statement(symbol="AERO_USDT", direction=2, page_size=2), timeout=None)
#         print(r)
#     except asyncio.CancelledError:
#         print("🚨 CancelledError caught")
#     finally:
#         print("♻️ Cleaning up iteration")


# if __name__ == "__main__":
#     # жёсткое убийство через Ctrl+C / kill
#     try:
#         asyncio.run(main())
#     except (KeyboardInterrupt, SystemExit):
#         print("💥 Force exit")

# # python -m API.MX.mx_bypass.api
