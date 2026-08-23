def convert_ex_ability(obj):
    converted = {
        1: [], # 3*
        2: [], # 4*
        3: []  # 5*
    }
    for ability_id, status in obj.items():
        tier = int(status[2]) - 2

        converted[tier].append(int(ability_id))
    return converted

