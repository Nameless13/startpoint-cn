import field_map as f
import quest_builder as qb

def convert_advent_quest(obj):
    return qb.convert_3level_with_story(obj, f.TYPE_MAP['advent_event_quest']['layout'])


