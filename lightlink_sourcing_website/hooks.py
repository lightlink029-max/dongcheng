from .models.content_translations import apply_sourcing_translations


def post_init_hook(env):
    env["website"].initialize_lightlink_sourcing_site()
    env["website"]._cleanup_lightlink_sourcing_bootstrap_menus()
    env["website"].sync_lightlink_sourcing_mirror()
    env["website"].seed_lightlink_sourcing_catalog()
    apply_sourcing_translations(env)
