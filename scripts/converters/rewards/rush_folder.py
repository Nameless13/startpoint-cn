def convert_rush_event_quest_folder(obj):
    converted = {}
    for rush_event_id, folders in obj.items():
        converted_folders = {}
        for folder_id, folder in folders.items():
            folder = folder[0]  # extract inner array
            rewards = []
            reward_offset = 7
            for _ in range (10):
                if folder[reward_offset] != "(None)":
                    reward = {
                        "type": int(folder[reward_offset])
                    }
                    if folder[reward_offset + 1] != "":
                        reward['id'] = int(folder[reward_offset + 1])
                    if folder[reward_offset + 2] != "":
                        reward['count'] = int(folder[reward_offset + 2])
                    rewards.append(reward)
                reward_offset += 3

            converted_folders[folder_id] = rewards

        converted[rush_event_id] = converted_folders
    return converted


