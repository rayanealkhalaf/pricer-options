"""Configuration pytest commune."""

import pytest


@pytest.fixture(params=["pcg64", "mrg32k3a"])
def generateur(request):
    """Chaque test Monte-Carlo paramétré tourne avec les deux générateurs."""
    return request.param
