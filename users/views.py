import re
import os
import requests
import shortuuid
import uuid  # 新增：用于UUID格式校验
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework.decorators import action
from django.contrib.auth import get_user_model, authenticate  # 验证账号密码（Django内置的authenticate方法）
from django.contrib.auth.hashers import check_password  # 补充缺失的导入
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import IntegrityError

from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import UserFollow, VipInfo
from .serializers import (UserDetailSerializer, UserFollowSerializer,
                          UserFollowListItemSerializer,
                          IsFollowedSerializer, FollowListSummarySerializer,
                          UserSerializer, VipInfoSerializer,
                          GroupSerializer, UserIDUpdateSerializer,
                          CustomTokenObtainPairSerializer,
                          UserPersonalDetailSerializer)
from .utils import get_user_avatar_full_url, rename_avatar  # 工具函数 用于拼接 头像url，重命名头像函数


# ========== 新增：SQL注入防护辅助函数（不影响原有逻辑） ==========
def validate_uuid(uuid_str):
    """校验字符串是否为合法UUID"""
    try:
        uuid.UUID(uuid_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_numeric_id(id_str):
    """校验字符串是否为合法数字ID"""
    if not id_str:
        return False
    return id_str.isdigit()


def sanitize_input(input_str):
    """清理输入字符串，移除SQL注入相关危险字符"""
    if not isinstance(input_str, str):
        return input_str
    # 移除SQL关键字和特殊字符
    dangerous_patterns = [
        r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b',
        r'--', r';', r'%', r'\\', r'\'', r'"', r'\(', r'\)'
    ]
    sanitized = input_str
    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


User = get_user_model()


# ============================ 备案要求实现  ===========================
# 备案要求网站首页要挂备案号，如果没有特殊要求这里进行简单实现即可
def index(request):
    return render(request, "index/index.html")


# ============================ 微信绑定视图  ===========================
class BindWeChatAPIView(APIView):
    """用户绑定微信OpenID接口（需登录）"""
    permission_classes = [IsAuthenticated]  # 强制要求用户登录

    def post(self, request):
        # 1. 获取当前登录用户（DRF自动通过认证解析）
        user = request.user

        # 2. 获取前端传递的openid（DRF用request.data，兼容JSON/表单）
        openid = request.data.get("openid")
        if not openid:
            return Response(
                {"code": 400, "msg": "8缺少OpenID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SQL注入防护：校验OpenID格式（微信OpenID为28位字母数字组合）openid长度28，unionid长度29
        if not re.match(r'^.{24,32}$', openid):
            return Response(
                {"code": 400, "msg": "8-OpenID格式非法"},
                status=status.HTTP_400_BAD_REQUEST
            )
        # 清理OpenID（防止特殊字符）
        openid = sanitize_input(openid)

        # 3. 检查OpenID是否已被其他用户绑定
        if User.objects.filter(wechat_openid=openid).exclude(pk=user.pk).exists():
            return Response(
                {"code": 400, "msg": "该微信账号已绑定其他用户"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. 更新用户的微信OpenID
        try:
            user.wechat_openid = openid
            user.save(update_fields=["wechat_openid", "updated_at"])  # 只更新必要字段，提升性能
            return Response({
                "code": 200,
                "msg": "绑定成功",
                "data": {"wechat_openid": user.wechat_openid}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"code": 500, "msg": f"绑定失败：{str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================ wechat api  ===========================
class WeChatMiniLoginAPIView(APIView):
    """微信小程序登录接口（DRF版）- 适配DefaultRouter"""
    authentication_classes = []  # 登录接口无需认证
    permission_classes = []  # 无需权限校验

    def post(self, request):
        # 1. 获取前端传递的code
        code = request.data.get("code")  # DRF使用request.data获取POST数据
        if not code:
            return Response(
                {"code": 400, "msg": "缺少登录凭证code"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SQL注入防护：校验code格式（微信code为字母数字组合，长度10-32）
        if not re.match(r'^[a-zA-Z0-9]{8,50}$', code):
            return Response(
                {"code": 400, "msg": "登录凭证格式非法"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 调用微信接口兑换openid
        wx_config = settings.WECHAT_MINI_APP
        params = {
            "appid": wx_config["APP_ID"],
            "secret": wx_config["APP_SECRET"],
            "js_code": code,
            "grant_type": "authorization_code"
        }
        try:
            response = requests.get(wx_config["LOGIN_URL"], params=params, timeout=10)
            response.raise_for_status()  # 捕获HTTP状态码错误（如404/500）
            res_data = response.json()
        except requests.exceptions.RequestException as e:
            return Response(
                {"code": 500, "msg": f"微信接口请求失败：{str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 3. 处理微信接口返回结果
        if "errcode" in res_data and res_data["errcode"] != 0:
            return Response(
                {"code": 400, "msg": f"微信登录失败：{res_data.get('errmsg', '未知错误')}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        openid = res_data.get("openid")
        if not openid:
            return Response(
                {"code": 400, "msg": "未获OpenID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SQL注入防护：校验并清理OpenID
        if not re.match(r'^.{24,32}$', openid):
            return Response(
                {"code": 400, "msg": "OpenID非法格式"},
                status=status.HTTP_400_BAD_REQUEST
            )
        openid = sanitize_input(openid)

        # 4. 关联/创建用户
        try:
            # 查找已有OpenID的用户
            user = User.objects.get(wechat_openid=openid)
        except User.DoesNotExist:
            # 创建新用户（保证用户名唯一）
            try:
                username = f"wx_{openid[:10]}_{shortuuid.ShortUUID().random(length=6)}"
                # 循环确保username唯一（防止极端情况重复）
                while User.objects.filter(username=username).exists():
                    username = f"wx_{openid[:10]}_{shortuuid.ShortUUID().random(length=6)}"

                user = User.objects.create(
                    username=username,
                    wechat_openid=openid,
                    email=f"{username}@wx.temp",  # 临时邮箱，后续可让用户完善
                    user_id=shortuuid.uuid()  # 确保user_id生成
                )
                user.set_unusable_password()  # 小程序用户无需密码
                user.save()
            except (IntegrityError, ValidationError) as e:
                return Response(
                    {"code": 500, "msg": f"创建用户失败：{str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # 拼接完整URL（站点URL + 相对路径）
        avatar_url = get_user_avatar_full_url(user, request)

        # 5. 生成JWT Token（复用现有逻辑）
        refresh = RefreshToken.for_user(user)

        # 6. 返回结果（仅保留通用Token，删除所有专属Token）
        return Response({
            "code": 200,
            "msg": "微信登录成功",
            "data": {
                # 基础通用Token和用户标识
                "user_id": user.user_id,
                "username": user.username,
                "access": str(refresh.access_token),  # 通用accessToken
                "refresh": str(refresh),  # 通用refreshToken
                "openid": user.wechat_openid,  # 微信OpenID（仅用于前端存储，非Token）
                # 用户信息（仅保留必要字段，用于前端区分登录方式）
                "userInfo": {
                    "id": str(user.id),  # UUID转字符串，前端易处理
                    "userId": user.user_id,
                    "username": user.username,
                    "email": user.email,
                    "gender": user.gender if hasattr(user, 'gender') else "",  # 兼容无该字段的情况
                    "wechat_openid": user.wechat_openid,
                    "avatar": avatar_url or "",  # 空值给默认空字符串
                    "bio": user.bio if hasattr(user, 'bio') else "",
                    "is_private": user.is_private if hasattr(user, 'is_private') else False,
                    "created_at": user.created_at.isoformat() if hasattr(user, 'created_at') else "",  # 时间转ISO字符串
                    "loginType": "wechat"  # 仅标记登录类型，无专属Token
                }
            }
        }, status=status.HTTP_200_OK)


class PasswordLoginAPIView(APIView):
    """用户名密码登录接口 - 返回通用Token"""
    authentication_classes = []  # 登录接口无需认证
    permission_classes = []  # 无需权限校验

    def post(self, request):
        # 1. 获取前端传递的用户名和密码
        username = request.data.get("username")
        password = request.data.get("password")
        if not username or not password:
            return Response(
                {"code": 400, "msg": "缺少用户名或密码"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SQL注入防护：清理用户名（防止特殊字符注入）
        username = sanitize_input(username)
        # 校验用户名格式（与更新逻辑保持一致）
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]{2,20}$', username):
            return Response(
                {"code": 400, "msg": "用户名格式非法"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 更规范的用户认证（替换原get+check_password）
        user = authenticate(username=username, password=password)
        if not user:
            return Response(
                {"code": 401, "msg": "用户名或密码错误"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 3. 生成JWT Token（仅通用Token）
        refresh = RefreshToken.for_user(user)

        # 拼接头像完整URL
        avatar_url = get_user_avatar_full_url(user, request)

        # 4. 返回结果（删除所有专属Token，仅保留通用Token）
        return Response({
            "code": 200,
            "msg": "密码登录成功",
            "data": {
                # 仅保留通用Token和必要信息
                "user_id": user.user_id,
                "username": user.username,
                "access": str(refresh.access_token),  # 通用accessToken
                "refresh": str(refresh),  # 通用refreshToken
                "openid": user.wechat_openid,  # 微信OpenID（仅用于前端存储，非Token）
                # 用户信息（仅保留必要字段，用于前端区分登录方式）
                "userInfo": {
                    "id": str(user.id),  # UUID转字符串，前端易处理
                    "userId": user.user_id,
                    "username": user.username,
                    "email": user.email,
                    "gender": user.gender if hasattr(user, 'gender') else "",  # 兼容无该字段的情况
                    "wechat_openid": user.wechat_openid,
                    "avatar": avatar_url or "",  # 空值给默认空字符串
                    "bio": user.bio if hasattr(user, 'bio') else "",
                    "is_private": user.is_private if hasattr(user, 'is_private') else False,
                    "created_at": user.created_at.isoformat() if hasattr(user, 'created_at') else "",  # 时间转ISO字符串
                    "loginType": "password",  # 仅标记登录类型，无专属Token
                }
            }
        }, status=status.HTTP_200_OK)


# =============================== api  ===============================
class UserViewSetV1(ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    合并了更新用户ID的功能，统一管理用户相关接口
    """
    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    lookup_fields = ['id', 'user_id']

    # 新增自定义 action：更新当前用户的 user_id
    # detail=False：表示这是「集合级」action（不针对单个用户实例），URL 无需传 pk
    # methods=["patch"]：仅允许 PATCH 请求（部分更新），符合 REST 规范
    @action(detail=False, methods=["patch"], serializer_class=UserIDUpdateSerializer)
    def update_user_id(self, request):
        """
        自定义动作：更新当前登录用户的 user_id
        仅允许用户修改自己的 ID，且仅接受 PATCH 请求（部分更新）
        """
        # 关键修正：获取当前登录用户实例（你之前的代码写的是 user = User，这是类，不是实例！）
        user = request.user

        # SQL注入防护：校验user_id参数（如果存在）
        if "user_id" in request.data:
            user_id = request.data.get("user_id")
            if not re.match(r'^[a-zA-Z0-9]{8,32}$', user_id):
                return Response(
                    {"code": 400, "msg": "user_id格式非法"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # 清理user_id
            request.data["user_id"] = sanitize_input(user_id)

        if "id" in request.data:
            main_id = request.data.get("id")
            # id 是不允许修改的
            if not re.match(r'^[a-zA-Z0-9]{16,32}$', main_id):
                return Response(
                    {"code": 400, "msg": "id格式非法"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # 清理id
            request.data["id"] = sanitize_input(main_id)

        # 使用专门的 UserIDUpdateSerializer 校验并更新 user_id
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)

    # 可选：如果需要限制普通用户只能查看/修改自己的信息（增强权限）
    def get_queryset(self):
        user = self.request.user
        # 管理员能看所有用户，普通用户只能看自己
        if user.is_staff:
            return User.objects.all().order_by("-date_joined")
        return User.objects.filter(pk=user.pk)

    # 根据动作切换序列化器（列表用基础序列化器，详情用带关注数的序列化器）
    def get_serializer_class(self):
        if self.action == 'retrieve':  # 详情接口用 UserDetailSerializer
            return UserDetailSerializer
        elif self.action == 'follow':  # 关注操作用 UserFollowSerializer
            return UserFollowSerializer
        return UserSerializer  # 列表/创建等用基础 UserSerializer

    # ========== 新增：关注/取消关注 自定义动作 ==========
    @action(detail=True, methods=['post', 'delete'], permission_classes=[IsAuthenticated])
    def follow(self, request, id=None):
        """
        关注/取消关注用户
        POST: /api/v1/auth/users/user/{id}/follow/ → 关注
        DELETE: /api/v1/auth/users/user/{id}/follow/ → 取消关注
        """
        # SQL注入防护：校验被关注者ID格式
        if not id or not (validate_uuid(id) or validate_numeric_id(id)):
            return Response({
                'code': 400,
                'msg': '用户ID格式非法',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)

        follower = request.user  # 当前登录用户（关注者）
        try:
            followed = self.get_object()  # 被关注者（通过 id 匹配）

            # 1. POST 请求：关注用户
            if request.method == 'POST':
                # 检查是否已关注
                if UserFollow.objects.filter(follower=follower, followed=followed).exists():
                    return Response({
                        'code': 400,
                        'msg': f'已关注 {followed.username}，无需重复关注',
                        'data': {}
                    }, status=status.HTTP_200_OK)
                # 创建关注关系（触发模型的 clean 校验：禁止关注自己）
                UserFollow.objects.create(follower=follower, followed=followed)
                return Response({
                    'code': 200,
                    'msg': f'关注 {followed.username} 成功',
                    'data': {}
                }, status=status.HTTP_200_OK)

            # 2. DELETE 请求：取消关注
            elif request.method == 'DELETE':
                # 删除关注关系
                deleted, _ = UserFollow.objects.filter(follower=follower, followed=followed).delete()
                if deleted > 0:
                    return Response({
                        'code': 200,
                        'msg': f'取消关注 {followed.username} 成功',
                        'data': {}
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'code': 400,
                        'msg': f'未关注 {followed.username}，无需取消',
                        'data': {}
                    }, status=status.HTTP_200_OK)
            return None

        except User.DoesNotExist:
            return Response({
                'code': 404,
                'msg': '用户不存在',
                'data': {}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'code': 500,
                'msg': f'操作失败：{str(e)}',
                'data': {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"], url_path="detail")
    def personal_detail(self, request):
        """
        根据username/user_id/email查询用户详情
        URL: /api/v1/auth/users/user/detail/?param_type=username&search_param=test666
        """
        param_type = ""
        search_param = ""
        try:
            # 1. 获取并校验请求参数
            param_type = request.query_params.get("param_type", "").strip()
            search_param = request.query_params.get("search_param", "").strip()

            # 校验参数是否为空
            if not param_type or not search_param:
                return Response({
                    "code": 400,
                    "msg": "param_type（username/user_id/email）和search_param均为必填参数",
                    "data": {}
                }, status=status.HTTP_200_OK)

            # 校验param_type是否合法
            valid_param_types = ["username", "user_id", "email"]
            if param_type not in valid_param_types:
                return Response({
                    "code": 400,
                    "msg": f"param_type仅支持：{','.join(valid_param_types)}",
                    "data": {}
                }, status=status.HTTP_200_OK)

            # SQL注入防护：清理并校验查询参数
            search_param = sanitize_input(search_param)
            # 按参数类型校验格式 user_id 8-28位, 写{8,32}绰绰有余
            if param_type == "user_id" and not re.match(r'^[a-zA-Z0-9]{8,32}$', search_param):
                return Response({
                    "code": 400,
                    "msg": "user_id格式非法",
                    "data": {}
                }, status=status.HTTP_400_BAD_REQUEST)
            elif param_type == "username" and not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]{2,20}$', search_param):
                return Response({
                    "code": 400,
                    "msg": "用户名格式非法",
                    "data": {}
                }, status=status.HTTP_400_BAD_REQUEST)
            elif param_type == "email" and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
                                                        search_param):
                return Response({
                    "code": 400,
                    "msg": "邮箱格式非法",
                    "data": {}
                }, status=status.HTTP_400_BAD_REQUEST)

            # 2. 根据param_type构建查询条件（精准匹配，因三者均为unique字段）
            filter_kwargs = {param_type: search_param}
            # 查找用户（get()会自动抛DoesNotExist，因字段唯一，最多1条）
            user = User.objects.get(**filter_kwargs)

            # 3. 序列化并返回用户详情（关键：传递request上下文，保证avatar返回完整URL）
            serializer = UserPersonalDetailSerializer(user, context={'request': request})
            return Response({
                "code": 200,
                "msg": "获取用户详情成功",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        # 异常处理：用户不存在
        except User.DoesNotExist:
            return Response({
                "code": 404,
                "msg": f"未找到参数类型为{param_type}、值为{search_param}的用户",
                "data": {}
            }, status=status.HTTP_200_OK)

        # 异常处理：其他错误（如参数类型错误、数据库异常等）
        except Exception as e:
            return Response({
                "code": 500,
                "msg": f"获取用户详情失败：{str(e)}",
                "data": {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroupViewSetV1(ModelViewSet):
    """
    API endpoint that allows groups to be viewed or edited.
    """

    queryset = Group.objects.all().order_by("name")
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]


class UserVipInfoViewSet(GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = VipInfoSerializer

    def get_queryset(self):
        # 仅返回当前用户的会员信息
        return VipInfo.objects.filter(user=self.request.user)

    def list(self, request):
        # 对应 GET 请求，获取会员信息（类似原 get 方法）
        vip_info, created = VipInfo.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(vip_info)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': '获取会员信息成功'
        })

    # 可添加其他动作（如更新会员信息）
    @action(detail=False, methods=['post'])
    def update_vip(self, request):
        # 处理会员信息更新逻辑
        pass


class MyObtainTokenPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer  # 只需修改其序列化器为刚刚自定义的即可


class LoginView(APIView):
    """自定义账号密码登录接口，返回JWT token"""
    # 登录接口不需要认证
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # 1. 获取前端传的账号密码
        username = request.data.get('username')
        password = request.data.get('password')

        # 2. 校验参数
        if not all([username, password]):
            return Response({
                'code': 400,
                'msg': '账号或密码不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)

        # SQL注入防护：清理用户名
        username = sanitize_input(username)
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]{2,20}$', username):
            return Response({
                'code': 400,
                'msg': '用户名格式非法'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. 验证账号密码（Django内置的authenticate方法）
        user = authenticate(username=username, password=password)
        if not user:
            return Response({
                'code': 401,
                'msg': '账号或密码错误'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 4. 生成JWT token
        refresh = RefreshToken.for_user(user)
        token_data = {
            'refresh': str(refresh),  # 刷新token（可选）
            'access': str(refresh.access_token),  # 访问token（核心）
        }

        # 5. 返回结果
        return Response({
            'code': 200,
            'msg': '登录成功',
            'data': token_data
        }, status=status.HTTP_200_OK)


class UserInfoViewSet(GenericViewSet):
    """
    用户(自己的)信息视图集（单URL多方法）
    修复：添加serializer_class满足GenericViewSet的约束
    """
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all()
    # 核心修复：添加serializer_class（关键！解决AssertionError）
    serializer_class = UserSerializer  # 或复用你的UserSerializer

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_avatar(self, request):
        """
        上传用户头像接口（按用户ID分文件夹存储）
        URL: /api/v1/auth/user-info/upload_avatar/
        """
        # 1. 检查是否有文件上传
        if 'avatar' not in request.FILES:
            return Response({
                'code': 400,
                'msg': '请选择要上传的头像文件',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['avatar']
        user = request.user

        # SQL注入/路径遍历防护：清理文件名
        original_filename = sanitize_input(file.name)
        file.name = original_filename  # 替换为清理后的文件名

        # 2. 校验文件类型/大小（原有逻辑不变）
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        file_ext = os.path.splitext(file.name)[1].lower()
        if file_ext not in allowed_extensions:
            return Response({
                'code': 400,
                'msg': f'Only images in the format {",".join(allowed_extensions)} are supported',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)

        max_size = 5 * 1024 * 1024  # 5MB
        if file.size > max_size:
            return Response({
                'code': 400,
                'msg': 'Avatar file size cannot exceed 5MB.',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # ========== 旧头像删除逻辑（适配新路径） ==========
            old_avatar_path = None
            if user.avatar and user.avatar != '':
                old_avatar_path = os.path.join(settings.MEDIA_ROOT, str(user.avatar))
                # 检查旧文件是否存在，且不是默认头像
                if os.path.exists(old_avatar_path) and not str(user.avatar).startswith('default_'):
                    try:
                        os.remove(old_avatar_path)
                        # 可选：如果用户文件夹为空，可删除空文件夹（可选优化）
                        user_folder = os.path.dirname(old_avatar_path)
                        if not os.listdir(user_folder):
                            os.rmdir(user_folder)
                    except Exception as e:
                        # 删除失败不中断流程，仅记录日志
                        pass

            # ========== 新头像保存（复用你的rename_avatar函数） ==========
            # 调用修改后的rename_avatar生成带用户ID文件夹的路径
            new_avatar_relative_path = rename_avatar(user, file.name)
            new_avatar_full_path = os.path.join(settings.MEDIA_ROOT, new_avatar_relative_path)

            # 写入新头像文件（rename_avatar已确保文件夹存在）
            with open(new_avatar_full_path, 'wb') as f:
                for chunk in file.chunks():
                    f.write(chunk)

            # 更新用户头像字段
            user.avatar = new_avatar_relative_path
            user.save(update_fields=['avatar', 'updated_at'])

            # 拼接完整访问URL
            avatar_full_url = get_user_avatar_full_url(user, request)

            return Response({
                'code': 200,
                'msg': 'Avatar uploaded successfully',
                'data': {
                    'avatar_url': avatar_full_url,
                    'avatar_path': new_avatar_relative_path,
                    'user_folder': str(user.id)  # 返回用户文件夹名，方便前端排查
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'code': 500,
                'msg': f'Upload failed: {str(e)}',
                'data': {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ========== 1. GET 请求 → 重写 list 方法 ==========
    def list(self, request, *args, **kwargs):
        user = request.user
        if user.is_anonymous:
            return Response(
                {"code": 401, "msg": "身份认证信息未提供", "data": {}},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 拼接头像完整URL
        avatar_url = get_user_avatar_full_url(user, request)

        # 返回用户核心信息
        data = {
            'id': str(user.id),
            'user_id': user.user_id,
            'username': user.username,
            'email': user.email if user.email else "",
            'is_staff': user.is_staff,
            'avatar': avatar_url,
            'bio': user.bio if user.bio else "",
            'gender': user.gender if hasattr(user, 'gender') else "",
            'is_private': user.is_private if hasattr(user, 'is_private') else False,
        }
        return Response({
            "code": 200,
            "msg": "获取用户信息成功",
            "data": data
        }, status=status.HTTP_200_OK)

    # ========== 2. POST 请求 → 重写 create 方法 ==========
    def create(self, request, *args, **kwargs):
        return self._update_user_info(request)

    # ========== 3. PATCH 请求 → 重写 partial_update 方法 ==========
    def partial_update(self, request, *args, **kwargs):
        return self._update_user_info(request)

    # ========== 4. PUT 请求 → 重写 update 方法 ==========
    def update(self, request, *args, **kwargs):
        return self._update_user_info(request)

    # ========== 通用更新逻辑 ==========
    def _update_user_info(self, request):
        user = request.user
        if user.is_anonymous:
            return Response(
                {"code": 401, "msg": "身份认证信息未提供", "data": {}},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 允许修改的字段
        ALLOWED_FIELDS = ["user_id", "username", "email", "is_staff", "bio", "gender", "is_private", "avatar"]
        update_data = {k: v for k, v in request.data.items() if k in ALLOWED_FIELDS}

        # SQL注入防护：清理所有文本字段
        for field in ["username", "email", "bio"]:
            if field in update_data:
                update_data[field] = sanitize_input(update_data[field])

        # 数据校验
        errors = {}
        # 3.1 user_id 校验
        if "user_id" in update_data and update_data["user_id"]:
            user_id_pattern = r'^[a-zA-Z0-9]{8,50}$'
            if not re.match(user_id_pattern, update_data["user_id"]):
                errors["user_id"] = "user_id需为8-32位字母/数字组合"
            if User.objects.filter(user_id=update_data["user_id"]).exclude(pk=user.pk).exists():
                errors["user_id"] = "该user_id已被其他用户占用"
        # 3.2 username 校验（支持汉字）
        if "username" in update_data and update_data["username"]:
            # 新正则：支持汉字(\u4e00-\u9fa5)、英文、数字、下划线，长度2-20
            username_pattern = r'^[\u4e00-\u9fa5a-zA-Z0-9_]{2,20}$'
            if not re.match(username_pattern, update_data["username"]):
                # 更新错误提示，明确支持的字符类型
                errors["username"] = "用户名需为4-20位汉字、字母、数字或下划线"
            if User.objects.filter(username=update_data["username"]).exclude(pk=user.pk).exists():
                errors["username"] = "该用户名已被占用"
        # 3.3 email 校验
        if "email" in update_data and update_data["email"]:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, update_data["email"]):
                errors["email"] = "邮箱格式不正确"
            if User.objects.filter(email=update_data["email"]).exclude(pk=user.pk).exists():
                errors["email"] = "该邮箱已被其他用户绑定"
        # 3.4 is_staff 校验
        if "is_staff" in update_data:
            if not isinstance(update_data["is_staff"], bool):
                errors["is_staff"] = "是否管理员必须为布尔值（true/false）"
            if not user.is_superuser and update_data["is_staff"] != user.is_staff:
                errors["is_staff"] = "无权限修改管理员状态（仅超级管理员可操作）"
        # 3.5 bio 校验
        if "bio" in update_data and update_data["bio"]:
            if len(update_data["bio"]) > 200:
                errors["bio"] = "个人简介长度不能超过200个字符"
        # 3.6 gender 校验
        if "gender" in update_data and update_data["gender"]:
            valid_genders = ["male", "female", "other", ""]
            if update_data["gender"] not in valid_genders:
                errors["gender"] = "性别仅支持：male/female/other/空"
        # 3.7 is_private 校验
        if "is_private" in update_data:
            if not isinstance(update_data["is_private"], bool):
                errors["is_private"] = "隐私设置必须为布尔值（true/false）"

        # 校验失败返回
        if errors:
            return Response(
                {"code": 400, "msg": "数据校验失败", "data": errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 无更新数据返回
        if not update_data:
            return Response(
                {"code": 400, "msg": "未提供可更新的字段", "data": {}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 批量更新
        try:
            for field, value in update_data.items():
                setattr(user, field, value)
            user.save(update_fields=update_data.keys())
        except Exception as e:
            return Response(
                {"code": 500, "msg": f"更新用户信息失败：{str(e)}", "data": {}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 重新拼接头像URL
        avatar_url = get_user_avatar_full_url(user, request)

        # 返回更新后信息
        response_data = {
            'id': str(user.id),
            'user_id': user.user_id,
            'username': user.username,
            'email': user.email if user.email else "",
            'is_staff': user.is_staff,
            'avatar': avatar_url,
            'bio': user.bio if user.bio else "",
            'gender': user.gender if hasattr(user, 'gender') else "",
            'is_private': user.is_private if hasattr(user, 'is_private') else False,
        }
        return Response(
            {"code": 200, "msg": "用户信息更新成功", "data": response_data},
            status=status.HTTP_200_OK
        )


class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        # SQL注入防护：清理用户名参数
        if "username" in request.data:
            request.data["username"] = sanitize_input(request.data["username"])

        # 验证用户登录信息（用户名/密码）
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        # 为用户创建/获取令牌（如果已存在则直接返回）
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user_id': user.pk,
            'username': user.username
        }, status=status.HTTP_200_OK)


# ========== 关注视图集 ==========
class FollowViewSet(GenericViewSet):
    """
    关注相关独立接口
    所有关注/取消关注/列表查询接口均在此，与User的detail接口完全解耦
    """
    # 添加JWT认证类，明确指定使用JWT解析Token
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]  # 所有接口都需要登录
    serializer_class = UserFollowSerializer  # 基础序列化器

    # ========== 1. 关注指定用户（POST） ==========
    @action(detail=False, methods=['post'], url_path='follow-user')
    def follow_user(self, request):
        """
        关注指定用户（独立接口）
        POST /api/v1/follow/follow-user/
        请求体：{"followed_user_id": "目标用户的user_id或UUID"}
        """
        follower = request.user
        # 获取目标用户ID（支持user_id或UUID）
        followed_id = request.data.get('followed_user_id')
        if not followed_id:
            return Response({
                'code': 400,
                'msg': '缺少参数：followed_user_id（目标用户ID）',
                'data': {}
            }, status=status.HTTP_200_OK)

        # SQL注入防护：校验目标用户ID格式
        # 因为 cppc 的id是8个8，所以 r'^[a-zA-Z0-9]{16,32}$' 改为 r'^[a-zA-Z0-9]{8,32}$'
        if not (validate_uuid(followed_id) or re.match(r'^[a-zA-Z0-9]{8,50}$', followed_id)):
            return Response({
                'code': 400,
                'msg': '目标用户ID格式非法',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)
        # 清理ID参数
        followed_id = sanitize_input(followed_id)

        try:
            # 兼容user_id和UUID两种查询方式
            try:
                followed = User.objects.get(user_id=followed_id)
            except User.DoesNotExist:
                followed = User.objects.get(id=followed_id)

            # 使用序列化器校验并创建关注关系
            serializer = UserFollowSerializer(
                data={'followed': followed.id},
                context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response({
                'code': 200,
                'msg': f'关注 {followed.username} 成功',
                'data': {
                    'followed_user_id': followed.user_id,
                    'followed_username': followed.username
                }
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({
                'code': 404,
                'msg': f'目标用户（ID：{followed_id}）不存在',
                'data': {}
            }, status=status.HTTP_200_OK)
        except (ValidationError, IntegrityError) as e:
            return Response({
                'code': 400,
                'msg': str(e),
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'code': 500,
                'msg': f'关注失败：{str(e)}',
                'data': {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ========== 2. 取消关注指定用户（DELETE） ==========
    @action(detail=False, methods=['delete'], url_path='unfollow-user')
    def unfollow_user(self, request):
        """
        取消关注指定用户（独立接口）
        DELETE /api/v1/follow/unfollow-user/
        请求体：{"followed_user_id": "目标用户的user_id或UUID"}
        """
        follower = request.user
        followed_id = request.data.get('followed_user_id')
        if not followed_id:
            return Response({
                'code': 400,
                'msg': '缺少参数：followed_user_id（目标用户ID）',
                'data': {}
            }, status=status.HTTP_200_OK)

        # SQL注入防护：校验并清理目标用户ID
        if not (validate_uuid(followed_id) or re.match(r'^[a-zA-Z0-9]{8,50}$', followed_id)):
            return Response({
                'code': 400,
                'msg': '目标用户ID格式非法',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)
        followed_id = sanitize_input(followed_id)

        try:
            # 兼容user_id和UUID
            try:
                followed = User.objects.get(user_id=followed_id)
            except User.DoesNotExist:
                followed = User.objects.get(id=followed_id)

            # 删除关注关系
            deleted, _ = UserFollow.objects.filter(follower=follower, followed=followed).delete()
            if deleted > 0:
                return Response({
                    'code': 200,
                    'msg': f'取消关注 {followed.username} 成功',
                    'data': {
                        'followed_user_id': followed.user_id,
                        'followed_username': followed.username
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'code': 400,
                    'msg': f'未关注 {followed.username}，无需取消',
                    'data': {}
                }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({
                'code': 404,
                'msg': f'目标用户（ID：{followed_id}）不存在',
                'data': {}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'code': 500,
                'msg': f'取消关注失败：{str(e)}',
                'data': {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ========== 3. 获取当前用户的关注列表（GET） ==========
    @action(detail=False, methods=['get'], url_path='following-list')
    def following_list(self, request):
        """
        获取当前用户的关注列表（独立接口）
        GET /api/v1/follow/following-list/
        """
        if request.user.is_anonymous:
            return Response({
                'code': 401,
                'msg': '身份认证信息未提供',
                'data': {}
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 查询关注关系（关联查询被关注者，避免N+1）
        follow_relations = UserFollow.objects.filter(
            follower=request.user
        ).select_related('followed').order_by('-created_at')
        followed_users = [rel.followed for rel in follow_relations]

        # 核心修复1：序列化器传递context
        list_serializer = UserFollowListItemSerializer(
            followed_users, many=True, context={'request': request}
        )

        # 核心修复2：给汇总序列化器也传递context（关键！）
        summary_serializer = FollowListSummarySerializer(
            {
                'count': len(followed_users),
                'list': followed_users  # 传递模型实例，而非序列化后的字典
            },
            context={'request': request}  # 给嵌套序列化器传递context
        )

        return Response({
            'code': 200,
            'msg': '获取关注列表成功',
            'data': summary_serializer.data
        }, status=status.HTTP_200_OK)

    # ========== 4. 获取当前用户的粉丝列表（GET） ==========
    @action(detail=False, methods=['get'], url_path='follower-list')
    def follower_list(self, request):
        """
        获取当前用户的粉丝列表（独立接口）
        GET /api/v1/follow/follower-list/
        """
        if request.user.is_anonymous:
            return Response({
                'code': 401,
                'msg': '身份认证信息未提供',
                'data': {}
            }, status=status.HTTP_401_UNAUTHORIZED)

        # 查询粉丝关系（关联查询粉丝用户，避免N+1）
        follower_relations = UserFollow.objects.filter(
            followed=request.user
        ).select_related('follower').order_by('-created_at')
        followers = [rel.follower for rel in follower_relations]

        # 核心修复1：序列化器传递context
        list_serializer = UserFollowListItemSerializer(
            followers, many=True, context={'request': request}
        )

        # 核心修复2：给汇总序列化器传递context+模型实例
        summary_serializer = FollowListSummarySerializer(
            {
                'count': len(followers),
                'list': followers  # 传递模型实例
            },
            context={'request': request}  # 传递context
        )

        return Response({
            'code': 200,
            'msg': '获取粉丝列表成功',
            'data': summary_serializer.data
        }, status=status.HTTP_200_OK)

    # ========== 5. 判断当前用户是否关注指定用户（GET） ==========
    @action(detail=False, methods=['get'], url_path='is-followed')
    def is_followed(self, request):
        """
        判断当前用户是否关注指定用户（独立接口）
        GET /api/v1/follow/is-followed/?followed_user_id=目标用户ID
        """
        # 新增：兜底判断
        if request.user.is_anonymous:
            return Response({
                'code': 401,
                'msg': '身份认证信息未提供',
                'data': {}
            }, status=status.HTTP_401_UNAUTHORIZED)

        followed_id = request.query_params.get('followed_user_id')
        if not followed_id:
            return Response({
                'code': 400,
                'msg': '缺少参数：followed_user_id（目标用户ID）',
                'data': {}
            }, status=status.HTTP_200_OK)

        # SQL注入防护：校验并清理目标用户ID
        if not (validate_uuid(followed_id) or re.match(r'^[a-zA-Z0-9]{8,50}$', followed_id)):
            return Response({
                'code': 400,
                'msg': '目标用户ID格式非法',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)
        followed_id = sanitize_input(followed_id)

        try:
            # 兼容user_id和UUID
            try:
                followed = User.objects.get(user_id=followed_id)
            except User.DoesNotExist:
                followed = User.objects.get(id=followed_id)

            # 检查关注关系
            is_followed = UserFollow.objects.filter(
                follower=request.user, followed=followed
            ).exists()

            # 序列化返回
            serializer = IsFollowedSerializer({
                'is_followed': is_followed,
                'target_username': followed.username,
                'target_user_id': followed.user_id
            })

            return Response({
                'code': 200,
                'msg': '查询关注状态成功',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({
                'code': 404,
                'msg': f'目标用户（ID：{followed_id}）不存在',
                'data': {}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'code': 500,
                'msg': f'查询关注状态失败：{str(e)}',
                'data': {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ========== 6. 取消某位粉丝（GET） ==========
    @action(detail=False, methods=['delete'], url_path='remove-follower')
    def remove_follower(self, request):
        """
        移除粉丝（取消他人关注我）
        DELETE /api/v1/auth/user/follow/remove-follower/
        请求体：{"follower_user_id": "粉丝的user_id或UUID"}
        """
        # 新增：兜底判断
        if request.user.is_anonymous:
            return Response({
                'code': 401,
                'msg': '身份认证信息未提供',
                'data': {}
            }, status=status.HTTP_401_UNAUTHORIZED)

        follower_id = request.data.get('follower_user_id')
        if not follower_id:
            return Response({
                'code': 400,
                'msg': '缺少参数：follower_user_id（粉丝用户ID）',
                'data': {}
            }, status=status.HTTP_200_OK)

        # SQL注入防护
        if not (validate_uuid(follower_id) or re.match(r'^[a-zA-Z0-9]{8,50}$', follower_id)):
            return Response({
                'code': 400,
                'msg': '粉丝ID格式非法',
                'data': {}
            }, status=status.HTTP_400_BAD_REQUEST)
        follower_id = sanitize_input(follower_id)

        try:
            # 兼容user_id和UUID查询粉丝
            try:
                follower = User.objects.get(user_id=follower_id)
            except User.DoesNotExist:
                follower = User.objects.get(id=follower_id)

            # 删除粉丝关系（followed=当前用户，follower=粉丝）
            deleted, _ = UserFollow.objects.filter(
                followed=request.user,
                follower=follower
            ).delete()

            if deleted > 0:
                return Response({
                    'code': 200,
                    'msg': f'移除粉丝 {follower.username} 成功',
                    'data': {}
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'code': 400,
                    'msg': f'{follower.username} 并非你的粉丝',
                    'data': {}
                }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({
                'code': 404,
                'msg': f'粉丝用户（ID：{follower_id}）不存在',
                'data': {}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'code': 500,
                'msg': f'移除粉丝失败：{str(e)}',
                'data': {}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
