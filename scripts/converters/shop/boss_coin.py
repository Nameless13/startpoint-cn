import os
from util import save_json
import util

def convert_boss_coin_shop(obj):
    converted = {}
    map_output = {}
    for item_id, item in obj.items():
        costs = []
        cost_offset = 16
        for _ in range(4):
            if item[cost_offset] != "(None)":
                costs.append({
                    "id": int(item[cost_offset]),
                    "amount": int(item[cost_offset + 1])
                })
            cost_offset += 2

        rewards = []
        reward_offset = 31
        for _ in range (6):
            if item[reward_offset] != "(None)":
                reward = {
                    "type": int(item[reward_offset])
                }
                if item[reward_offset + 1] != "":
                    reward['id'] = int(item[reward_offset + 1])
                if item[reward_offset + 2] != "":
                    reward['count'] = int(item[reward_offset + 2])
                rewards.append(reward)
            reward_offset += 3
        
        category = int(item[0])

        converted_item = {
            "costs": costs,
            "rewards": rewards,
            "availableFrom": item[24],
            "availableUntil": item[25] if item[25] != "(None)" else None,
            "stock": int(item[27]),
        }
        
        if not converted.get(category):
            converted[category] = {}

        map_output[item_id] = category
        converted[category][item_id] = converted_item
        
    save_json(map_output, os.path.join(util.FILE_OUTPUT, "boss_coin_shop_item_category_map.json"))
    return converted


