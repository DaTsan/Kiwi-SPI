def capture_execution(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        from .services import snapshot_execution

        snapshot_execution(instance)
