def convert_mana_nodes(obj):
    converted = {}
    for characterId, data in obj.items():
        levels = {}
        for level, nodes in data.items():
            mana_nodes = {}
            for _, node in nodes.items():
                item_list = {}
                item_costs = node[3].split(",")
                
                for n, item_id in enumerate(node[2].split(",")):
                    item_list[item_id.strip()] = int(item_costs[n].strip())

                mana_nodes[node[0]] = {
                    "items": item_list,
                    "manaCost": int(node[4]),
                    "field1": node[1],
                    "field5": node[5],
                    "field6": node[6]
                }
            levels[level] = mana_nodes
        converted[characterId] = levels
    return converted


