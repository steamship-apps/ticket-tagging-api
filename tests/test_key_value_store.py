import json
from steamship import Steamship

import os
from typing import List

__copyright__ = "Steamship"
__license__ = "MIT"

from src.api import KeyValueStore


def test_key_value_store():
    """We can test the app like a regular python object!"""
    client = Steamship()
    kv = KeyValueStore(client=client)
    kv.reset()

    # Getting empty key is None
    assert kv.get("FOO") == None

    KEY_1 = "FOO"
    KEY_2 = "BAR"

    # Set then Get
    value = {"a": 3}
    value_2 = dict(hi="there", b=5)
    value_3 = dict(j=9)

    # Set and get
    kv.set(KEY_1, value)
    assert kv.get(KEY_1) == value

    # Get again
    assert kv.get(KEY_1) == value

    # Make a new one
    kv.set(KEY_2, value_2)
    assert kv.get(KEY_2) == value_2
    assert kv.get(KEY_2) != value

    # Overwite the new one
    kv.set(KEY_2, value_3)
    got = kv.get(KEY_2)
    got_2 = kv.get(KEY_2)
    got_3 = kv.get(KEY_2)

    assert got == value_3
    assert got != value_2
    assert got != value
    assert got == got_2
    assert got == got_3

    # Delete a key
    kv.delete(KEY_1)
    assert kv.get(KEY_1) is None

    # But still others
    assert kv.get(KEY_2) == value_3

    # Delete all
    kv.reset()
    assert kv.get(KEY_2) is None




