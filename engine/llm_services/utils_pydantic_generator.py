from typing import Union, get_args, get_origin

from pydantic import BaseModel


def build_generic_pydantic_instance_from_pydantic_model(model_cls: type[BaseModel]) -> BaseModel:
    def _fake_value(field_type):
        origin = get_origin(field_type) or field_type
        args = get_args(field_type)

        # Simple types
        if origin is bool:
            return False
        elif origin is int:
            return 0
        elif origin is float:
            return 0.0
        elif origin is str:
            return "string"
        elif origin is list:
            # for list[T], generate one element of T
            inner_type = args[0] if args else str
            return [_fake_value(inner_type)]
        elif origin is dict:
            # for dict[K, V], generate one key-value pair with proper types
            # Use "key" as a consistent key for all dictionaries
            value_type = args[1] if len(args) > 1 else str
            return {"key": _fake_value(value_type)}
        elif origin is Union:
            # handle Optional[X] (Union[X, None])
            non_none_args = [arg for arg in args if arg is not type(None)]
            return _fake_value(non_none_args[0]) if non_none_args else None
        elif issubclass(origin, BaseModel):
            # nested model
            return build_generic_pydantic_instance_from_pydantic_model(origin)
        else:
            return None

    # build data dict
    data = {name: _fake_value(field.annotation) for name, field in model_cls.model_fields.items()}

    return model_cls(**data)
