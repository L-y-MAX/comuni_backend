from rest_framework import serializers
from .models import PayOrder
from users.models import User

class PayOrderSerializer(serializers.ModelSerializer):
    """支付订单序列化器（适配前后端分离，统一返回格式）"""
    # 自定义显示被充值用户信息（用户名+ID）
    payee_user_name = serializers.CharField(source='payee_user.username', read_only=True)
    payee_user_id = serializers.UUIDField(source='payee_user.id', read_only=True)
    # 自定义显示套餐名称（替代choices的数字/英文）
    package_name = serializers.CharField(source='get_package_type_display', read_only=True)
    # 自定义显示订单状态文本
    status_text = serializers.CharField(source='get_status_display', read_only=True)
    # 格式化时间字段
    create_time = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True)
    pay_time = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True, allow_null=True)
    actual_expire_time = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', read_only=True, allow_null=True)

    class Meta:
        model = PayOrder
        fields = [
            'id', 'out_trade_no', 'payer_openid', 'payee_user', 
            'payee_user_name', 'payee_user_id', 'package_type', 
            'package_name', 'price', 'status', 'status_text', 
            'add_days', 'actual_expire_time', 'attach', 
            'notify_data', 'create_time', 'pay_time'
        ]
        # 只读字段（后端生成/数据库自动填充，前端不可修改）
        read_only_fields = [
            'id', 'out_trade_no', 'add_days', 'actual_expire_time',
            'create_time', 'pay_time', 'status', 'notify_data'
        ]

class PayOrderQuerySerializer(serializers.Serializer):
    """订单查询参数序列化器（校验前端查询参数）"""
    payee_user_id = serializers.UUIDField(required=False, allow_null=True)  # 被充值用户ID
    payer_openid = serializers.CharField(max_length=128, required=False, allow_blank=True)  # 付款人OpenID

    def validate(self, attrs):
        """至少传一个查询参数"""
        if not attrs.get('payee_user_id') and not attrs.get('payer_openid'):
            raise serializers.ValidationError("必须传入payee_user_id或payer_openid作为查询条件")
        return attrs

class PayOrderCreateSerializer(serializers.Serializer):
    """创建订单参数序列化器（校验前端创建订单参数）"""
    package_type = serializers.ChoiceField(choices=['month', 'year'])  # 充值套餐
    payer_openid = serializers.CharField(max_length=128)  # 付款人OpenID
    payee_user_id = serializers.UUIDField()  # 被充值用户ID

    def validate_payee_user_id(self, value):
        """校验被充值用户存在"""
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("被充值用户不存在")
        return value