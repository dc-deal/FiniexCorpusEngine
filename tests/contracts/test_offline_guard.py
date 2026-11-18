"""The offline guard itself: a connection that leaves the machine fails the test."""

import socket

import pytest


def test_a_connection_to_the_internet_is_refused_in_an_offline_test():
    with pytest.raises(RuntimeError, match='network access in an offline test'):
        socket.create_connection(('openrouter.ai', 443), timeout=1)
