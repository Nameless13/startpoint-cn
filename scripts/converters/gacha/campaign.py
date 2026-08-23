def convert_gacha_campaigns(obj):
    campaign_map = {}
    for campaign_id, data in obj.items():
        campaign_id = int(campaign_id)
        for gacha_id in data[5].split(","):
            campaign_map[gacha_id] = campaign_id
    return campaign_map
