from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RobotTask:
    key: str
    platform: str
    platform_code: str
    profile: str
    kind: str
    url: str
    slug: str
    default_timeout_seconds: int = 900


TASKS: dict[str, RobotTask] = {
    "pinduoduo_orders": RobotTask(
        key="pinduoduo_orders",
        platform="拼多多",
        platform_code="pinduoduo",
        profile="pinduoduo",
        kind="orders",
        slug="orders",
        url="https://mms.pinduoduo.com/orders/list?tab=0",
    ),
    "pinduoduo_ads": RobotTask(
        key="pinduoduo_ads",
        platform="拼多多",
        platform_code="pinduoduo",
        profile="pinduoduo",
        kind="ads",
        slug="ads",
        url="https://yingxiao.pinduoduo.com/goods/report/promotion/overView",
    ),
    "wechat_channels_orders": RobotTask(
        key="wechat_channels_orders",
        platform="视频号",
        platform_code="wechat_channels",
        profile="wechat_channels",
        kind="orders",
        slug="orders",
        url="https://store.weixin.qq.com/shop/order/list",
    ),
    "douyin_ads": RobotTask(
        key="douyin_ads",
        platform="抖音",
        platform_code="douyin",
        profile="douyin",
        kind="ads",
        slug="ads",
        url=(
            "https://qianchuan.jinritemai.com/dataV2/bidding/site-promotion?"
            "aavid=1860240208332803&btm_ppre=a2427.b0.c0.d0&btm_pre=a2427.b76571.c4158.d397407_i2"
            "&btm_show_id=7a09e2f5-a01a-4241-a5ed-3a1801337703&utm_source=qianchuan-origin-entrance"
            "&utm_medium=doudian-pc&utm_campaign=top-navigation-qianchuan&utm_term=guanggaoshuju&mar-goal=1"
            "&tabs=product&live-report-type=post_data&live-data-dimensions=aweme&live-post-invest-ecp=0"
            "&live-material-type=4&live-task-search=&live-raise-target=0&product-assist-task-type=1"
            "&product-material-type=video&product-material-search=&product-plan-aggregate-smart-bid-type="
            "&product-task-search=&product-invest-order-platform=0&product-material-order-platform=0"
            "#date-range%5BprefixOptionValue%5D=stat_time_day&date-range%5BdateValue%5D%5B0%5D="
            "2026-06-02%2020%3A20%3A55&date-range%5BdateValue%5D%5B1%5D=2026-06-08%2020%3A20%3A55"
        ),
    ),
    "douyin_influencer": RobotTask(
        key="douyin_influencer",
        platform="抖音",
        platform_code="douyin",
        profile="douyin",
        kind="influencer",
        slug="influencer",
        url="https://buyin.jinritemai.com/dashboard/data/financial/list",
    ),
    "tmall_orders": RobotTask(
        key="tmall_orders",
        platform="天猫",
        platform_code="tmall",
        profile="tmall",
        kind="orders",
        slug="orders",
        url="https://myseller.taobao.com/home.htm/trade-platform/tp/sold",
    ),
    "tmall_ads": RobotTask(
        key="tmall_ads",
        platform="天猫",
        platform_code="tmall",
        profile="tmall",
        kind="ads",
        slug="ads",
        url=(
            "https://one.alimama.com/index.html?spm=a21dvs.28490323.cf182d077.de22e78c2.2b022ceddhGr5B"
            "#!/report/account?spm=a21dvs.28490323.cf182d077.de22e78c2.2b022ceddhGr5B&rptType=account"
            "&isRequestedQztDefaultSet=1&queryFieldIn=%5B%22adPv%22%2C%22click%22%2C%22charge%22%2C%22ctr%22"
            "%2C%22ecpc%22%2C%22alipayInshopAmt%22%2C%22alipayInshopNum%22%2C%22cvr%22%2C%22cartInshopNum%22"
            "%2C%22itemColInshopNum%22%2C%22shopColDirNum%22%2C%22colNum%22%2C%22itemColInshopCost%22"
            "%2C%22ecpm%22%5D&vsType=off&queryDomains=%5B%22date%22%5D"
        ),
    ),
}


PLATFORM_TASKS: dict[str, tuple[str, ...]] = {
    "pinduoduo": ("pinduoduo_orders", "pinduoduo_ads"),
    "wechat_channels": ("wechat_channels_orders",),
    "douyin": ("douyin_ads", "douyin_influencer"),
    "tmall": ("tmall_orders", "tmall_ads"),
}
