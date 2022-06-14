import os
import json

def config_json() -> str:
    folder = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(folder, 'config.json'), 'r') as f:
        return json.load(f)