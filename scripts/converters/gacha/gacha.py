import os
import util
from .rarities import convert_gacha_rarities

def convert_gacha(obj):
    converted = {}
    for gacha_id, gacha_data in obj.items():
        payment_type = int(gacha_data[4])

        # 0 = character; 1 = weapon
        gacha_type = int(gacha_data[13])
        if payment_type == 0:
            single_cost = int(gacha_data[5])
            multi_cost = int(gacha_data[6])
            discount_single_cost = int(gacha_data[7])

            if gacha_type == 0:
                converted_gacha = {
                    "type": gacha_type,
                    "paymentType": payment_type,
                    "singleCost": single_cost,
                    "multiCost": multi_cost,
                    "discountCost": discount_single_cost,
                    "movieName": gacha_data[17],
                    "guaranteeMovieName": gacha_data[18],
                    "startDate": gacha_data[29],
                    "endDate": gacha_data[30]
                }
                converted_gacha["pool"] = {
                    "3": convert_gacha_rarities(os.path.join(util.FILE_INPUT, "gacha_odds", f"{gacha_data[14]}.json")),
                    "2": convert_gacha_rarities(os.path.join(util.FILE_INPUT, "gacha_odds", f"{gacha_data[15]}.json")),
                    "1": convert_gacha_rarities(os.path.join(util.FILE_INPUT, "gacha_odds", f"{gacha_data[16]}.json")),
                }
                converted[gacha_id] = converted_gacha 

            elif gacha_type == 1:
                converted_gacha = {
                    "type": gacha_type,
                    "paymentType": payment_type,
                    "singleCost": single_cost,
                    "multiCost": multi_cost,
                    "discountCost": discount_single_cost,
                    "startDate": gacha_data[29],
                    "endDate": gacha_data[30]
                }
                converted_gacha["pool"] = {
                    "3": convert_gacha_rarities(os.path.join(util.FILE_INPUT, "gacha_odds", f"{gacha_data[22]}.json")),
                    "2": convert_gacha_rarities(os.path.join(util.FILE_INPUT, "gacha_odds", f"{gacha_data[23]}.json")),
                    "1": convert_gacha_rarities(os.path.join(util.FILE_INPUT, "gacha_odds", f"{gacha_data[24]}.json")),
                }
                converted[gacha_id] = converted_gacha
    
    return converted
