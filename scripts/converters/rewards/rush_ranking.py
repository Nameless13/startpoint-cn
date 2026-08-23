def convert_rush_event_ranking_reward(obj):
    """CDN format: event_id → rank_group_id → [[from_rank, to_rank, ?, kind, kind_id, number], ...]"""
    converted = {}
    for event_id, groups in obj.items():
        converted_groups = {}
        for group_id, entries in groups.items():
            rewards = []
            for entry in entries:
                rewards.append({
                    "fromRank": int(entry[0]),
                    "toRank": int(entry[1]),
                    "kind": int(entry[3]) if len(entry) > 3 else 1,
                    "kindId": int(entry[4]) if len(entry) > 4 else 0,
                    "number": int(entry[5]) if len(entry) > 5 else 0
                })
            converted_groups[group_id] = rewards
        converted[event_id] = converted_groups
    return converted
