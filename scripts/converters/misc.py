def convert_encyclopedia(obj):
    converted = {}
    for _, entries in obj.items():
        for _, item in entries.items():
            converted[int(item[0])] = {
                "read": True
            }
    return converted

