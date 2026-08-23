def convert_ex_status(obj):
    converted = {
        1: [], # 3*
        2: [], # 4*
        3: []  # 5*
    }
    for status_id, status in obj.items():
        tier = int(status[3]) - 2

        converted[tier].append(int(status_id))
    return converted


