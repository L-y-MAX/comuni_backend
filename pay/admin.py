from django.contrib import admin
from django.utils.html import format_html
from .models import PayOrder


@admin.register(PayOrder)
class PayOrderAdmin(admin.ModelAdmin):
    """支付订单Admin配置：仅允许查看，禁止所有修改操作"""

    # ========== 核心：禁用所有修改权限 ==========
    def has_add_permission(self, request):
        """保留添加订单权限"""
        return True

    def has_change_permission(self, request, obj=None):
        """禁用修改订单权限"""
        return False

    def has_delete_permission(self, request, obj=None):
        """保留删除订单权限"""
        return True

    def has_view_permission(self, request, obj=None):
        """仅保留查看权限"""
        return True

    # ========== 列表页展示配置（仅查看） ==========
    # 列表显示的字段（优先展示核心+易排查的字段）
    list_display = [
        'out_trade_no',  # 商户订单号（核心）
        'payee_user_info',  # 自定义：被充值用户（用户名+ID）
        'payer_openid',  # 付款人OpenID
        'package_type_display',  # 自定义：套餐中文名称
        'price',  # 支付金额
        'status_display',  # 自定义：订单状态中文
        'create_time',  # 创建时间
        'pay_time',  # 支付时间
        'expire_at',  # 过期时间
        'yungou_code_display',  # 自定义：YunGouOS返回码
    ]

    # 列表筛选条件（便于快速过滤查看）
    list_filter = [
        'status',  # 订单状态
        'package_type',  # 套餐类型
        'auto',  # 分账模式
        'create_time',  # 创建时间（按日期筛选）
        'pay_time',  # 支付时间
    ]

    # 搜索字段（支持模糊搜索查看）
    search_fields = [
        'out_trade_no',  # 商户订单号（精准搜索）
        'payer_openid',  # 付款人OpenID
        'payee_user__username',  # 被充值用户用户名
        'payee_user__id',  # 被充值用户ID
        'mch_id',  # 商户号
    ]

    # 排序规则（默认按创建时间倒序）
    ordering = ['-create_time']

    # ========== 关键：所有字段设为只读（无任何可编辑项） ==========
    readonly_fields = [
        # 核心订单信息
        'id', 'out_trade_no', 'payee_user', 'payer_openid',
        'package_type', 'price', 'status', 'add_days', 'actual_expire_time',
        # 时间信息
        'create_time', 'pay_time', 'expire_at',
        # YunGouOS 请求参数
        'mch_id', 'app_id', 'total_fee', 'body', 'notify_url',
        'auto', 'auto_node', 'config_no', 'biz_params', 'sign',
        # YunGouOS 返回结果
        'yungou_code', 'yungou_msg', 'yungou_data',
        # 附加信息
        'attach', 'notify_data'
    ]

    # ========== 详情页分栏配置（仅查看，更清晰） ==========
    fieldsets = (
        ('核心订单信息', {
            'fields': ('id', 'out_trade_no', 'payee_user', 'payer_openid',
                       'package_type', 'price', 'status', 'add_days', 'actual_expire_time')
        }),
        ('时间信息', {
            'fields': ('create_time', 'pay_time', 'expire_at')
        }),
        ('YunGouOS 请求参数', {
            'fields': ('mch_id', 'app_id', 'total_fee', 'body', 'notify_url',
                       'auto', 'auto_node', 'config_no', 'biz_params', 'sign'),
            'classes': ('collapse',)  # 默认折叠，需要时展开查看
        }),
        ('YunGouOS 返回结果', {
            'fields': ('yungou_code', 'yungou_msg', 'yungou_data'),
            'classes': ('collapse',)
        }),
        ('附加信息', {
            'fields': ('attach', 'notify_data'),
            'classes': ('collapse',)
        }),
    )

    # ========== 自定义列表显示字段（优化查看可读性） ==========
    def payee_user_info(self, obj):
        """自定义显示被充值用户：用户名（ID）"""
        return format_html(f"{obj.payee_user.username}（ID：{obj.payee_user.id}）")

    payee_user_info.short_description = '被充值用户'  # 列表表头名称
    payee_user_info.admin_order_field = 'payee_user__username'  # 支持按用户名排序

    def package_type_display(self, obj):
        """自定义显示套餐中文名称"""
        return obj.get_package_type_display()

    package_type_display.short_description = '充值套餐'
    package_type_display.admin_order_field = 'package_type'

    def status_display(self, obj):
        """自定义显示状态（带颜色标签，更直观查看）"""
        color_map = {
            'pending': 'orange',
            'success': 'green',
            'failed': 'red',
            'expired': 'gray'
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color_map.get(obj.status, 'black'),
            obj.get_status_display()
        )

    status_display.short_description = '订单状态'
    status_display.admin_order_field = 'status'

    def yungou_code_display(self, obj):
        """自定义显示YunGouOS返回码（带说明，便于查看）"""
        if obj.yungou_code == 0:
            return format_html('<span style="color: green;">0（下单成功）</span>')
        elif obj.yungou_code == 1:
            return format_html('<span style="color: red;">1（下单失败）</span>')
        return '-'

    yungou_code_display.short_description = 'YunGouOS返回码'
    yungou_code_display.admin_order_field = 'yungou_code'

    # ========== 禁用所有批量操作（防止误操作） ==========
    actions = None