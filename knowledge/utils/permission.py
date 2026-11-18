#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/1/6 17:16
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : permission.py
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
#     [功能描述] . 权限校验工具（核心逻辑） 创建 utils/permission.py，封装权限校验函数，供视图层调用：
#     [技术架构] 
# ----------------------------------------------------------------------------
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, status, permissions, filters
from ..models import (KnowledgeBase, KnowledgeNode, KnowledgeShare,
                      PermissionLevel, UserFollowKnowledgeBase)

def check_knowledge_permission(user, knowledge_base_id, required_permission):
    """
    校验用户对知识库的权限
    :param user: 当前登录用户
    :param knowledge_base_id: 知识库ID
    :param required_permission: 所需权限（PermissionLevel中的值，如"admin"）
    :return: 知识库实例（校验通过）/ 抛PermissionDenied异常（校验失败）
    """
    try:
        knowledge_base = KnowledgeBase.objects.get(id=knowledge_base_id)
    except KnowledgeBase.DoesNotExist:
        raise PermissionDenied("知识库不存在")

    # 核心修改：公开知识库直接授予VIEWER（只读）权限，无需关注
    if knowledge_base.is_public and required_permission == PermissionLevel.VIEWER:
        return knowledge_base  # 只要是公开知识库，无论是否关注，都有只读权限

    # 1. 知识库创建者默认拥有最高权限（管理者），无需共享记录
    if knowledge_base.creator == user:
        return knowledge_base

    # 2. 查找用户的共享记录
    try:
        share = KnowledgeShare.objects.get(
            knowledge_base=knowledge_base,
            shared_to=user
        )
    except KnowledgeShare.DoesNotExist:
        # 修改：公开知识库已无需关注，仅私有知识库提示权限不足
        if knowledge_base.is_public:
            # 公开知识库仅VIEWER权限，如需更高权限则提示
            if required_permission != PermissionLevel.VIEWER:
                raise PermissionDenied("公开知识库仅支持只读访问，如需编辑/管理权限请联系创建者")
            return knowledge_base  # 兜底：确保公开知识库VIEWER权限始终通过
        else:
            raise PermissionDenied("您没有该知识库的编辑权限, 试试其他知识库吧")

    # 3. 权限等级映射（数字越大，权限越高）
    permission_map = {
        PermissionLevel.VIEWER: 1,
        PermissionLevel.PARTICIPANT: 2,
        PermissionLevel.ADMIN: 3
    }

    # 4. 校验所需权限是否满足（如需要participant权限，admin也满足）
    if permission_map[share.permission_level] >= permission_map[required_permission]:
        return knowledge_base
    else:
        raise PermissionDenied(f"您需要{PermissionLevel(required_permission).label}权限才能执行此操作")

# 简化权限校验的辅助函数（供接口直接调用）
def require_view_permission(user, knowledge_base_id):
    """需要查看权限（所有角色都满足）"""
    return check_knowledge_permission(user, knowledge_base_id, PermissionLevel.VIEWER)

def require_edit_permission(user, knowledge_base_id):
    """需要编辑权限（participant/admin）"""
    return check_knowledge_permission(user, knowledge_base_id, PermissionLevel.PARTICIPANT)

def require_admin_permission(user, knowledge_base_id):
    """需要管理权限（仅admin）"""
    return check_knowledge_permission(user, knowledge_base_id, PermissionLevel.ADMIN)

# ===================== 自定义权限：文章评论权限 =====================
class NodeCommentPermission(permissions.BasePermission):
    """
    文章评论权限规则（适配指定根评论的回复API）：
    1. 所有接口必须传article_id/node_pk（文章ID），否则拒绝
    2. 匿名用户仅可查看公开知识库下文章的评论
    3. 登录用户可对有权限的文章发布评论
    4. 仅评论作者/文章所属知识库管理员可编辑/删除评论
    """

    def has_permission(self, request, view):
        """
        全局权限校验（接口访问权限）：
        - 适配URL路径参数：node_pk（你的回复API路径参数）/article_id（原有参数）
        - 兼容query_params/data参数
        """
        # ========== 核心优化：适配回复API的URL参数（node_pk） ==========
        # 优先从URL路径取：回复API路径是 nodes/<node_pk>/comments/<root_comment_pk>/answers/
        article_id = view.kwargs.get("node_pk") or view.kwargs.get("article_id")
        # 兼容：从query_params/data获取（适配其他评论接口）
        if not article_id:
            article_id = request.query_params.get("article_id") or request.data.get("article_id")

        # 1. 必须传文章ID（node_pk/article_id）
        if not article_id:
            return False

        # 2. 校验文章存在（完善异常捕获，兼容UUID格式错误）
        try:
            article = KnowledgeNode.objects.get(id=article_id)
        except (KnowledgeNode.DoesNotExist, ValueError, TypeError):
            # ValueError：ID格式错误（如非UUID字符串）
            # TypeError：ID类型错误（如传了数字而非字符串）
            return False

        # 3. 匿名用户：仅允许GET/HEAD/OPTIONS（安全方法）查看公开知识库的评论
        if not request.user.is_authenticated:
            return request.method in permissions.SAFE_METHODS and article.knowledge_base.is_public

        # 4. 登录用户：校验文章所属知识库权限（优化逻辑，减少查询）
        kb = article.knowledge_base
        if not kb:  # 容错：知识库为空时拒绝
            return False

        # 权限判断逻辑优化：先判断创建者/公开，再查共享（减少数据库查询）
        if kb.creator == request.user or kb.is_public:
            return True

        # 校验共享权限（补充PermissionLevel的有效值校验）
        share_exists = KnowledgeShare.objects.filter(
            knowledge_base=kb,
            shared_to=request.user,
            permission_level__in=PermissionLevel.values  # 确保权限等级有效
        ).exists()
        return share_exists

    def has_object_permission(self, request, view, obj):
        """
        对象级权限校验（编辑/删除评论）：
        - 适配评论模型的 `commented_by` 字段（你的模型中评论作者字段）
        - 细化共享用户的权限（仅ADMIN可删改他人评论）
        """
        # ========== 核心适配：你的评论模型中作者字段是commented_by ==========
        comment_author = obj.commented_by
        if not comment_author:  # 容错：评论作者为空时拒绝
            return False

        # 先获取评论关联的文章和知识库
        article = obj.article
        kb = article.knowledge_base if article else None
        if not kb:  # 容错：无知识库时拒绝
            return False

        # 基础权限：评论作者自己可编辑/删除
        if comment_author == request.user:
            return True

        # 高级权限：知识库创建者（管理员）可操作所有评论
        if kb.creator == request.user:
            return True

        # 扩展权限：共享的ADMIN用户可操作所有评论（PARTICIPANT/VIEWER仅能操作自己的）
        share_admin = KnowledgeShare.objects.filter(
            knowledge_base=kb,
            shared_to=request.user,
            permission_level=PermissionLevel.ADMIN  # 仅ADMIN有权限
        ).exists()
        return share_admin