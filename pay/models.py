import uuid
import json
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.conf import settings  # 导入配置文件，读取默认值
from users.models import User  # 导入自定义User模型

# 订单状态枚举（保留原有，补充业务含义）
STATUS_CHOICES = (
    ('pending', '待支付'),  # 调用YunGouOS下单成功，等待用户支付
    ('success', '支付成功'),  # YunGouOS回调确认支付成功
    ('failed', '支付失败'),  # 下单失败/支付失败/用户取消
    ('expired', '订单过期'),  # 超过支付时效未支付
)

# 套餐类型枚举
PACKAGE_CHOICES = (
    ('month', '月度会员'),
    ('year', '年度会员'),
)

# YunGouOS 分账模式枚举
AUTO_CHOICES = (
    ('0', '不分账'),
    ('1', '自动分账'),
    ('2', '手动分账'),
)

# YunGouOS 分账执行节点枚举
AUTO_NODE_CHOICES = (
    ('pay', '付款成功后分账'),
    ('callback', '回调成功后分账'),
)


class PayOrder(models.Model):
    # ===================== 原有核心字段 =====================
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 被充值用户（会员权益接收者）
    payee_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_pay_orders',
        verbose_name='被充值用户',
        null=False,
        blank=False
    )

    # 支付用户OpenID（对应YunGouOS的open_id参数）
    payer_openid = models.CharField(
        verbose_name='支付用户OpenID',
        max_length=128,
        null=False,
        blank=False
    )

    # 支付核心参数（原有）
    out_trade_no = models.CharField(verbose_name='商户订单号', max_length=64, unique=True)
    package_type = models.CharField(verbose_name='充值套餐', max_length=10, choices=PACKAGE_CHOICES)
    price = models.DecimalField(verbose_name='支付金额', max_digits=10, decimal_places=2)
    status = models.CharField(verbose_name='订单状态', max_length=10, choices=STATUS_CHOICES, default='pending')

    # 会员时长记录（冗余存储）
    add_days = models.IntegerField(verbose_name='新增会员天数', blank=True, null=True)  # 30/365
    actual_expire_time = models.DateTimeField(verbose_name='充值后过期时间', blank=True, null=True)

    # 附加信息（原有，对应YunGouOS的 attach 参数）
    attach = models.TextField(verbose_name='附加信息', blank=True, null=True)
    notify_data = models.JSONField(verbose_name='回调原始数据', blank=True, null=True)

    # 时间字段（原有）
    create_time = models.DateTimeField(verbose_name='创建时间', auto_now_add=True)
    pay_time = models.DateTimeField(verbose_name='支付完成时间', blank=True, null=True)

    # ===================== 新增：YunGouOS 请求参数（完整） =====================
    mch_id = models.CharField(
        verbose_name='微信支付商户号（YunGouOS）',
        max_length=32,
        null=False,
        blank=False,
        default=getattr(settings, 'YUNGOU_MCH_ID', '1234567890')  # 从配置读取，无则用默认值
    )

    app_id = models.CharField(
        verbose_name='小程序APPID（YunGouOS）',
        max_length=32,
        null=False,
        blank=False,
        default=getattr(settings, 'WX_MINI_APPID', 'wx1234567890abcdef')  # 从配置读取
    )

    total_fee = models.DecimalField(
        verbose_name='支付金额（YunGouOS参数）',
        max_digits=10,
        decimal_places=2,
        null=False,
        blank=False,
        default=0.00  # 默认0，创建订单时覆盖为price值
    )

    body = models.CharField(
        verbose_name='商品/服务描述（YunGouOS）',
        max_length=128,
        null=False,
        blank=False,
        default='会员充值'  # 默认商品描述
    )

    notify_url = models.URLField(
        verbose_name='异步回调地址（YunGouOS）',
        blank=True,
        null=True,
        default=getattr(settings, 'YUNGOU_NOTIFY_URL', '')  # 从配置读取回调地址
    )

    auto = models.CharField(
        verbose_name='分账模式（YunGouOS）',
        max_length=1,
        choices=AUTO_CHOICES,
        default='0',  # 默认不分账
        blank=False,
        null=False
    )

    auto_node = models.CharField(
        verbose_name='分账执行节点（YunGouOS）',
        max_length=10,
        choices=AUTO_NODE_CHOICES,
        blank=True,
        null=True,
        default='pay'  # 默认付款后分账
    )

    config_no = models.CharField(
        verbose_name='分账配置单号（YunGouOS）',
        max_length=256,
        blank=True,
        null=True,
        default=''  # 默认空字符串
    )

    biz_params = models.JSONField(
        verbose_name='附加业务参数（YunGouOS）',
        blank=True,
        null=True,
        default=dict  # 默认空字典
    )

    sign = models.CharField(
        verbose_name='数据签名（YunGouOS）',
        max_length=256,
        null=False,
        blank=False,
        default='temp_sign_123456'  # 临时默认值，创建订单时覆盖
    )

    # ===================== 新增：YunGouOS 返回结果（完整） =====================
    yungou_code = models.IntegerField(
        verbose_name='YunGouOS返回状态码',
        blank=True,
        null=True,
        help_text='0：下单成功；1：下单失败'
    )

    yungou_msg = models.CharField(
        verbose_name='YunGouOS返回消息',
        max_length=256,
        blank=True,
        null=True
    )

    yungou_data = models.JSONField(
        verbose_name='YunGouOS返回支付参数',
        blank=True,
        null=True,
        help_text='包含appId、nonceStr、package等小程序支付参数'
    )

    # ===================== 新增：订单过期管理 =====================
    expire_at = models.DateTimeField(
        verbose_name='订单过期时间',
        blank=True,
        null=True,
        help_text='订单创建后2小时未支付则过期'
    )

    class Meta:
        verbose_name = '支付订单'
        verbose_name_plural = '支付订单'
        ordering = ['-create_time']
        indexes = [
            # 原有索引
            models.Index(fields=['payee_user', 'payer_openid']),
            models.Index(fields=['payer_openid']),
            models.Index(fields=['out_trade_no']),
            models.Index(fields=['status']),
            # 新增索引（优化查询）
            models.Index(fields=['mch_id']),
            models.Index(fields=['app_id']),
            models.Index(fields=['status', 'expire_at']),  # 筛选过期订单
        ]

    def __str__(self):
        return f"付款人({self.payer_openid}) → 被充值人({self.payee_user.username}) - {self.get_package_type_display()} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # 1. 自动计算新增会员天数（原有逻辑）
        if self.package_type:
            self.add_days = 30 if self.package_type == 'month' else 365

        # 2. 保证total_fee与price一致（防止数据不一致）
        self.total_fee = self.price

        # 3. 新增订单时初始化过期时间（创建后2小时）
        if not self.pk:  # 首次创建
            self.expire_at = timezone.now() + timedelta(hours=2)

        super().save(*args, **kwargs)

    # ===================== 核心：订单状态更新逻辑（严格校验） =====================
    def mark_as_pending(self, yungou_code: int, yungou_msg: str, yungou_data: dict):
        """
        标记订单为「待支付」（调用YunGouOS下单成功）
        :param yungou_code: YunGouOS返回的code（0=成功）
        :param yungou_msg: YunGouOS返回的msg
        :param yungou_data: YunGouOS返回的支付参数（appId、nonceStr等）
        """
        if self.status != 'pending':
            raise ValueError(f"订单当前状态为{self.get_status_display()}，无法标记为待支付")
        if yungou_code != 0:
            raise ValueError(f"YunGouOS下单失败（code={yungou_code}），无法标记为待支付")

        self.yungou_code = yungou_code
        self.yungou_msg = yungou_msg
        self.yungou_data = yungou_data
        self.status = 'pending'
        self.save(update_fields=['yungou_code', 'yungou_msg', 'yungou_data', 'status'])

    def mark_as_order_failed(self, yungou_code: int, yungou_msg: str):
        """标记订单为「支付失败」（调用YunGouOS下单失败）"""
        self.yungou_code = yungou_code
        self.yungou_msg = yungou_msg
        self.status = 'failed'
        self.save(update_fields=['yungou_code', 'yungou_msg', 'status'])

    def mark_as_pay_success(self, notify_data: dict, pay_time: timezone.datetime = None):
        """
        标记订单为「支付成功」（YunGouOS回调确认）
        :param notify_data: 回调原始数据
        :param pay_time: 实际支付时间（默认当前时间）
        """
        if self.status != 'pending':
            raise ValueError(f"订单当前状态为{self.get_status_display()}，无法标记为支付成功")

        self.status = 'success'
        self.pay_time = pay_time or timezone.now()
        self.notify_data = notify_data
        self.save(update_fields=['status', 'pay_time', 'notify_data'])

    def mark_as_pay_failed(self, notify_data: dict = None, reason: str = None):
        """
        标记订单为「支付失败」（YunGouOS回调失败/用户取消）
        :param notify_data: 回调原始数据
        :param reason: 失败原因
        """
        if self.status != 'pending':
            raise ValueError(f"订单当前状态为{self.get_status_display()}，无法标记为支付失败")

        self.status = 'failed'
        self.notify_data = notify_data
        if reason:
            # 保留原有attach，追加失败原因
            if self.attach:
                try:
                    attach_dict = json.loads(self.attach)
                except json.JSONDecodeError:
                    attach_dict = {}
                attach_dict['fail_reason'] = reason
                self.attach = json.dumps(attach_dict)
            else:
                self.attach = json.dumps({'fail_reason': reason})
        self.save(update_fields=['status', 'notify_data', 'attach'])

    def mark_as_expired(self):
        """标记订单为「订单过期」（超期未支付）"""
        if self.status != 'pending':
            raise ValueError(f"订单当前状态为{self.get_status_display()}，无法标记为过期")
        if not self.is_expired():
            raise ValueError("订单未到过期时间，无法标记为过期")

        self.status = 'expired'
        self.save(update_fields=['status'])

    def is_expired(self) -> bool:
        """判断订单是否已过期（仅待支付状态有效）"""
        if self.status != 'pending':
            return False
        if not self.expire_at:
            return False
        return timezone.now() > self.expire_at