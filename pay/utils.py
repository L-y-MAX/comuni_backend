from datetime import datetime, timedelta
from django.utils import timezone
import hashlib
import time
import random


def generate_out_trade_no() -> str:
    """生成唯一订单号"""
    timestamp = str(int(time.time() * 1000))
    random_str = str(random.randint(100000, 999999))
    return f"VIP{timestamp}{random_str}"


def generate_yungou_sign(params: dict, pay_key: str) -> str:
    """生成YunGouOS签名（传入pay_key避免耦合settings）"""
    valid_params = {k: v for k, v in params.items() if v not in (None, "", "")}
    sorted_keys = sorted(valid_params.keys())
    sign_str = "&".join([f"{k}={valid_params[k]}" for k in sorted_keys])
    sign_str += f"&key={pay_key}"
    md5 = hashlib.md5()
    md5.update(sign_str.encode("utf-8"))
    return md5.hexdigest().upper()


def calculate_vip_expire_time(pay_time: datetime, package_type: str, current_expire_time: datetime = None) -> datetime:
    """计算会员过期时间（非自然月+累加逻辑）"""
    days_map = {"month": 30, "year": 365}
    add_days = days_map.get(package_type, 0)

    if current_expire_time and current_expire_time > timezone.now():
        base_time = current_expire_time
    else:
        base_time = pay_time

    new_expire = base_time + timedelta(days=add_days)
    new_expire = new_expire.replace(hour=0, minute=0, second=0, microsecond=0)

    return new_expire