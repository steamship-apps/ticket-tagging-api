import os
import json
from typing import Dict


def config_json() -> Dict:
    folder = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(folder, 'config.json'), 'r') as f:
        return json.load(f)