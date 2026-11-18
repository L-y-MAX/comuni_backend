from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.conf import settings
from django.utils import timezone
import requests
import json

from .models import PayOrder
from .serializers import (
    PayOrderSerializer, PayOrderQuerySerializer, PayOrderCreateSerializer
)
from users.models import User, VipInfo
from .utils import (
    generate_out_trade_no, generate_yungou_sign, calculate_vip_expire_time
)

from django.shortcuts import render

def pay_page(request):
    """支付页面视图"""
    return render(request, 'pay/pay.html')

class PayOrderViewSet(viewsets.GenericViewSet):
    """支付订单ViewSet（管理创建订单、查询订单、支付回调）"""
    queryset = PayOrder.objects.all().order_by('-create_time')
    serializer_class = PayOrderSerializer
    # 全局权限：默认需要登录（创建/查询订单）
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='create_order')
    def create_order(self, request):
        """创建支付订单（POST /api/v1/pay/create_order/）"""
        # 保留原有创建订单逻辑，无修改
        serializer = PayOrderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": -1,
                "msg": "参数校验失败",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        package_type = serializer.validated_data['package_type']
        payer_openid = serializer.validated_data['payer_openid']
        payee_user_id = serializer.validated_data['payee_user_id']
        payee_user = User.objects.get(id=payee_user_id)

        price_map = {"month": 19.9, "year": 199}
        price = price_map[package_type]

        out_trade_no = generate_out_trade_no()
        pay_params = {
            "out_trade_no": out_trade_no,
            "total_fee": str(price),
            "mch_id": settings.MCH_ID,
            "body": f"为{payee_user.username}充值{package_type == 'month' and '月度' or '年度'}会员",
            "open_id": payer_openid,
            "app_id": settings.APP_ID,
            "attach": json.dumps({
                "payeeUserId": str(payee_user.id),
                "payerOpenId": payer_openid,
                "packageType": package_type
            }),
            "notify_url": settings.NOTIFY_URL,
            "auto": "0",
            "sign": ""
        }
        pay_params["sign"] = generate_yungou_sign(pay_params, settings.PAY_KEY)

        try:
            res = requests.post(
                url=settings.YUNGOUOS_PAY_URL,
                data=pay_params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15
            )
            yun_res = res.json()
        except requests.exceptions.RequestException as e:
            return Response({
                "code": -1,
                "msg": f"支付接口调用失败：{str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if yun_res.get("code") != 0:
            return Response({
                "code": -1,
                "msg": f"下单失败：{yun_res.get('msg', '未知错误')}"
            }, status=status.HTTP_400_BAD_REQUEST)

        pay_order = PayOrder.objects.create(
            payee_user=payee_user,
            payer_openid=payer_openid,
            out_trade_no=out_trade_no,
            package_type=package_type,
            price=price
        )

        order_info = {
            "out_trade_no": out_trade_no,
            "payeeUserId": str(payee_user.id),
            "payerOpenId": payer_openid,
            "package_type": package_type,
            "status": "pending"
        }
        settings.REDIS_CONN.setex(f"pay_order:{out_trade_no}", 7200, json.dumps(order_info))

        return Response({
            "code": 0,
            "msg": "下单成功，请发起支付",
            "data": {
                "timeStamp": yun_res["data"]["timeStamp"],
                "nonceStr": yun_res["data"]["nonceStr"],
                "package": yun_res["data"]["package"],
                "signType": yun_res["data"]["signType"],
                "paySign": yun_res["data"]["paySign"],
                "outTradeNo": out_trade_no,
                "orderId": str(pay_order.id)
            }
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='orders')
    def list_orders(self, request):
        """查询订单（POST /api/v1/pay/orders/）"""
        # 保留原有查询订单逻辑，无修改
        serializer = PayOrderQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": -1,
                "msg": "查询参数校验失败",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        query_kwargs = {}
        if serializer.validated_data.get('payee_user_id'):
            query_kwargs["payee_user_id"] = serializer.validated_data['payee_user_id']
        if serializer.validated_data.get('payer_openid'):
            query_kwargs["payer_openid"] = serializer.validated_data['payer_openid']

        orders = self.get_queryset().filter(**query_kwargs)
        order_serializer = self.get_serializer(orders, many=True)

        return Response({
            "code": 0,
            "msg": "查询成功",
            "data": order_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='notify', permission_classes=[permissions.AllowAny])
    def notify(self, request):
        """
        支付回调接口（由 DefaultRouter 管理，POST /api/v1/pay/notify/）
        权限：允许任何人访问（YunGouOS 调用无需认证）
        """
        try:
            # 1. 解析回调参数（兼容form-data和json）
            if request.content_type == 'application/json':
                notify_data = request.data
            else:
                notify_data = request.POST.dict()

            out_trade_no = notify_data.get("out_trade_no")
            trade_state = notify_data.get("trade_state")

            # 2. 校验基础参数
            if not out_trade_no or trade_state != "SUCCESS":
                return Response({
                    "code": -1,
                    "msg": "无效回调"
                }, status=status.HTTP_400_BAD_REQUEST)

            # 3. 查询订单
            try:
                order = PayOrder.objects.get(out_trade_no=out_trade_no)
            except PayOrder.DoesNotExist:
                return Response({
                    "code": -1,
                    "msg": "订单不存在"
                }, status=status.HTTP_404_NOT_FOUND)

            # 4. 防止重复回调
            if order.status == "success":
                return Response({
                    "code": 0,
                    "msg": "success"
                }, status=status.HTTP_200_OK)

            # 5. 更新订单状态
            pay_time = timezone.now()
            order.status = "success"
            order.pay_time = pay_time
            order.notify_data = notify_data

            # 6. 累加被充值用户会员时长
            payee_user = order.payee_user
            vip_info, created = VipInfo.objects.get_or_create(user=payee_user)
            new_expire = calculate_vip_expire_time(
                pay_time=pay_time,
                package_type=order.package_type,
                current_expire_time=vip_info.expire_date
            )
            vip_info.is_vip = True
            vip_info.expire_date = new_expire
            vip_info.save()

            # 7. 更新订单的会员过期时间
            order.actual_expire_time = new_expire
            order.save()

            return Response({
                "code": 0,
                "msg": "success"
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"回调处理异常：{str(e)}")
            return Response({
                "code": -1,
                "msg": "处理失败"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)