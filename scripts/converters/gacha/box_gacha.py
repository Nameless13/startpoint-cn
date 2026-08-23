import os
from . import box_total_counts

def convert_box_gacha(obj):
    converted = {}
    for gacha_id, gacha in obj.items():
        gacha = gacha[0]  # extract inner array
        converted[gacha_id] = {
            "itemId": int(gacha[2]),
            "count": int(gacha[3]),
            "availableCounts": box_total_counts.get(str(gacha_id), {})
        }
    return converted


