import os
from util import save_json
import util

def convert_equipment_enhancement_shop(obj):
    converted = {}
    for item_id, item in obj.items():
        # value is [[cols]], extract the inner array
        item = item[0]
        costs = []
        cost_offset = 14
        for _ in range(4):
            if item[cost_offset] != "(None)" and item[cost_offset] != "":
                costs.append({
                    "id": int(item[cost_offset]),
                    "amount": int(item[cost_offset + 1])
                })
            cost_offset += 2

        rewards = []
        # EquipmentEnhancementKind.Normal (product_kind=0) has reward kinds at [32]-[49]
        if item[4] == "0":
            reward_offset = 32
            for _ in range(6):
                if item[reward_offset] != "(None)" and item[reward_offset] != "":
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
            "availableFrom": item[22],
            "availableUntil": item[23] if item[23] != "(None)" else None,
            "stock": int(item[25]) if item[25] != "" else -1,
            "shopCategoryId": int(item[0]),
            "groupId": int(item[2]),
            "stage": int(item[3]),
        }

        # EquipmentEnhancement kind fields
        if item[29] != "":
            converted_item["equipmentId"] = int(item[29])
        if item[30] != "":
            converted_item["enhancementMaxLevel"] = int(item[30])
        if item[31] != "":
            converted_item["requireAwakeningLevel"] = int(item[31])
        if item[26] != "" and item[26] != "(None)":
            converted_item["maxFrequency"] = int(item[26])
        if item[27] != "" and item[27] != "(None)":
            converted_item["dailyStock"] = int(item[27])
        if item[28] != "" and item[28] != "(None)":
            converted_item["monthlyStock"] = int(item[28])

        if item[11] != "(None)" and item[11] != "":
            converted_item['userCost'] = {
                "type": int(item[11]),
                "amount": int(item[12])
            }

        converted[item_id] = converted_item

    return converted


