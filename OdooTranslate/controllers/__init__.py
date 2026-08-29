# -*- coding: utf-8 -*-
from . import odoo_translate_controller

# Import conditionnel pour le controller website (sync langue visiteur)
try:
    from . import website
except ImportError:
    pass
