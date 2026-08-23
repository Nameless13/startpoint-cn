import field_map as f
import quest_builder as qb

def convert_main_ex_quests(obj):
    return qb.convert_4level_with_story(obj, f.TYPE_MAP['main_quest']['layout'])

def convert_boss_quests(obj):
    return qb.convert_4level_with_story(obj, f.TYPE_MAP['boss_battle_quest']['layout'], story_clear_reward=3)
