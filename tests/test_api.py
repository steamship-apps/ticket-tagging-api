import json
from steamship import Steamship

import os
from typing import List

__copyright__ = "Steamship"
__license__ = "MIT"

from src.api import TicketTaggingApp


def test_tag_ticket():
    """We can test the app like a regular python object!"""
    client = Steamship()
    app = TicketTaggingApp(client, config={'save_classifications':True})

    assert app.set_labels(['mouse','tiger','elephant']).data == "Labels accepted"

    result = app.tag_ticket('I really enjoy seeing large animals in the wild, especially cats and animals with tusks.')
    result.data


def test_specialize():
    """We can test the app like a regular python object!"""
    client = Steamship()
    app = TicketTaggingApp(client)

    assert app.set_labels(['mouse','tiger','elephant']).data == "Labels accepted"

    result = app.start_specialize()
    result.data