#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2025/12/10 8:16
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : serializers.py
# @Version : 0.0.1 (SemVer规范：主版本.次版本.修订号)
# @Project : comuni_backend
# @IDE     : PyCharm 
# ----------------------------------------------------------------------------
# 协作规范区
# @Dependencies: 
#     - requests>=2.25.1 (通过`requirements.txt`管理)
#     - package<version (版本冲突规避说明将在此写明，如无则通过`requirements.txt`配置)
# @finish      : 
#     - [高优先级] 示例：实现多线程优化 (负责人: @Skixkk)
#     - [待评审] 示例：重构数据验证逻辑XXX (截止日期: 2025-0X-XX)
# ----------------------------------------------------------------------------
# 法律声明区
# @License     : MIT
# @SPDX-License-Identifier: MIT
# @Copyright   : Copyright (c) 2025 by Skixkk , All Rights Reserved
# @Description : [Functional description of the file]
#     [功能描述] User 序列化器
#     [技术架构] 
# ----------------------------------------------------------------------------
from rest_framework import serializers
from django.db import IntegrityError
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import VipInfo, UserFollow

User = get_user_model()


class UserIDUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["user_id"]

    def validate_user_id(self, value):
        """校验用户ID：格式+唯一性"""
        # 格式校验（和模型层一致，双重保障）
        if not value.isalnum():
            raise serializers.ValidationError("用户ID仅支持数字和字母组合")
        if len(value) > 20:
            raise serializers.ValidationError("用户ID长度不能超过20位")
        # 唯一性校验（排除当前用户）
        user = self.instance
        if User.objects.filter(user_id=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(f"用户ID {value} 已被使用")
        return value


# Serializers define the API representation.
class UserSerializer(serializers.HyperlinkedModelSerializer):
    #  显式定义avatar为ImageField，确保返回完整URL
    avatar = serializers.ImageField(read_only=True)
    # 头像文本字段（用于前端无头像时显示）
    avatar_text = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'user_id', 'email', 'avatar', 'avatar_text', 'gender', 'bio', 'is_private',
                  'is_staff']

    def get_avatar_text(self, obj):
        """生成头像占位文字（用户名首字母大写）"""
        # 1. 获取用户名，若obj.username为None则赋值为空字符串
        username = obj.username or ""
        # 2. 核心逻辑：
        # - 先去除用户名首尾的空格（strip()）
        # - 取第一个字符（[:1]）
        # - 转为大写（upper()）
        # - 如果username为空（或处理后无字符），则返回"?"
        return username.strip()[:1].upper() if username else "?"


class TOTPSetupSerializer(serializers.Serializer):
    """TOTP绑定序列化器"""
    code = serializers.CharField(max_length=6, required=True)


class TOTPVerifySerializer(serializers.Serializer):
    """TOTP验证序列化器"""
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True)
    totp_code = serializers.CharField(max_length=6, required=True)


class BackupCodeSerializer(serializers.Serializer):
    """备用验证码序列化器"""
    code = serializers.CharField(max_length=6, required=True)


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name', "url", 'permissions']


# 会员信息序列化器（适配前端返回格式）
class VipInfoSerializer(serializers.ModelSerializer):
    # 格式化过期时间为字符串（YYYY-MM-DD），匹配前端 formatDate 方法
    expireDate = serializers.SerializerMethodField()
    isVip = serializers.BooleanField(source='is_vip')  # 映射到模型的 is_vip 字段

    class Meta:
        model = VipInfo
        fields = ['isVip', 'expireDate']

    def get_expireDate(self, obj):
        """格式化过期时间"""
        if obj.expire_date:
            return obj.expire_date.strftime('%Y-%m-%d')
        return None


# 统一响应格式序列化器（匹配前端 ApiResponse 接口）
class ApiResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField(required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_null=True)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username  # 添加自定义字段
        token['user_id'] = user.user_id  # 添加自定义字段
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data.update({'message': '登录成功', 'code': 200})
        return data


# 用户详情序列化器（含关注/粉丝数）
class UserDetailSerializer(serializers.ModelSerializer):
    #  显式定义avatar为ImageField，确保返回完整URL
    avatar = serializers.ImageField(read_only=True)
    # 头像文本字段
    avatar_text = serializers.SerializerMethodField()
    # 关联自定义字段
    user_id = serializers.CharField(read_only=True)
    gender = serializers.CharField(source='get_gender_display', read_only=True)  # 显示中文性别（男/女/隐藏）
    following_count = serializers.SerializerMethodField()  # 关注数
    follower_count = serializers.SerializerMethodField()  # 粉丝数

    class Meta:
        model = User
        fields = ['id', 'username', 'user_id', 'email', 'gender', 'bio', 'avatar', 'avatar_text', 'following_count',
                  'follower_count']

    def get_following_count(self, obj):
        """获取用户关注的人数"""
        return obj.following.count()

    def get_follower_count(self, obj):
        """获取用户的粉丝数"""
        return obj.followers.count()

    def get_avatar_text(self, obj):
        """生成头像占位文字（用户名首字母大写）"""
        username = obj.username or ""
        return username.strip()[:1].upper() if username else "?"


# ========== 1. 关注操作核心序列化器 ==========
class UserFollowSerializer(serializers.ModelSerializer):
    """
    关注操作序列化器（适配关注/取消关注的POST/DELETE操作）
    自动填充当前登录用户为follower，校验关注逻辑（禁止关注自己、重复关注）
    """

    class Meta:
        model = UserFollow
        fields = ['id', 'follower', 'followed', 'created_at']
        read_only_fields = ['id', 'created_at', 'follower']  # follower 由当前用户自动填充

    def create(self, validated_data):
        """重写create：自动填充当前登录用户为关注者，并捕获校验异常"""
        # 从上下文获取当前登录用户（FollowViewSet中已传入context）
        validated_data['follower'] = self.context['request'].user

        # 调用模型的clean和save，捕获异常并转为序列化器异常
        try:
            return super().create(validated_data)
        except ValidationError as e:
            raise serializers.ValidationError(e.message)
        except IntegrityError:
            followed_username = validated_data['followed'].username
            raise serializers.ValidationError(f"已关注 {followed_username}，无需重复关注")


# ========== 2. 关注/粉丝列表项序列化器 ==========
class UserFollowListItemSerializer(serializers.ModelSerializer):
    """
    关注/粉丝列表项序列化器（适配following-list/follower-list接口）
    返回前端展示所需的精简字段，无需前端二次处理
    """
    # 映射模型字段（适配前端命名习惯）
    user_id = serializers.CharField(read_only=True)  # 自定义用户ID（非UUID）
    username = serializers.CharField(read_only=True)
    # 核心修复：改用SerializerMethodField处理头像，保证URL拼接和空值处理
    avatar = serializers.SerializerMethodField()
    avatar_text = serializers.SerializerMethodField()  # 头像占位文字（用户名首字母）
    gender_text = serializers.SerializerMethodField()  # 性别中文（男/女/隐藏/未填写）
    is_followed = serializers.SerializerMethodField()  # 区分关注列表/粉丝列表返回状态
    is_private = serializers.BooleanField(read_only=True, default=False)  # 兼容无该字段场景

    class Meta:
        model = User
        fields = ['avatar', 'avatar_text', 'id', 'user_id',
                  'username', 'gender_text', 'is_followed', 'is_private']

    def get_avatar(self, obj):
        """返回头像完整URL，无头像返回空字符串（终极修复）"""
        # 1. 获取request上下文（拼接URL必需）
        request = self.context.get('request')
        if not request:
            print("警告：request上下文缺失")
            return ""

        # 2. 兼容模型实例和字典（优先处理模型实例）
        avatar_path = ""
        if isinstance(obj, dict):
            avatar_path = obj.get('avatar', "")
        else:
            # 核心修复：直接使用avatar.name（已确认有值）
            if hasattr(obj, 'avatar') and obj.avatar:
                try:
                    avatar_path = obj.avatar.name  # 直接取存储路径（如avatars/xxx.png）
                except Exception as e:
                    print(f"获取avatar.name失败：{e}")
                    avatar_path = ""

        # 3. 无头像路径返回空字符串
        if not avatar_path or avatar_path.strip() == "":
            return ""

        # 4. 拼接完整绝对URL（核心：手动拼接，避免依赖avatar.url）
        try:
            if request:
                # 有request：返回绝对URL
                # 方式1：使用request.build_absolute_uri拼接MEDIA_URL + 存储路径
                from django.conf import settings
                # 拼接MEDIA_URL和avatar_path（处理MEDIA_URL末尾是否有/的情况）
                media_url = settings.MEDIA_URL.rstrip('/') + '/'
                relative_url = media_url + avatar_path.lstrip('/')
                # 转为绝对URL
                absolute_url = request.build_absolute_uri(relative_url)
                return absolute_url
            else:
                # 无request：返回相对URL（前端拼接域名） Relative URL
                from django.conf import settings
                relative_url = settings.MEDIA_URL + avatar_path.lstrip('/')
                # 转为相对URL
                return relative_url

        except Exception as e:
            print(f"拼接URL失败：{e}")
            # 兜底：返回相对路径（前端可自行拼接域名）
            return avatar_path

    def get_avatar_text(self, obj):
        """生成头像占位文字（用户名首字母大写）"""
        #  兼容字典/模型实例两种类型
        if isinstance(obj, dict):
            username = obj.get('username', "")
        else:
            username = obj.username or ""
        return username.strip()[:1].upper() if username else "?"

    def get_gender_text(self, obj):
        """将模型中的gender值转为中文（适配User模型的GENDER_CHOICES）"""
        gender_map = {
            "male": "男",
            "female": "女",
            "other": "隐藏",
            "": "未填写"
        }
        #  兼容字典/模型实例两种类型
        if isinstance(obj, dict):
            gender = obj.get('gender', "")
        else:
            gender = obj.gender or ""
        return gender_map.get(gender, "未填写")

    def get_is_followed(self, obj):
        """判断当前登录用户是否关注该用户（仅粉丝列表需要）"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        #  兼容字典/模型实例两种类型（获取目标用户ID）
        if isinstance(obj, dict):
            target_user_id = obj.get('id')
            if not target_user_id:
                return False
            # 字典场景：通过ID查询用户
            try:
                target_user = User.objects.get(pk=target_user_id)
            except User.DoesNotExist:
                return False
        else:
            target_user = obj

        # 判断当前用户是否关注该用户（关注列表必然为True）
        is_followed = UserFollow.objects.filter(follower=request.user, followed=target_user).exists()

        return is_followed


# ========== 3. 关注状态校验序列化器 ==========
class IsFollowedSerializer(serializers.Serializer):
    """
    关注状态查询序列化器（适配is-followed接口）
    返回是否关注、目标用户名、目标用户ID，适配前端按钮状态展示
    """
    is_followed = serializers.BooleanField()  # 是否关注目标用户
    target_username = serializers.CharField()  # 目标用户昵称
    target_user_id = serializers.CharField()  # 目标用户自定义ID（非UUID）


# ========== 4. 关注/粉丝列表汇总序列化器（FollowListSummarySerializer） ==========
class FollowListSummarySerializer(serializers.Serializer):
    """
    关注/粉丝列表汇总序列化器（适配following-list/follower-list接口）
    返回列表总数+列表数据，统一返回格式
    """
    count = serializers.IntegerField()  # 列表总数（关注数/粉丝数）
    list = UserFollowListItemSerializer(many=True)  # 列表数据（每个项用UserFollowListItemSerializer）


# ========== 1. 搜索结果序列化器（公开用户，仅返回基础字段） ==========
class UserSearchSerializer(serializers.ModelSerializer):
    """用户搜索序列化器（返回全部用户字段）"""
    # 补充显示用的性别文本（兼容前端gender_text字段）
    gender_text = serializers.SerializerMethodField()
    # 头像文本（取用户名首字母，兼容前端）
    avatar_text = serializers.SerializerMethodField()
    # 是否已关注（需要request上下文）
    is_followed = serializers.SerializerMethodField()
    # 关联会员信息（完整字段）
    vip_info = VipInfoSerializer(read_only=True)
    # 显式定义avatar为ImageField，确保返回完整URL
    avatar = serializers.ImageField(read_only=True)

    class Meta:
        model = User
        # fields = '__all__'  # 序列化用户模型所有字段
        # 可选：如果需要排除敏感字段，可替换为显式字段列表
        fields = ['id', 'user_id', 'username', 'email', 'gender', 'gender_text',
                  'avatar', 'avatar_text', 'bio', 'is_private', 'created_at', 'updated_at',
                  'is_followed', 'vip_info']

    def get_gender_text(self, obj):
        """转换性别编码为中文文本"""
        gender_map = {
            'male': '男',
            'female': '女',
            'other': '隐藏',
            '': '未填写',
            None: '未填写'
        }
        return gender_map.get(obj.gender, '未知')

    def get_avatar_text(self, obj):
        """生成头像显示文本（用户名首字母）"""
        if obj.username:
            return obj.username[:1].upper()
        return '?'

    def get_is_followed(self, obj):
        """判断当前登录用户是否关注该用户"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        # 检查关注关系
        return UserFollow.objects.filter(
            follower=request.user,
            followed=obj
        ).exists()


# ========== 用户详情序列化器（含关注数/粉丝数/会员信息） ==========
class DocumentMiniSerializer(serializers.Serializer):
    """文档子序列化器（适配你的知识库文档模型，按需调整）"""
    id = serializers.UUIDField()
    title = serializers.CharField()
    short_summary = serializers.CharField(allow_null=True, allow_blank=True)


class UserPersonalDetailSerializer(serializers.ModelSerializer):
    """用户详情序列化器（贴合你的模型，计算关注/粉丝数）"""
    #  显式定义avatar为ImageField，确保返回完整URL
    avatar = serializers.ImageField(read_only=True)
    # 头像文本字段
    avatar_text = serializers.SerializerMethodField()
    # 性别中文显示（适配模型choices）
    gender_text = serializers.SerializerMethodField()
    # 关注数（通过UserFollow关联计算：当前用户关注的人数）
    following_count = serializers.SerializerMethodField()
    # 粉丝数（通过UserFollow关联计算：关注当前用户的人数）
    follower_count = serializers.SerializerMethodField()
    # 会员信息（可选，按需返回）
    is_vip = serializers.SerializerMethodField()
    vip_expire_date = serializers.SerializerMethodField()
    # 该用户的知识库文档（按需关联，若有Document模型则启用）
    documents = DocumentMiniSerializer(source="documents.all", many=True, read_only=True, required=False)

    class Meta:
        model = User
        # 仅返回前端需要的字段（贴合你的模型）
        fields = [
            "avatar", "avatar_text", "username", "user_id", "email", "gender_text",
            "following_count", "follower_count", "is_vip",
            "vip_expire_date", "documents"
        ]

    # 性别中文映射
    def get_gender_text(self, obj):
        gender_map = {"male": "男", "female": "女", "other": "隐藏", "": "未填写"}
        return gender_map.get(obj.gender or "", "未填写")

    # 计算关注数：当前用户关注的人数（UserFollow中follower=当前用户的数量）
    def get_following_count(self, obj):
        return obj.following.count()  # 基于UserFollow的related_name='following'

    # 计算粉丝数：关注当前用户的人数（UserFollow中followed=当前用户的数量）
    def get_follower_count(self, obj):
        return obj.followers.count()  # 基于UserFollow的related_name='followers'

    # 是否为会员（关联VipInfo模型）
    def get_is_vip(self, obj):
        try:
            return obj.vip_info.is_vip  # 基于VipInfo的related_name='vip_info'
        except VipInfo.DoesNotExist:
            return False

    # 会员过期时间
    def get_vip_expire_date(self, obj):
        try:
            return obj.vip_info.expire_date.strftime("%Y-%m-%d %H:%M") if obj.vip_info.expire_date else None
        except VipInfo.DoesNotExist:
            return None

    # 头像文本生成方法
    def get_avatar_text(self, obj):
        """生成头像占位文字（用户名首字母大写）"""
        username = obj.username or ""
        return username.strip()[:1].upper() if username else "?"