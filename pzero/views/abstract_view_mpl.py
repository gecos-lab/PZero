"""abstract_view_mpl.py
PZero© Andrea Bistacchi"""

# PZero imports____
from .abstract_base_view import BaseView


class ViewMPL(BaseView):
    """Abstract class used as a base for all classes using the Matplotlib plotting canvas."""

    def __init__(self, *args, **kwargs):
        super(ViewMPL, self).__init__(*args, **kwargs)
