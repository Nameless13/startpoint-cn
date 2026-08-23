import os
from util import save_json
import util

def convert_event_item_shop(obj):
    converted = {}

    map_output = {}
    
    for item_id, item in obj.items():
        item = item[0]  # extract inner array
        costs = []
        cost_offset = 18
        for _ in range(4):
            if item[cost_offset] != "(None)":
                costs.append({
                    "id": int(item[cost_offset]),
                    "amount": int(item[cost_offset + 1])
                })
            cost_offset += 2

        rewards = []
        reward_offset = 32
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
        
        event_type = int(item[2])
        event_id = int(item[1])

        converted_item = {
            "costs": costs,
            "rewards": rewards,
            "availableFrom": item[26],
            "availableUntil": item[27] if item[27] != "(None)" else None,
            "stock": int(item[29]),
        }
        
        if not converted.get(event_type):
            converted[event_type] = {}

        if not converted[event_type].get(event_id):
            converted[event_type][event_id] = {}

        map_output[item_id] = {
            "eventType": event_type,
            "eventId": event_id
        }

        converted[event_type][event_id][item_id] = converted_item

    save_json(map_output, os.path.join(util.FILE_OUTPUT, "event_item_shop_id_map.json"))
    return converted


