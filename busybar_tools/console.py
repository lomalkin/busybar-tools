import json
import logging


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if any(getattr(handler, "_busybar_handler", False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler._busybar_handler = True
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


def print_pretty(data, return_instead_of_print=False):
    if isinstance(data, (dict, list)):
        rendered = json.dumps(data, indent=4)
    else:
        try:
            rendered = json.dumps(json.loads(data), indent=4)
        except (json.JSONDecodeError, TypeError):
            rendered = data
    if return_instead_of_print:
        return rendered
    print(rendered)

