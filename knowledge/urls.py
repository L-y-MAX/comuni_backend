
#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/1/9 17:00
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : urls.py
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
from django.urls import path, include
from rest_framework_nested import routers
from rest_framework.routers import DefaultRouter
from .views import (
    KnowledgeBaseViewSet, KnowledgeShareViewSet, KnowledgeNodeViewSet,
    CommentViewSet, NodeTagViewSet, NodeHistoryViewSet,
    KnowledgeNodeByKBViewSet, GlobalSearchViewSet, CommentNotificationViewSet,
    NodeCommentViewSet, NodeCommentNotificationViewSet,
    UserFollowKnowledgeBaseViewSet, UserPublicKnowledgeBasesViewSet, PublicKnowledgeNodeViewSet
)

# 根路由配置（保留你的原有配置）
router = DefaultRouter()
router.register(r"knowledge/knowledgebase", KnowledgeBaseViewSet, basename="knowledgebase")
router.register(r"knowledge/knowledgeshare", KnowledgeShareViewSet, basename="knowledgeshare")
router.register(r"knowledge/knowledgenode", KnowledgeNodeViewSet, basename="knowledgenode")
router.register(r'knowledge/comments', CommentViewSet, basename='comment')
router.register(r'knowledge/comment-notifications', CommentNotificationViewSet, basename='comment-notification')
router.register(r"knowledge/nodetag", NodeTagViewSet, basename="nodetag")
router.register(r"knowledge/nodehistory", NodeHistoryViewSet, basename="nodehistory")
router.register(r"knowledge/nodes", KnowledgeNodeByKBViewSet, basename="knowledge-node-by-kb")
router.register(r"search", GlobalSearchViewSet, basename="search")
router.register(r"knowledge/node-comments", NodeCommentViewSet, basename="node-comment")
router.register(r"knowledge/node-comment-notifications", NodeCommentNotificationViewSet, basename="node-comment-notification")
# 用户关注知识库路由
router.register(r"knowledge/user-follow-knowledgebase", UserFollowKnowledgeBaseViewSet, basename="user-follow-knowledgebase")
router.register(r"knowledge/user-public-kbs", UserPublicKnowledgeBasesViewSet, basename="user-public-kbs")

# ========== 第一层嵌套（节点→评论）保留，移除重复的第二层嵌套 ==========
knowledge_nodes_router = routers.NestedDefaultRouter(router, r"knowledge/knowledgenode", lookup="article")
knowledge_nodes_router.register(r"comments", NodeCommentViewSet, basename="knowledge-node-comments")
# 公开知识库节点查询路由
router.register(r"knowledge/public-nodes", PublicKnowledgeNodeViewSet, basename="public-knowledge-node")
# ========== 自定义嵌套回复接口路径（避免参数名重复） ==========
# 方式1：嵌套路由的回复接口（通过自定义path实现，避免自动生成重复参数）
nested_answer_urls = [
    # 嵌套路径：/api/v1/knowledge/knowledgenode/{article_id}/comments/root-comment/{root_comment_pk}/answers/
    path(
        r"knowledge/knowledgenode/<uuid:article_id>/comments/root-comment/<uuid:root_comment_pk>/answers/",
        NodeCommentViewSet.as_view({"get": "root_comment_answers", "post": "create_root_comment_answer"}),
        name="knowledge-node-comment-answers"
    ),
]

# 方式2：基础路由的回复接口（保留，兼容原有调用）
basic_answer_urls = [
    # 基础路径：/api/v1/knowledge/node-comments/root-comment/{root_comment_pk}/answers/
    path(
        r"knowledge/node-comments/root-comment/<uuid:root_comment_pk>/answers/",
        NodeCommentViewSet.as_view({"get": "root_comment_answers", "post": "create_root_comment_answer"}),
        name="node-comment-root-answers"
    ),
]

# 关注知识库的快捷接口路由（可选，优化前端调用体验）
follow_shortcut_urls = [
    # 快捷路径：/api/v1/knowledge/user-follow-knowledgebase/followed-bases/
    path(
        r"knowledge/user-follow-knowledgebase/followed-bases/",
        UserFollowKnowledgeBaseViewSet.as_view({"get": "get_followed_bases"}),
        name="user-follow-knowledgebase-followed-bases"
    ),
]

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("api/v1/", include(knowledge_nodes_router.urls)),  # 保留第一层嵌套（节点→评论）
    path("api/v1/", include(nested_answer_urls)),          # 新增：嵌套回复接口（自定义path）
    path("api/v1/", include(basic_answer_urls)),           # 保留：基础回复接口
    path("api/v1/", include(follow_shortcut_urls)),        # 新增：关注快捷接口（可选）
]