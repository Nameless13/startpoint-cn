import json
import os

def convert_gacha_rarities(path):
    converted = []
    with open(path, "r") as file:
        obj = json.load(file)
        total_odds = 0
        for rarity_entry in list(obj.values())[0].values():
            odds = int(rarity_entry[2])
            converted.append({
                "id": int(rarity_entry[0]),
                "rank": int(rarity_entry[1]),
                "odds": odds,
                "isRateUp": True if rarity_entry[3] == 'true' else False
            })
            total_odds += odds

        # calculate rarities
        for converted_rarity in converted:
            converted_rarity["rarity"] = round((converted_rarity["odds"] / total_odds) * 1000, 2)

    return converted


