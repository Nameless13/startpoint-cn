# Shared utilities for converter scripts.
import json
import os

FILE_OUTPUT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "out")
FILE_INPUT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "in")

def parse_file(file_name):
    if file_name.endswith(".json") and os.path.exists(file_name):
        with open(file_name, "r", encoding='utf8') as file:
            return json.load(file)
    return None

def save_json(obj, file_path):
    with open(file_path, 'w', encoding='utf8') as file:
        json.dump(obj, file, indent=4, ensure_ascii=False)
