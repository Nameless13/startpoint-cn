import os
from util import save_json
import util

def convert_treasure_shop(obj):
    converted = {}
    for item_id, item in obj.items():
        costs = []
        cost_offset = 10
        for _ in range(4):
            if item[cost_offset] != "(None)":
                costs.append({
                    "id": int(item[cost_offset]),
                    "amount": int(item[cost_offset + 1])
                })
            cost_offset += 2

        rewards = []
        reward_offset = 24
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

        converted_item = {
            "costs": costs,
            "rewards": rewards,
            "availableFrom": item[18],
            "availableUntil": item[19] if item[19] != "(None)" else None,
            "stock": int(item[21]),
        }

        if (item[7]) != "(None)":
            converted_item['userCost'] = {
                "type": int(item[7]),
                "amount": int(item[8])
            }

        converted[item_id] = converted_item

    return converted


