

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