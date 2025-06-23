"""abstract_view_mpl.py
PZero© Andrea Bistacchi"""

# PZero imports____
from .abstract_base_view import BaseView


class ViewMPL(BaseView):
    """Abstract class used as a base for all classes using the Matplotlib plotting canvas."""

    def __init__(self, *args, **kwargs):
        """Incrementally initialize the ViewMPL intermediate-level class."""

        # Initialize dictionary to store reference to actors in the Matplotlib plot, with key = uid
        self.mpl_actors = dict()

        super(ViewMPL, self).__init__(*args, **kwargs)
