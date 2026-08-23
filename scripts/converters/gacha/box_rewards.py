import os
from . import box_total_counts

def convert_box_rewards(obj):
    converted = {}
    for gacha_id, boxes in obj.items():
        converted_gacha = {}
        box_total_counts[str(gacha_id)] = {}
        for box_id, box in boxes.items():
            converted_box = {}
            box_total_counts[str(gacha_id)][str(box_id)] = 0
            for _, reward in box.items():
                reward = reward[0]  # extract inner array
                converted_reward = {
                    "type": int(reward[2]),
                    "count": int(reward[4]),
                    "available": int(reward[5]),
                    "tier": int(reward[6])
                }
                box_total_counts[str(gacha_id)][str(box_id)] += converted_reward["available"]
                if reward[3] != "":
                    converted_reward["id"] = int(reward[3])
                
                converted_box[reward[0]] = converted_reward
            converted_gacha[box_id] = converted_box
        converted[gacha_id] = converted_gacha
    return converted


