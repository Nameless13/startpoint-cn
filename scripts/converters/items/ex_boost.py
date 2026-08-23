def convert_ex_boost(obj):
    converted = {}
    for item_id, ex_boost_item in obj.items():
        name = ex_boost_item[1]
        new =  {
            "tier": 3 if name.endswith("r5") else 2 if name.endswith("r4") else 1,
            "count": int(ex_boost_item[0])
        }
        if len(ex_boost_item[2]) == 1:
            new['element'] = int(ex_boost_item[2])
        converted[item_id] = new
    return converted


