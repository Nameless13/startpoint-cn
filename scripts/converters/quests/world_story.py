import field_map as f
import quest_builder as qb

def convert_world_story_event_quest(obj):
    return qb.convert_3level_with_story(obj, f.TYPE_MAP['world_story_event_quest']['layout'])



def convert_world_story_event_boss_battle_quest(obj):
    return qb.convert_3level(obj, f.TYPE_MAP['world_story_event_boss_battle_quest']['layout'], hardcode_s_plus=True)


