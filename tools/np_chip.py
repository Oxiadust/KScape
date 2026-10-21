"""The now-playing chip the view generators add: kept in the add-on (resources/lib/npchip.py),
which also builds the cover wall's XML at run time. Re-exported here for the generators."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'script.kscape.wall'))
from resources.lib import npchip  # noqa: E402

chip = npchip.chip
count_chip = npchip.count_chip
