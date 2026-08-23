def convert_score_reward(obj):
    converted = {}
    # type map
    # 0 = item, 1 = rare score group + id
    for group_id, score_group in obj.items():
        converted_group = []
        for position, reward in score_group.items():
            type = int(reward[1])
            if type == 0:
                converted_reward = {
                    "name": "", #reward[0],
                    "position": int(position),
                    "type": type,
                    "reward_type": int(reward[2]),
                    "count": int(reward[4]),
                    "field5": int(reward[5]),
                }
                if reward[3] != "":
                    converted_reward["id"] = int(reward[3])

                converted_group.append(converted_reward)
            elif type == 1:
                converted_group.append({
                    "name": "", #reward[0],
                    "position": int(position),
                    "type": type,
                    "id": int(reward[6]),
                    "rarity": float(reward[7])
                })
        converted[group_id] = converted_group
    return converted


