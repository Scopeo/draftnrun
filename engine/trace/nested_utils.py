import re


def split_key(key: str) -> list:
    parts = key.split(".")
    result = []
    for part in parts:
        if re.fullmatch(r"\d+", part):
            result.append(int(part))
        else:
            result.append(part)
    return result


def ensure_list_size(lst: list, index: int, fill_value=None):
    if index >= len(lst):
        lst.extend([fill_value] * (index + 1 - len(lst)))


def insert_nested(nested, keys, value):
    current = nested
    for i, key in enumerate(keys[:-1]):
        next_key = keys[i + 1]

        if isinstance(key, int):
            ensure_list_size(current, key)
            if current[key] is None:
                current[key] = [] if isinstance(next_key, int) else {}
            current = current[key]
        else:
            if key not in current or not isinstance(current[key], (dict, list)):
                current[key] = [] if isinstance(next_key, int) else {}
            current = current[key]

    # Final key
    last_key = keys[-1]
    if isinstance(last_key, int):
        ensure_list_size(current, last_key)
        current[last_key] = value
    else:
        current[last_key] = value


def split_nested_keys(flat_dict: dict) -> dict:
    nested = {}
    for compound_key, value in flat_dict.items():
        keys = split_key(compound_key)
        insert_nested(nested, keys, value)
    return nested
