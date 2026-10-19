from . import models
from . import wizard
from . import report


def post_init_hook(env):
    from .translation_repair import repair_es_ar_translations

    repair_es_ar_translations(env.cr)
