from .models.content_translations import apply_sourcing_translations


def post_init_hook(env):
    env["website"].initialize_lightlink_sourcing_site()
    env["website"]._cleanup_lightlink_sourcing_bootstrap_menus()
    apply_sourcing_translations(env)
