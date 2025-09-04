

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