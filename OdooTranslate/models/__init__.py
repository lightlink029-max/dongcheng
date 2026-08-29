from . import field_config
from . import chat_translation_notification_router
from . import dynamic_translation
from . import translation_patch
from . import translation_source_inspector
from . import rule_identity
from . import base_automation
from . import auth_mail_policy
from . import mail_template
from . import mail_mail
from . import res_users
from . import ir_actions_server
from . import ir_http
from . import odoo_translate_config
from . import module_api_operation
from . import native_text_operation
from . import native_text_gateway

# Applique les patchs au chargement du module (une seule fois par worker)
translation_patch.apply_basemodel_patch()
ir_http.apply_sidebar_patch()
