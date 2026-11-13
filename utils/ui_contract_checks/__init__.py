"""Built-in UI contract checkers, grouped by the UI property they inspect."""

from .interaction import CHECKERS as INTERACTION_CHECKERS
from .hierarchy import CHECKERS as HIERARCHY_CHECKERS
from .text import CHECKERS as TEXT_CHECKERS
from .texture import CHECKERS as TEXTURE_CHECKERS

DEFAULT_CHECKERS = {
    **TEXTURE_CHECKERS,
    **INTERACTION_CHECKERS,
    **HIERARCHY_CHECKERS,
    **TEXT_CHECKERS,
}
