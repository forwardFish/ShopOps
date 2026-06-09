from shopops.storage.feishu_bitable import FeishuBitableStorage, FeishuEnvironmentError
from shopops.storage.local_feishu import LocalFeishuBitableStorage


def create_storage(settings):
    if settings.storage_backend == "feishu":
        return FeishuBitableStorage(settings)
    return LocalFeishuBitableStorage(settings)


__all__ = ["FeishuBitableStorage", "FeishuEnvironmentError", "LocalFeishuBitableStorage", "create_storage"]
