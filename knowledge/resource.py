#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/1/6 18:07
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : resource.py
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
# resource.py - 所有模型的导入导出资源配置
from import_export import resources
from import_export.fields import Field
from import_export import widgets
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

# 导入项目模型
from .models import (
    User, NodeTag, KnowledgeBase, KnowledgeNode,
    NodeHistory, KnowledgeShare, Comment, PermissionLevel
)


# ===================== 1. 节点标签（NodeTag）资源 =====================
class NodeTagResource(resources.ModelResource):
    """
    节点标签导入导出配置
    - 中文列名
    - 按标签名称去重
    - 支持按用户名匹配创建者
    """
    # 自定义字段映射（中文列名）
    id = Field(attribute='id', column_name='标签ID')
    name = Field(attribute='name', column_name='标签名称')
    color = Field(attribute='color', column_name='标签颜色')
    creator = Field(
        attribute='creator',
        column_name='创建者',
        widget=widgets.ForeignKeyWidget(User, 'username')  # 按用户名匹配外键
    )
    created_at = Field(attribute='created_at', column_name='创建时间')

    # 数据校验
    def clean_name(self, value):
        """校验标签名称"""
        if not value or len(value.strip()) == 0:
            raise ValidationError("标签名称不能为空")
        if len(value) > 50:
            raise ValidationError("标签名称不能超过50个字符")
        return value.strip()

    class Meta:
        model = NodeTag
        # 导入导出字段
        fields = ('id', 'name', 'color', 'creator', 'created_at')
        # 导出字段顺序
        export_order = ('id', 'name', 'color', 'creator', 'created_at')
        # 导入去重标识（按标签名称）
        import_id_fields = ['name']
        # 跳过无变更的记录
        skip_unchanged = True
        # 报告跳过的记录
        report_skipped = True
        # 排除的字段
        exclude = []


# ===================== 2. 知识库（KnowledgeBase）资源 =====================
class KnowledgeBaseResource(resources.ModelResource):
    """
    知识库导入导出配置
    - 中文列名
    - 按short_id去重
    - 支持按用户名匹配创建者
    """
    # 自定义字段映射
    id = Field(attribute='id', column_name='知识库ID')
    short_id = Field(attribute='short_id', column_name='短ID')
    name = Field(attribute='name', column_name='知识库名称')
    description = Field(attribute='description', column_name='描述')
    creator = Field(
        attribute='creator',
        column_name='创建者',
        widget=widgets.ForeignKeyWidget(User, 'username')
    )
    is_public = Field(attribute='is_public', column_name='是否公开')
    created_at = Field(attribute='created_at', column_name='创建时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    # 数据校验
    def clean_name(self, value):
        """校验知识库名称"""
        if not value or len(value.strip()) == 0:
            raise ValidationError("知识库名称不能为空")
        if len(value) > 100:
            raise ValidationError("知识库名称不能超过100个字符")
        return value.strip()

    class Meta:
        model = KnowledgeBase
        fields = ('id', 'short_id', 'name', 'description', 'creator', 'is_public', 'created_at', 'updated_at')
        export_order = ('id', 'short_id', 'name', 'creator', 'is_public', 'created_at', 'updated_at', 'description')
        import_id_fields = ['short_id']  # 按短ID去重
        skip_unchanged = True
        report_skipped = True


# ===================== 3. 知识库节点（KnowledgeNode）资源 =====================
class KnowledgeNodeResource(resources.ModelResource):
    """
    知识库节点核心资源配置
    - 中文列名
    - 关联字段按名称匹配（知识库/父节点/创建者）
    - 按名称+知识库去重
    - 自动处理节点类型和编辑模式
    """
    # 自定义字段映射
    id = Field(attribute='id', column_name='节点ID')
    short_id = Field(attribute='short_id', column_name='短ID')
    name = Field(attribute='name', column_name='节点名称')
    node_type = Field(attribute='node_type', column_name='节点类型')
    editor_mode = Field(attribute='editor_mode', column_name='编辑模式')
    content = Field(attribute='content', column_name='节点内容')
    description = Field(attribute='description', column_name='描述')
    # 关联知识库（按名称匹配）
    knowledge_base = Field(
        attribute='knowledge_base',
        column_name='知识库名称',
        widget=widgets.ForeignKeyWidget(KnowledgeBase, 'name')
    )
    # 关联父节点（按名称匹配）
    parent_node = Field(
        attribute='parent_node',
        column_name='父节点名称',
        widget=widgets.ForeignKeyWidget(KnowledgeNode, 'name'),
        null=True,
        blank=True
    )
    # 关联创建者（按用户名匹配）
    creator = Field(
        attribute='creator',
        column_name='创建者',
        widget=widgets.ForeignKeyWidget(User, 'username')
    )
    sort_order = Field(attribute='sort_order', column_name='排序')
    created_at = Field(attribute='created_at', column_name='创建时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    # 导入前处理关联字段
    def before_import_row(self, row, **kwargs):
        """
        导入行数据前的预处理：
        1. 将知识库名称转为ID
        2. 将父节点名称转为ID（需关联对应知识库）
        3. 将创建者用户名转为ID
        """
        # 1. 处理知识库关联
        kb_name = row.get('知识库名称')
        if kb_name:
            try:
                kb = KnowledgeBase.objects.get(name=kb_name.strip())
                row['knowledge_base'] = kb.id
            except KnowledgeBase.DoesNotExist:
                raise ValidationError(f"知识库「{kb_name}」不存在，请先创建该知识库")

        # 2. 处理父节点关联
        parent_name = row.get('父节点名称')
        if parent_name and parent_name.strip():
            try:
                parent_node = KnowledgeNode.objects.get(
                    name=parent_name.strip(),
                    knowledge_base_id=row.get('knowledge_base')
                )
                row['parent_node'] = parent_node.id
            except KnowledgeNode.DoesNotExist:
                raise ValidationError(f"知识库「{kb_name}」下的父节点「{parent_name}」不存在")
        else:
            row['parent_node'] = None

        # 3. 处理创建者关联
        creator_name = row.get('创建者')
        if creator_name:
            try:
                creator = User.objects.get(username=creator_name.strip())
                row['creator'] = creator.id
            except User.DoesNotExist:
                raise ValidationError(f"用户「{creator_name}」不存在")

    # 数据校验
    def clean_name(self, value):
        """校验节点名称"""
        if not value or len(value.strip()) == 0:
            raise ValidationError("节点名称不能为空")
        if len(value) > 100:
            raise ValidationError("节点名称不能超过100个字符")
        return value.strip()

    def clean_node_type(self, value):
        """校验节点类型"""
        valid_types = [choice[0] for choice in KnowledgeNode.NodeType.choices]
        if value not in valid_types:
            raise ValidationError(f"节点类型必须是：{', '.join(valid_types)}")
        return value

    def clean_editor_mode(self, value):
        """校验编辑模式"""
        if value not in ['markdown', 'rich-text']:
            raise ValidationError("编辑模式必须是 markdown 或 rich-text")
        return value

    class Meta:
        model = KnowledgeNode
        fields = (
            'id', 'short_id', 'name', 'node_type', 'editor_mode',
            'content', 'description', 'knowledge_base', 'parent_node',
            'creator', 'sort_order', 'created_at', 'updated_at'
        )
        export_order = (
            'id', 'short_id', 'name', 'node_type', 'editor_mode',
            'knowledge_base', 'parent_node', 'creator', 'sort_order',
            'created_at', 'updated_at', 'description', 'content'
        )
        import_id_fields = ['name', 'knowledge_base']  # 按名称+知识库去重
        exclude = ['path']  # 排除自动生成的path字段
        skip_unchanged = True
        report_skipped = True


# ===================== 4. 知识库共享（KnowledgeShare）资源 =====================
class KnowledgeShareResource(resources.ModelResource):
    """
    知识库共享导入导出配置
    - 中文列名
    - 按知识库+共享对象去重
    - 校验权限等级
    """
    # 自定义字段映射
    id = Field(attribute='id', column_name='共享ID')
    knowledge_base = Field(
        attribute='knowledge_base',
        column_name='知识库名称',
        widget=widgets.ForeignKeyWidget(KnowledgeBase, 'name')
    )
    shared_to = Field(
        attribute='shared_to',
        column_name='共享给',
        widget=widgets.ForeignKeyWidget(User, 'username')
    )
    permission_level = Field(attribute='permission_level', column_name='权限等级')
    shared_at = Field(attribute='shared_at', column_name='共享时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    # 数据校验
    def clean_permission_level(self, value):
        """校验权限等级"""
        valid_levels = [choice[0] for choice in PermissionLevel.choices]
        if value not in valid_levels:
            raise ValidationError(f"权限等级必须是：{', '.join(valid_levels)}")
        return value

    class Meta:
        model = KnowledgeShare
        fields = ('id', 'knowledge_base', 'shared_to', 'permission_level', 'shared_at', 'updated_at')
        export_order = ('id', 'knowledge_base', 'shared_to', 'permission_level', 'shared_at', 'updated_at')
        import_id_fields = ['knowledge_base', 'shared_to']  # 按知识库+共享对象去重
        skip_unchanged = True
        report_skipped = True


# ===================== 5. 节点编辑历史（NodeHistory）资源 =====================
class NodeHistoryResource(resources.ModelResource):
    """
    节点编辑历史导出配置（仅导出，禁止导入）
    - 中文列名
    - 关联字段友好显示
    """
    # 自定义字段映射
    id = Field(attribute='id', column_name='历史记录ID')
    node = Field(
        attribute='node',
        column_name='关联节点',
        widget=widgets.ForeignKeyWidget(KnowledgeNode, 'name')
    )
    editor = Field(
        attribute='editor',
        column_name='编辑者',
        widget=widgets.ForeignKeyWidget(User, 'username')
    )
    old_content = Field(attribute='old_content', column_name='修改前内容')
    new_content = Field(attribute='new_content', column_name='修改后内容')
    remark = Field(attribute='remark', column_name='修改备注')
    edited_at = Field(attribute='edited_at', column_name='编辑时间')

    class Meta:
        model = NodeHistory
        fields = ('id', 'node', 'editor', 'old_content', 'new_content', 'remark', 'edited_at')
        export_order = ('id', 'node', 'editor', 'edited_at', 'remark', 'old_content', 'new_content')
        # 仅导出，禁止导入
        import_id_fields = []
        skip_unchanged = True
        report_skipped = True


# ===================== 6. 评论（Comment）资源 =====================
class CommentResource(resources.ModelResource):
    """
    评论导入导出配置
    - 中文列名
    - 按评论者+节点+时间去重
    """
    # 自定义字段映射
    id = Field(attribute='id', column_name='评论ID')
    commentator = Field(
        attribute='commentator',
        column_name='评论者',
        widget=widgets.ForeignKeyWidget(User, 'username')
    )
    knowledge_base = Field(
        attribute='knowledge_base',
        column_name='知识库名称',
        widget=widgets.ForeignKeyWidget(KnowledgeBase, 'name')
    )
    node = Field(
        attribute='node',
        column_name='关联节点',
        widget=widgets.ForeignKeyWidget(KnowledgeNode, 'name')
    )
    content = Field(attribute='content', column_name='评论内容')
    created_at = Field(attribute='created_at', column_name='评论时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    # 数据校验
    def clean_content(self, value):
        """校验评论内容"""
        if not value or len(value.strip()) == 0:
            raise ValidationError("评论内容不能为空")
        return value.strip()

    class Meta:
        model = Comment
        fields = ('id', 'commentator', 'knowledge_base', 'node', 'content', 'created_at', 'updated_at')
        export_order = ('id', 'commentator', 'knowledge_base', 'node', 'created_at', 'content', 'updated_at')
        import_id_fields = ['commentator', 'node', 'created_at']  # 按评论者+节点+时间去重
        skip_unchanged = True
        report_skipped = True
