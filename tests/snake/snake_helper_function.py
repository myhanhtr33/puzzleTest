def get_color_name(color_int: int) -> str:
    color_map = {
        -1: "None",
        0: "Red",
        1: "Orange",
        2: "Yellow",
        3: "Lime",
        4: "Green",
        5: "Sky",
        6: "Blue",
        7: "Violet",
        8: "Pink",
        9: "Copper",
        10: "Snow",
        11: "Onyx",
        12: "Red_Sub",
        13: "Orange_Sub",
        14: "Yellow_Sub",
        15: "Lime_Sub",
        16: "Green_Sub",
        17: "Sky_Sub",
        18: "Blue_Sub",
        19: "Violet_Sub",
        20: "Purple_Sub",
        21: "Copper_Sub",
        22: "Snow_Sub",
        23: "Onyx_Sub"
    }
    return color_map.get(color_int, f"Unknown({color_int})")
from typing import Literal

VALID_DATA_TYPES = ["gold", "magnet", "pole", "broom", "magicWand", "level", "levelPlayTimes", "box"]

def get_user_data(
    data_type: Literal["gold", "magnet", "pole", "broom", "magicWand", "level", "levelPlayTimes", "box"],
    poco
):
    """
    Retrieve a specific field from the user data.

    :param data_type: The field to retrieve. Must be one of:
        "gold", "magnet", "pole", "broom", "magicWand", "level", "levelPlayTimes", "box"
    :param poco: The poco instance used to invoke the remote call.
    :return: The value of the requested field, or None if unavailable.
    """
    if data_type not in VALID_DATA_TYPES:
        raise ValueError(f"Invalid data_type '{data_type}'. Must be one of: {VALID_DATA_TYPES}")
    result = poco.invoke("get_user_data")
    data = result.get("userData")
    return data.get(data_type) if data else None

VALID_ADD_DATA_TYPES=["gold", "magnet", "pole", "broom", "magicWand", "box"]
def add_user_data(
    data_type: Literal["gold", "magnet", "pole", "broom", "magicWand", "box"],
    amount: int,
    poco
):
    """
    Add a specific amount to a field in the user data.

    :param data_type: The field to modify. Must be one of:
        "gold", "magnet", "pole", "broom", "magicWand", "box"
    :param amount: The amount to add to the specified field.
    :param poco: The poco instance used to invoke the remote call. Required if data_type is valid.
    """
    if data_type not in VALID_ADD_DATA_TYPES:
        raise ValueError(f"Invalid data_type '{data_type}'. Must be one of: {VALID_ADD_DATA_TYPES}")
    result = poco.invoke("add_resource", resourceId=data_type, amount=amount)
    return result

