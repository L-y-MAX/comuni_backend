#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/1/9 17:36
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : serializers.py
# @Version : 0.0.1 (SemVer规范：主版本.次版本.修订号)
# @Project : KnowledgeBase
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
#     [功能描述] 
#     [技术架构] 
# ----------------------------------------------------------------------------
from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (User, NodeTag, KnowledgeBase,
                     KnowledgeNode, NodeHistory, KnowledgeShare,
                     Comment, CommentType, CommentNotification,
                     NodeComment, NodeCommentNotification, CommentTypeChoices,
                     UserFollowKnowledgeBase)


class NodeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodeTag
        fields = ["id", "name", "color"]  # "__all__"  # 生产环境建议显式指定字段

# 标签迷你序列化器（用于节点嵌套展示）
class NodeTagMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodeTag
        fields = ["id", "name", "color"]

# 知识库迷你序列化器（列表展示用）
class KnowledgeBaseMiniSerializer(serializers.ModelSerializer):
    """精简版知识库序列化器，用于列表展示"""
    creator_username = serializers.CharField(source="creator.username", read_only=True)  # 新增创建者用户名

    class Meta:
        model = KnowledgeBase
        fields = [
            "id", "short_id", "name", "description",
            "is_public", "creator_username", "created_at", "updated_at"
        ]

class KnowledgeBaseSerializer(serializers.ModelSerializer):
    creator_username = serializers.CharField(source="creator.username", read_only=True)
    class Meta:
        model = KnowledgeBase
        # fields = "__all__"  # 生产环境建议显式指定字段
        fields = [
            "id", "short_id", "name", "description", "creator",
            "creator_username", "is_public", "created_at", "updated_at"
        ]

class KnowledgeNodeSerializer(serializers.ModelSerializer):
    """节点序列化器（补充创建者user_id和知识库名称）"""
    """知识库节点序列化器，支持标签嵌套展示"""
    node_type_text = serializers.CharField(source="get_node_type_display", read_only=True)  # 节点类型中文
    editor_mode_text = serializers.CharField(source="get_editor_mode_display", read_only=True)  # 编辑模式中文
    tags = NodeTagMiniSerializer(many=True, read_only=True)  # 嵌套标签信息
    creator_username = serializers.CharField(source="creator.username", read_only=True)  # 创建者用户名
    parent_node_name = serializers.CharField(source="parent_node.name", read_only=True, allow_null=True, default='未知')  # 父节点名称

    # 新增：通过外键关联获取用户短ID（creator是User外键，user_id是User模型的自定义字段）
    creator_user_id = serializers.CharField(source='creator.user_id', read_only=True, default='未知')
    # 新增：通过外键关联获取知识库名称（knowledge_base是KnowledgeBase外键，name是知识库名称字段）
    knowledge_base_name = serializers.CharField(source='knowledge_base.name', read_only=True, default='无')

    class Meta:
        model = KnowledgeNode
        # 保留原有字段 + 新增两个字段（creator_user_id/knowledge_base_name）
        fields = [
            'id', 'name', 'content', 'description', 'knowledge_base_id',
            'creator', 'knowledge_base', 'creator_user_id', 'creator_username',
            'knowledge_base_name', "short_id", "parent_node", "parent_node_name",
            "node_type", "node_type_text", "editor_mode", "editor_mode_text",
            "path", "tags", "sort_order", "created_at", "updated_at"
        ]
        read_only_fields = ["path", "short_id"]  # 路径和短ID自动生成，禁止前端修改
        # 可选：设置默认值，避免字段为空
        extra_kwargs = {
            'creator_user_id': {'default': '未知'},
            'knowledge_base_name': {'default': '无'}
        }


class NodeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = NodeHistory
        fields = "__all__"


class KnowledgeShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeShare
        fields = "__all__"


# ===================== 简易用户信息序列化器（避免冗余） =====================
class UserSimpleSerializer(serializers.ModelSerializer):
    """用户简易信息序列化器（返回核心字段）"""

    class Meta:
        model = User
        fields = ["id", "username", "avatar"]  # 按你的User模型字段调整，avatar为可选
        extra_kwargs = {"avatar": {"default": None}}


# ===================== 用户关注知识库序列化器 =====================
class UserFollowKnowledgeBaseSerializer(serializers.ModelSerializer):
    """用户关注知识库序列化器"""
    # 嵌套扩展字段（提升前端可读性）
    user_info = UserSimpleSerializer(source="user", read_only=True)
    knowledge_base_info = KnowledgeBaseSerializer(source="knowledge_base", read_only=True)
    # 简化显示字段（可选）
    knowledge_base_name = serializers.CharField(source="knowledge_base.name", read_only=True, default="未知")
    user_name = serializers.CharField(source="user.username", read_only=True, default="未知")

    class Meta:
        model = UserFollowKnowledgeBase
        fields = [
            "id", "user", "user_info", "user_name",
            "knowledge_base", "knowledge_base_info", "knowledge_base_name",
            "follow_time", "unfollow_time", "is_active"
        ]
        # 只读字段（自动生成/关联）
        read_only_fields = ["id", "user", "follow_time"]
        # 默认值配置
        extra_kwargs = {
            "is_active": {"default": True},
            "unfollow_time": {"allow_null": True, "default": None},
            "knowledge_base_name": {"default": "未知"},
            "user_name": {"default": "未知"}
        }

    def validate(self, attrs):
        """自定义校验逻辑"""
        # 获取当前登录用户
        user = self.context.get("request").user if self.context.get("request") else None

        # 1. 校验：同一用户不能重复关注同一有效知识库
        if attrs.get("is_active", True) and user and "knowledge_base" in attrs:
            exists = UserFollowKnowledgeBase.objects.filter(
                user=user,
                knowledge_base=attrs["knowledge_base"],
                is_active=True
            ).exists()
            if exists:
                raise ValidationError("你已关注该知识库，无需重复关注")

        # 2. 校验取消关注的时间逻辑
        instance = self.instance
        if instance:
            is_active = attrs.get("is_active", instance.is_active)
            unfollow_time = attrs.get("unfollow_time", instance.unfollow_time)

            # 取消关注时自动填充取消时间
            if not is_active and not unfollow_time:
                attrs["unfollow_time"] = timezone.now()
            # 恢复关注时清空取消时间
            if is_active and unfollow_time:
                attrs["unfollow_time"] = None

        return attrs

    def create(self, validated_data):
        """重写创建逻辑：优先恢复已取消的记录，而非新建"""
        user = self.context["request"].user
        knowledge_base = validated_data["knowledge_base"]

        # 检查是否有已取消的关注记录
        canceled_record = UserFollowKnowledgeBase.objects.filter(
            user=user,
            knowledge_base=knowledge_base,
            is_active=False
        ).first()

        if canceled_record:
            # 恢复关注
            canceled_record.is_active = True
            canceled_record.unfollow_time = None
            canceled_record.save()
            return canceled_record
        else:
            # 新建关注记录（强制关联当前用户）
            validated_data["user"] = user
            return super().create(validated_data)


# ===================== 回复评论序列化器（CommentAnswerVO） =====================
class CommentAnswerSerializer(serializers.ModelSerializer):
    """回复评论序列化器（对应原文的CommentAnswerVO）"""
    # 评论者信息（关联commented_by字段，映射为user_info）
    user_info = UserSimpleSerializer(source="commented_by", read_only=True)
    # 被回复用户信息（关联to_user字段，兼容你的命名习惯保留answer_user_info）
    answer_user_info = UserSimpleSerializer(source="to_user", read_only=True)
    # 兼容你的article_id命名：映射模型的knowledge_base.id（核心适配）
    article_id = serializers.UUIDField(source="knowledge_base.id", read_only=True)
    # 补充：知识库名称（提升前端可读性）
    knowledge_base_name = serializers.CharField(source="knowledge_base.name", read_only=True, default='无')

    class Meta:
        model = Comment
        fields = [
            "id", "article_id", "knowledge_base_name", "user_info", "answer_user_info",
            "root_id", "comment_text", "hot", "type", "comment_date", "updated_at"
        ]
        # 可选：设置默认值，避免字段为空
        extra_kwargs = {
            "knowledge_base_name": {"default": "无"},
            "hot": {"default": 0},
            "type": {"default": CommentType.ANSWER}
        }


# ===================== 根评论序列化器（CommentVO） =====================
class CommentRootSerializer(serializers.ModelSerializer):
    """根评论序列化器（对应原文的CommentVO）：包含回复列表"""
    # 评论者信息（关联commented_by字段）
    user_info = UserSimpleSerializer(source="commented_by", read_only=True)
    # 兼容你的article_id命名：映射模型的knowledge_base.id
    article_id = serializers.UUIDField(source="knowledge_base.id", read_only=True)
    # 补充：知识库名称
    knowledge_base_name = serializers.CharField(source="knowledge_base.name", read_only=True, default='无')
    # 该根评论下的回复列表（关联comment_set，按需加载时可注释，分页加载）
    answer_comment_list = CommentAnswerSerializer(source="comment_set", many=True, read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id", "article_id", "knowledge_base_name", "user_info", "root_id",
            "comment_text", "hot", "type", "comment_date", "updated_at",
            "answer_comment_list"
        ]
        # 可选：设置默认值，避免字段为空
        extra_kwargs = {
            "knowledge_base_name": {"default": "无"},
            "hot": {"default": 0},
            "type": {"default": CommentType.ROOT},
            "root_id": {"read_only": True}  # 根评论root_id自动生成，前端无需传参
        }


# ===================== 评论通知序列化器 =====================
class CommentNotificationSerializer(serializers.ModelSerializer):
    """评论通知序列化器：返回通知核心信息 + 扩展关联字段"""
    # 被通知用户信息（嵌套简易用户信息）
    notified_user_info = UserSimpleSerializer(source="notified_user", read_only=True)
    # 回复评论的核心信息（扩展字段，提升前端可读性）
    reply_comment_text = serializers.CharField(source="reply_comment.comment_text", read_only=True, default='')
    reply_comment_id = serializers.UUIDField(source="reply_comment.id", read_only=True)
    # 评论者用户名（扩展字段）
    replier_username = serializers.CharField(source="reply_comment.commented_by.username", read_only=True,
                                             default='未知')
    # 关联知识库名称（扩展字段）
    knowledge_base_name = serializers.CharField(source="reply_comment.knowledge_base.name", read_only=True,
                                                default='无')

    class Meta:
        model = CommentNotification
        fields = [
            "id", "content", "is_read", "created_at",
            "notified_user_info", "reply_comment_text", "reply_comment_id",
            "replier_username", "knowledge_base_name"  # 扩展字段
        ]
        # 可选：设置默认值，避免字段为空
        extra_kwargs = {
            "reply_comment_text": {"default": ""},
            "replier_username": {"default": "未知"},
            "knowledge_base_name": {"default": "无"},
            "is_read": {"default": False}
        }


# ===================== 评论创建专用序列化器（前端提交数据用） =====================
class CommentCreateSerializer(serializers.ModelSerializer):
    """评论创建序列化器：仅保留前端需要提交的字段，适配创建逻辑"""
    # 手动传入的字段（创建时必传）
    article_id = serializers.UUIDField(write_only=True, label="所属知识库ID")
    to_user_id = serializers.UUIDField(write_only=True, label="被回复用户ID", required=False, allow_null=True)

    class Meta:
        model = Comment
        fields = [
            "comment_text", "type", "root_id", "article_id", "to_user_id"
        ]
        # 校验规则
        extra_kwargs = {
            "comment_text": {"required": True, "error_messages": {"blank": "评论内容不能为空"}},
            "type": {"required": True, "error_messages": {"invalid_choice": "评论类型只能是root或answer"}},
            "root_id": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        """校验评论创建规则"""
        # 回复评论必须传root_id和to_user_id
        if attrs.get("type") == CommentType.ANSWER:
            if not attrs.get("root_id"):
                raise serializers.ValidationError("回复评论必须指定root_id（根评论ID）")
            if not attrs.get("to_user_id"):
                raise serializers.ValidationError("回复评论必须指定to_user_id（被回复用户ID）")
        # 根评论不能传to_user_id
        if attrs.get("type") == CommentType.ROOT and attrs.get("to_user_id"):
            raise serializers.ValidationError("根评论无需指定被回复用户ID")
        return attrs

    def create(self, validated_data):
        """重写创建逻辑：映射article_id到knowledge_base，关联当前用户"""
        # 提取并删除write_only字段
        article_id = validated_data.pop("article_id")
        to_user_id = validated_data.pop("to_user_id", None)

        # 关联知识库（article_id对应knowledge_base的id）
        try:
            knowledge_base = KnowledgeBase.objects.get(id=article_id)
        except KnowledgeBase.DoesNotExist:
            raise serializers.ValidationError(f"知识库ID {article_id} 不存在")

        # 关联被回复用户（如有）
        to_user = None
        if to_user_id:
            try:
                to_user = User.objects.get(id=to_user_id)
            except User.DoesNotExist:
                raise serializers.ValidationError(f"用户ID {to_user_id} 不存在")

        # 创建评论
        comment = Comment.objects.create(
            **validated_data,
            knowledge_base=knowledge_base,
            commented_by=self.context["request"].user,
            to_user=to_user
        )
        return comment


# 知识节点（文章）序列化器（适配完整模型）
class KnowledgeNodeListSerializer(serializers.ModelSerializer):
    """新增接口专用序列化器，包含所有核心字段"""
    # 关联知识库信息
    knowledge_base_id = serializers.UUIDField(source="knowledge_base.id", read_only=True)
    knowledge_base_name = serializers.CharField(source="knowledge_base.name", read_only=True)
    knowledge_base_short_id = serializers.CharField(source="knowledge_base.short_id", read_only=True)
    # 创建者信息
    creator_id = serializers.UUIDField(source="creator.id", read_only=True)
    creator_username = serializers.CharField(source="creator.username", read_only=True)
    # 父节点信息（简化返回）
    parent_node_id = serializers.UUIDField(source="parent_node.id", read_only=True, allow_null=True)
    parent_node_name = serializers.CharField(source="parent_node.name", read_only=True, allow_null=True)
    # 标签信息（嵌套序列化）
    tags = NodeTagSerializer(many=True, read_only=True)
    # 节点类型中文显示
    node_type_display = serializers.CharField(source="get_node_type_display", read_only=True)
    # 编辑模式中文显示
    editor_mode_display = serializers.CharField(source="get_editor_mode_display", read_only=True)

    class Meta:
        model = KnowledgeNode
        # 包含你模型的所有核心字段，适配前端展示/交互
        fields = [
            "id", "short_id", "name",
            # 知识库关联
            "knowledge_base", "knowledge_base_id", "knowledge_base_name", "knowledge_base_short_id",
            # 父节点关联
            "parent_node", "parent_node_id", "parent_node_name",
            # 节点类型/编辑模式
            "node_type", "node_type_display", "editor_mode", "editor_mode_display",
            # 内容/描述
            "content", "description",
            # 物化路径/排序
            "path", "sort_order",
            # 标签
            "tags",
            # 创建者
            "creator", "creator_id", "creator_username",
            # 时间戳
            "created_at", "updated_at"
        ]


class KnowledgeNodeSimpleSerializer(serializers.ModelSerializer):
    """文章简易序列化器：仅返回评论关联的文章信息"""

    class Meta:
        model = KnowledgeNode
        fields = ["id", "name", "short_id"]


# ===================== 回复评论序列化器 =====================
class NodeCommentAnswerSerializer(serializers.ModelSerializer):
    """文章回复评论序列化器（适配指定根评论的回复API）"""
    # 嵌套关联字段（保留你原有的核心字段）
    user_info = UserSimpleSerializer(source="commented_by", read_only=True)
    answer_user_info = UserSimpleSerializer(source="to_user", read_only=True)
    article_id = serializers.UUIDField(source="article.id", read_only=True)
    article_name = serializers.CharField(source="article.name", read_only=True, default="未知")

    # 新增：只写字段（创建回复时传入被回复用户ID，用于绑定to_user）
    to_user_id = serializers.UUIDField(write_only=True, required=True, help_text="被回复用户的ID")

    class Meta:
        model = NodeComment
        fields = [
            "id", "article_id", "article_name", "user_info", "answer_user_info",
            "root_id", "comment_text", "hot", "type", "comment_date", "updated_at",
            "to_user_id"  # 新增：添加只写字段到返回字段列表
        ]
        extra_kwargs = {
            "article_name": {"default": "未知"},
            "type": {"default": CommentTypeChoices.ANSWER, "read_only": True},  # 固定为回复类型，只读
            "root_id": {"read_only": True},  # 由视图自动填充，前端无需传
            "commented_by": {"read_only": True},  # 关联当前登录用户，只读
            "comment_date": {"read_only": True},  # 自动生成，只读
            "updated_at": {"read_only": True},  # 自动更新，只读
            "hot": {"read_only": True},  # 热评权重默认0，后端控制
        }

    def validate_to_user_id(self, value):
        """校验：被回复用户必须存在"""
        try:
            User.objects.get(pk=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"被回复用户ID {value} 不存在")
        return value

    def validate_comment_text(self, value):
        """校验：评论内容不能为空"""
        if not value.strip():
            raise serializers.ValidationError("评论内容不能为空")
        return value

    def create(self, validated_data):
        """重写创建逻辑：
        1. 从validated_data中移除to_user_id，查询并绑定to_user
        2. 自动设置评论类型为ANSWER
        3. 保留视图层传入的root_id、article、commented_by等字段
        """
        # 1. 取出并删除只写字段to_user_id，查询被回复用户
        to_user_id = validated_data.pop("to_user_id")
        to_user = User.objects.get(pk=to_user_id)

        # 2. 强制设置评论类型为回复（避免前端传错）
        validated_data["type"] = CommentTypeChoices.ANSWER

        # 3. 绑定被回复用户
        validated_data["to_user"] = to_user

        # 4. 创建并返回回复评论
        return super().create(validated_data)


# ===================== 根评论序列化器 =====================
class NodeCommentRootSerializer(serializers.ModelSerializer):
    """文章根评论序列化器（包含回复列表）"""
    # 嵌套关联字段
    user_info = UserSimpleSerializer(source="commented_by", read_only=True)
    article_id = serializers.UUIDField(source="article.id", read_only=True)
    article_name = serializers.CharField(source="article.name", read_only=True, default="未知")
    # 嵌套回复列表（当前根评论下的所有回复）
    answer_comment_list = NodeCommentAnswerSerializer(
        source="node_comments",  # 关联NodeComment的root_id
        many=True,
        read_only=True
    )

    class Meta:
        model = NodeComment
        fields = [
            "id", "article_id", "article_name", "user_info", "root_id",
            "comment_text", "hot", "type", "comment_date", "updated_at",
            "answer_comment_list"
        ]
        extra_kwargs = {
            "article_name": {"default": "未知"},
            "hot": {"default": 0},
            "type": {"default": CommentTypeChoices.ROOT},
            "root_id": {"read_only": True}  # 根评论root_id自动等于自身ID
        }


# ===================== 评论创建专用序列化器 =====================
class NodeCommentCreateSerializer(serializers.ModelSerializer):
    """文章评论创建序列化器（前端提交数据专用）"""
    # 必传字段（write_only）
    article_id = serializers.UUIDField(write_only=True, label="文章ID（KnowledgeNode ID）", required=True)
    to_user_id = serializers.UUIDField(write_only=True, label="被回复用户ID", required=False, allow_null=True)

    class Meta:
        model = NodeComment
        fields = [
            "comment_text", "type", "root_id", "article_id", "to_user_id"
        ]
        extra_kwargs = {
            "comment_text": {
                "required": True,
                "error_messages": {"blank": "评论内容不能为空"}
            },
            "type": {
                "required": True,
                "error_messages": {"invalid_choice": "评论类型仅支持root/answer"}
            },
            "root_id": {"required": False, "allow_null": True}
        }

    def validate(self, attrs):
        """校验评论创建规则"""
        # 回复评论必须传root_id和to_user_id
        if attrs.get("type") == CommentTypeChoices.ANSWER:
            if not attrs.get("root_id"):
                raise serializers.ValidationError("回复评论必须指定root_id（根评论ID）")
            if not attrs.get("to_user_id"):
                raise serializers.ValidationError("回复评论必须指定to_user_id（被回复用户ID）")
        # 根评论禁止传to_user_id
        if attrs.get("type") == CommentTypeChoices.ROOT and attrs.get("to_user_id"):
            raise serializers.ValidationError("根评论无需指定被回复用户ID")
        return attrs

    def create(self, validated_data):
        """重写创建逻辑：绑定文章、用户、自动设置根评论ID"""
        # 提取write_only字段
        article_id = validated_data.pop("article_id")
        to_user_id = validated_data.pop("to_user_id", None)

        # 校验文章存在
        try:
            article = KnowledgeNode.objects.get(id=article_id)
        except KnowledgeNode.DoesNotExist:
            raise serializers.ValidationError(f"文章ID {article_id} 不存在")

        # 校验被回复用户存在（如有）
        to_user = None
        if to_user_id:
            try:
                to_user = User.objects.get(id=to_user_id)
            except User.DoesNotExist:
                raise serializers.ValidationError(f"用户ID {to_user_id} 不存在")

        # 创建评论
        comment = NodeComment.objects.create(
            **validated_data,
            article=article,
            commented_by=self.context["request"].user,
            to_user=to_user,
        )

        # 根评论：自动将root_id设为自身ID
        if comment.type == CommentTypeChoices.ROOT:
            comment.root_id = comment.id
            comment.save(update_fields=["root_id"])

        return comment


# ===================== 评论通知序列化器 =====================
class NodeCommentNotificationSerializer(serializers.ModelSerializer):
    """文章评论通知序列化器"""
    # 嵌套扩展字段
    notified_user_info = UserSimpleSerializer(source="notified_user", read_only=True)
    reply_comment_text = serializers.CharField(source="reply_comment.comment_text", read_only=True, default="")
    reply_comment_id = serializers.UUIDField(source="reply_comment.id", read_only=True)
    replier_username = serializers.CharField(source="reply_comment.commented_by.username", read_only=True,
                                             default="未知")
    article_name = serializers.CharField(source="reply_comment.article.name", read_only=True, default="未知")

    class Meta:
        model = NodeCommentNotification
        fields = [
            "id", "notified_user_info", "reply_comment_text", "reply_comment_id",
            "replier_username", "article_name", "content", "is_read", "created_at"
        ]
        extra_kwargs = {
            "reply_comment_text": {"default": ""},
            "replier_username": {"default": "未知"},
            "article_name": {"default": "未知"},
            "is_read": {"default": False}
        }