from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.utils.html import format_html
import zipfile
import os
import tempfile
from io import BytesIO

from import_export import resources
from import_export.fields import Field
from import_export.admin import ImportExportModelAdmin, ExportMixin, ImportMixin
from django.contrib.auth import get_user_model

from .models import (
    User, NodeTag, KnowledgeBase, KnowledgeNode,
    NodeHistory, KnowledgeShare, Comment, PermissionLevel,
    CommentType, CommentNotification, NodeComment, NodeCommentNotification,
    UserFollowKnowledgeBase
)


# ===================== 工具函数：文件解析（保留原有） =====================
def parse_uploaded_file(file_obj, knowledge_base, creator):
    """
    解析上传的文件（支持单个MD/HTML/ZIP），返回待创建的节点数据列表
    :param file_obj: 上传的文件对象
    :param knowledge_base: 关联的知识库
    :param creator: 创建者用户
    :return: (success_list, error_list)
    """
    success_list = []
    error_list = []

    # 判断文件类型
    file_name = file_obj.name
    file_ext = os.path.splitext(file_name)[-1].lower()

    # 1. ZIP压缩包（多文件）
    if file_ext == '.zip':
        with zipfile.ZipFile(file_obj, 'r') as zip_file:
            # 遍历ZIP中的所有文件
            for zip_info in zip_file.infolist():
                # 跳过文件夹和隐藏文件
                if zip_info.is_dir() or zip_info.filename.startswith('.'):
                    continue

                # 只处理MD/HTML文件
                zip_ext = os.path.splitext(zip_info.filename)[-1].lower()
                if zip_ext not in ['.md', '.html', '.txt']:
                    error_list.append(f"跳过非文本文件：{zip_info.filename}")
                    continue

                try:
                    # 读取文件内容
                    with zip_file.open(zip_info) as f:
                        content = f.read().decode('utf-8', errors='replace')

                    # 构建节点数据
                    node_name = os.path.splitext(os.path.basename(zip_info.filename))[0]
                    node_data = {
                        'name': node_name,
                        'content': content,
                        'knowledge_base': knowledge_base,
                        'creator': creator,
                        'node_type': KnowledgeNode.NodeType.MARKDOWN if zip_ext == '.md' else KnowledgeNode.NodeType.RICH_TEXT,
                        'editor_mode': 'markdown' if zip_ext == '.md' else 'rich-text',
                        'sort_order': len(success_list) + 1
                    }
                    success_list.append(node_data)
                except Exception as e:
                    error_list.append(f"解析文件 {zip_info.filename} 失败：{str(e)}")

    # 2. 单个MD/HTML/TXT文件
    elif file_ext in ['.md', '.html', '.txt']:
        try:
            # 读取文件内容
            content = file_obj.read().decode('utf-8', errors='replace')
            node_name = os.path.splitext(file_name)[0]
            node_data = {
                'name': node_name,
                'content': content,
                'knowledge_base': knowledge_base,
                'creator': creator,
                'node_type': KnowledgeNode.NodeType.MARKDOWN if file_ext == '.md' else KnowledgeNode.NodeType.RICH_TEXT,
                'editor_mode': 'markdown' if file_ext == '.md' else 'rich-text',
                'sort_order': 1
            }
            success_list.append(node_data)
        except Exception as e:
            error_list.append(f"解析文件 {file_name} 失败：{str(e)}")

    # 3. 不支持的文件类型
    else:
        error_list.append(f"不支持的文件类型：{file_ext}，仅支持ZIP/MD/HTML/TXT")

    return success_list, error_list


# ===================== 新增：定义各模型的Resource（导入导出配置） =====================
# 1. NodeTag资源配置
class NodeTagResource(resources.ModelResource):
    # 自定义中文列名
    id = Field(attribute='id', column_name='标签ID')
    name = Field(attribute='name', column_name='标签名称')
    color = Field(attribute='color', column_name='标签颜色')
    creator = Field(attribute='creator', column_name='创建者',
                    widget=resources.widgets.ForeignKeyWidget(User, 'username'))
    created_at = Field(attribute='created_at', column_name='创建时间')

    class Meta:
        model = NodeTag
        fields = ('id', 'name', 'color', 'creator', 'created_at')
        export_order = ('id', 'name', 'color', 'creator', 'created_at')
        import_id_fields = ['name']  # 以标签名称为唯一标识
        skip_unchanged = True
        report_skipped = True


# 2. KnowledgeBase资源配置
class KnowledgeBaseResource(resources.ModelResource):
    # 自定义中文列名
    id = Field(attribute='id', column_name='知识库ID')
    short_id = Field(attribute='short_id', column_name='短ID')
    name = Field(attribute='name', column_name='知识库名称')
    description = Field(attribute='description', column_name='描述')
    creator = Field(attribute='creator', column_name='创建者',
                    widget=resources.widgets.ForeignKeyWidget(User, 'username'))
    is_public = Field(attribute='is_public', column_name='是否公开')
    created_at = Field(attribute='created_at', column_name='创建时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    class Meta:
        model = KnowledgeBase
        fields = ('id', 'short_id', 'name', 'description', 'creator', 'is_public', 'created_at', 'updated_at')
        export_order = ('id', 'short_id', 'name', 'creator', 'is_public', 'created_at', 'updated_at')
        import_id_fields = ['short_id']  # 以短ID为唯一标识
        skip_unchanged = True
        report_skipped = True


# 3. KnowledgeNode资源配置（核心）
class KnowledgeNodeResource(resources.ModelResource):
    # 自定义中文列名
    id = Field(attribute='id', column_name='节点ID')
    short_id = Field(attribute='short_id', column_name='短ID')
    name = Field(attribute='name', column_name='节点名称')
    node_type = Field(attribute='node_type', column_name='节点类型')
    editor_mode = Field(attribute='editor_mode', column_name='编辑模式')
    content = Field(attribute='content', column_name='节点内容')
    description = Field(attribute='description', column_name='描述')
    # 关联字段（通过名称匹配）
    knowledge_base = Field(
        attribute='knowledge_base',
        column_name='知识库名称',
        widget=resources.widgets.ForeignKeyWidget(KnowledgeBase, 'name')
    )
    parent_node = Field(
        attribute='parent_node',
        column_name='父节点名称',
        widget=resources.widgets.ForeignKeyWidget(KnowledgeNode, 'name'),
    )
    creator = Field(
        attribute='creator',
        column_name='创建者',
        widget=resources.widgets.ForeignKeyWidget(User, 'username')
    )
    sort_order = Field(attribute='sort_order', column_name='排序')
    created_at = Field(attribute='created_at', column_name='创建时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    # 自定义导入逻辑：处理关联字段匹配
    def before_import_row(self, row, **kwargs):
        # 匹配知识库（通过名称）
        kb_name = row.get('知识库名称')
        if kb_name:
            try:
                kb = KnowledgeBase.objects.get(name=kb_name)
                row['knowledge_base'] = kb.id
            except KnowledgeBase.DoesNotExist:
                raise ValueError(f"知识库「{kb_name}」不存在！")

        # 匹配父节点（通过名称+知识库）
        parent_name = row.get('父节点名称')
        if parent_name and parent_name.strip():
            try:
                parent_node = KnowledgeNode.objects.get(
                    name=parent_name,
                    knowledge_base_id=row.get('knowledge_base')
                )
                row['parent_node'] = parent_node.id
            except KnowledgeNode.DoesNotExist:
                raise ValueError(f"父节点「{parent_name}」不存在！")
        else:
            row['parent_node'] = None

        # 匹配创建者（通过用户名）
        creator_name = row.get('创建者')
        if creator_name:
            try:
                creator = User.objects.get(username=creator_name)
                row['creator'] = creator.id
            except User.DoesNotExist:
                raise ValueError(f"用户「{creator_name}」不存在！")

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
        import_id_fields = ['name', 'knowledge_base']  # 名称+知识库作为唯一标识
        exclude = ['path']  # 排除自动生成的path字段
        skip_unchanged = True
        report_skipped = True


# 4. KnowledgeShare资源配置
class KnowledgeShareResource(resources.ModelResource):
    id = Field(attribute='id', column_name='共享ID')
    knowledge_base = Field(attribute='knowledge_base', column_name='知识库名称',
                           widget=resources.widgets.ForeignKeyWidget(KnowledgeBase, 'name'))
    shared_to = Field(attribute='shared_to', column_name='共享给',
                      widget=resources.widgets.ForeignKeyWidget(User, 'username'))
    permission_level = Field(attribute='permission_level', column_name='权限等级')
    shared_at = Field(attribute='shared_at', column_name='共享时间')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    class Meta:
        model = KnowledgeShare
        fields = ('id', 'knowledge_base', 'shared_to', 'permission_level', 'shared_at', 'updated_at')
        export_order = ('id', 'knowledge_base', 'shared_to', 'permission_level', 'shared_at', 'updated_at')
        import_id_fields = ['knowledge_base', 'shared_to']
        skip_unchanged = True
        report_skipped = True


# ===================== 新增：用户关注知识库Resource配置 =====================
class UserFollowKnowledgeBaseResource(resources.ModelResource):
    """用户关注知识库导入导出配置"""
    id = Field(attribute='id', column_name='关注记录ID')
    user = Field(
        attribute='user',
        column_name='关注用户',
        widget=resources.widgets.ForeignKeyWidget(User, 'username')
    )
    knowledge_base = Field(
        attribute='knowledge_base',
        column_name='被关注知识库',
        widget=resources.widgets.ForeignKeyWidget(KnowledgeBase, 'name')
    )
    follow_time = Field(attribute='follow_time', column_name='关注时间')
    unfollow_time = Field(attribute='unfollow_time', column_name='取消关注时间')
    is_active = Field(attribute='is_active', column_name='关注是否有效')

    # 自定义导入逻辑：匹配关联字段
    def before_import_row(self, row, **kwargs):
        # 匹配关注用户（通过用户名）
        user_name = row.get('关注用户')
        if user_name:
            try:
                user = User.objects.get(username=user_name)
                row['user'] = user.id
            except User.DoesNotExist:
                raise ValueError(f"用户「{user_name}」不存在！")

        # 匹配被关注知识库（通过名称）
        kb_name = row.get('被关注知识库')
        if kb_name:
            try:
                kb = KnowledgeBase.objects.get(name=kb_name)
                row['knowledge_base'] = kb.id
            except KnowledgeBase.DoesNotExist:
                raise ValueError(f"知识库「{kb_name}」不存在！")

    class Meta:
        model = UserFollowKnowledgeBase
        fields = ('id', 'user', 'knowledge_base', 'follow_time', 'unfollow_time', 'is_active')
        export_order = ('id', 'user', 'knowledge_base', 'is_active', 'follow_time', 'unfollow_time')
        import_id_fields = ['user', 'knowledge_base', 'is_active']  # 唯一约束组合
        skip_unchanged = True
        report_skipped = True
        fields_with_nulls = ['unfollow_time']  # 允许取消关注时间为空


# ===================== 1. 标签模型 Admin（集成导入导出） =====================
@admin.register(NodeTag)
class NodeTagAdmin(ImportExportModelAdmin):
    """节点标签后台配置（含导入导出）"""
    resource_class = NodeTagResource
    list_display = ("id", "name", "color", "creator", "created_at")
    search_fields = ("name", "creator__username")
    list_filter = ("created_at", "creator")
    readonly_fields = ("id", "created_at")
    fieldsets = (
        (_("基础信息"), {
            "fields": ("id", "name", "color", "creator")
        }),
        (_("系统信息"), {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )
    ordering = ["-created_at"]


# ===================== 2. 知识库模型 Admin（集成导入导出） =====================
@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(ImportExportModelAdmin):
    """知识库后台配置（含导入导出）"""
    resource_class = KnowledgeBaseResource
    list_display = ("id", "short_id", "name", "creator", "is_public", "created_at", "updated_at")
    search_fields = ("name", "short_id", "creator__username", "description")
    list_filter = ("is_public", "created_at", "updated_at", "creator")
    readonly_fields = ("id", "short_id", "created_at", "updated_at")
    fieldsets = (
        (_("基础信息"), {
            "fields": ("id", "short_id", "name", "description", "creator")
        }),
        (_("权限设置"), {
            "fields": ("is_public",)
        }),
        (_("系统信息"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    ordering = ["-created_at"]


# ===================== 新增：用户关注知识库Admin配置 =====================
@admin.register(UserFollowKnowledgeBase)
class UserFollowKnowledgeBaseAdmin(ImportExportModelAdmin):
    """用户关注知识库后台配置（含导入导出）"""
    resource_class = UserFollowKnowledgeBaseResource
    # 列表显示字段
    list_display = (
        "id_short", "user_name", "knowledge_base_name",
        "is_active", "follow_time", "unfollow_time"
    )
    # 搜索字段
    search_fields = (
        "user__username", "knowledge_base__name",
        "follow_time", "unfollow_time"
    )
    # 筛选条件
    list_filter = (
        "is_active", "follow_time", "unfollow_time",
        "knowledge_base__creator", "knowledge_base__is_public"
    )
    # 只读字段
    readonly_fields = ("id", "follow_time")
    # 字段分组
    fieldsets = (
        (_("关联信息"), {
            "fields": ("id", "user", "knowledge_base")
        }),
        (_("关注状态"), {
            "fields": ("is_active", "follow_time", "unfollow_time")
        }),
    )
    # 批量操作
    actions = [
        "activate_follow", "deactivate_follow"
    ]
    ordering = ["-follow_time"]

    # 自定义短ID显示
    def id_short(self, obj):
        return str(obj.id)[:8]

    id_short.short_description = "关注ID"

    # 自定义用户名显示
    def user_name(self, obj):
        return obj.user.username

    user_name.short_description = "关注用户"

    # 自定义知识库名称显示
    def knowledge_base_name(self, obj):
        return obj.knowledge_base.name

    knowledge_base_name.short_description = "被关注知识库"

    # 批量激活关注（恢复关注）
    def activate_follow(self, request, queryset):
        queryset.update(
            is_active=True,
            unfollow_time=None
        )

    activate_follow.short_description = _("批量激活关注（恢复关注）")

    # 批量取消关注
    def deactivate_follow(self, request, queryset):
        from django.utils import timezone
        queryset.update(
            is_active=False,
            unfollow_time=timezone.now()
        )

    deactivate_follow.short_description = _("批量取消关注")


# ===================== 3. 节点编辑历史 内嵌Admin =====================
class NodeHistoryInline(admin.TabularInline):
    """节点编辑历史内嵌显示"""
    model = NodeHistory
    extra = 0
    readonly_fields = ("id", "editor", "old_content", "new_content", "edited_at")
    can_add = False
    can_delete = False
    fields = ("id", "editor", "edited_at", "old_content", "new_content")
    ordering = ["-edited_at"]


# ===================== 4. 知识库节点 Admin（集成导入导出+保留批量上传） =====================
@admin.register(KnowledgeNode)
class KnowledgeNodeAdmin(ImportExportModelAdmin):
    """知识库节点后台配置（含导入导出+批量上传）"""
    resource_class = KnowledgeNodeResource
    list_display = (
        "id", "short_id", "name", "node_type", "knowledge_base",
        "parent_node", "creator", "sort_order", "created_at"
    )
    search_fields = (
        "name", "short_id", "content", "creator__username",
        "knowledge_base__name", "parent_node__name"
    )
    list_filter = (
        "node_type", "editor_mode", "knowledge_base", "creator",
        "created_at", "updated_at"
    )
    readonly_fields = ("id", "short_id", "path", "created_at", "updated_at")
    inlines = [NodeHistoryInline]
    fieldsets = (
        (_("归属信息"), {
            "fields": ("id", "short_id", "knowledge_base", "parent_node")
        }),
        (_("基础信息"), {
            "fields": ("name", "node_type", "editor_mode", "sort_order")
        }),
        (_("内容信息"), {
            "fields": ("content", "description"),
            "classes": ("collapse",)
        }),
        (_("分类信息"), {
            "fields": ("tags",)
        }),
        (_("权限信息"), {
            "fields": ("creator",)
        }),
        (_("系统信息"), {
            "fields": ("path", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    filter_horizontal = ("tags",)
    ordering = ["sort_order", "-created_at"]

    # 保留原有批量操作+批量上传
    actions = [
        "make_folder", "make_markdown",
        "batch_upload_nodes"
    ]

    def make_folder(self, request, queryset):
        """批量设置为文件夹"""
        queryset.update(node_type=KnowledgeNode.NodeType.FOLDER)

    make_folder.short_description = _("将选中节点设为文件夹")

    def make_markdown(self, request, queryset):
        """批量设置为MD文件"""
        queryset.update(node_type=KnowledgeNode.NodeType.MARKDOWN)

    make_markdown.short_description = _("将选中节点设为MD文件")

    # 保留原有批量上传节点功能
    def batch_upload_nodes(self, request, queryset):
        """
        批量上传节点的Admin Action
        步骤：1. 弹出上传表单 2. 解析文件 3. 批量创建节点 4. 返回结果
        """
        if 'file' in request.FILES:
            # 获取关联的知识库
            knowledge_base = None
            if queryset.exists():
                knowledge_base = queryset.first().knowledge_base
            else:
                kb_id = request.POST.get('knowledge_base_id')
                if kb_id:
                    try:
                        knowledge_base = KnowledgeBase.objects.get(id=kb_id)
                    except KnowledgeBase.DoesNotExist:
                        self.message_user(request, _("指定的知识库不存在！"), level='error')
                        return

            if not knowledge_base:
                self.message_user(request, _("请先选中一个节点（自动关联知识库）或在表单中指定知识库！"), level='error')
                return

            # 解析上传的文件
            file_obj = request.FILES['file']
            success_list, error_list = parse_uploaded_file(
                file_obj=file_obj,
                knowledge_base=knowledge_base,
                creator=request.user
            )

            # 批量创建节点
            created_count = 0
            for node_data in success_list:
                try:
                    KnowledgeNode.objects.create(**node_data)
                    created_count += 1
                except Exception as e:
                    error_list.append(f"创建节点 {node_data['name']} 失败：{str(e)}")

            # 返回结果提示
            success_msg = f"成功创建 {created_count} 个节点！" if created_count > 0 else ""
            error_msg = f"失败 {len(error_list)} 项：{'; '.join(error_list)}" if error_list else ""
            total_msg = f"{success_msg} {error_msg}".strip()
            self.message_user(request, total_msg, level='success' if created_count > 0 else 'error')
            return

        # 显示上传表单
        from django.template.response import TemplateResponse
        context = {
            'title': _('批量上传节点'),
            'knowledge_bases': KnowledgeBase.objects.all(),
            'queryset': queryset,
            'opts': self.model._meta,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, 'admin/batch_upload_nodes.html', context)

    batch_upload_nodes.short_description = _("批量上传节点（MD/HTML/ZIP）")


# ===================== 5. 节点编辑历史 Admin（仅导出，禁止导入） =====================
@admin.register(NodeHistory)
class NodeHistoryAdmin(ExportMixin, admin.ModelAdmin):
    """节点编辑历史后台配置（仅导出）"""
    resource_class = resources.ModelResource  # 基础导出配置
    list_display = ("id", "node", "editor", "edited_at")
    search_fields = ("node__name", "editor__username", "old_content", "new_content", "remark")
    list_filter = ("edited_at", "editor")
    readonly_fields = ("id", "node", "editor", "old_content", "new_content", "edited_at", "remark")
    can_add = False
    can_change = False
    can_delete = False
    fieldsets = (
        (_("关联信息"), {
            "fields": ("id", "node", "editor")
        }),
        (_("内容变更"), {
            "fields": ("old_content", "new_content"),
            "classes": ("collapse", "wide")
        }),
        (_("备注信息"), {
            "fields": ("remark",)
        }),
        (_("系统信息"), {
            "fields": ("edited_at",),
            "classes": ("collapse",)
        }),
    )
    ordering = ["-edited_at"]


# ===================== 6. 知识库共享 Admin（集成导入导出） =====================
@admin.register(KnowledgeShare)
class KnowledgeShareAdmin(ImportExportModelAdmin):
    """知识库共享后台配置（含导入导出）"""
    resource_class = KnowledgeShareResource
    list_display = ("id", "knowledge_base", "shared_to", "permission_level", "shared_at", "updated_at")
    search_fields = ("knowledge_base__name", "shared_to__username", "permission_level")
    list_filter = ("permission_level", "shared_at", "updated_at")
    readonly_fields = ("id", "shared_at", "updated_at")
    fieldsets = (
        (_("共享信息"), {
            "fields": ("id", "knowledge_base", "shared_to", "permission_level")
        }),
        (_("时间信息"), {
            "fields": ("shared_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    actions = [
        "set_admin_permission",
        "set_participant_permission",
        "set_viewer_permission"
    ]
    ordering = ["-shared_at"]

    def set_admin_permission(self, request, queryset):
        queryset.update(permission_level=PermissionLevel.ADMIN)

    set_admin_permission.short_description = _("设为管理者权限")

    def set_participant_permission(self, request, queryset):
        queryset.update(permission_level=PermissionLevel.PARTICIPANT)

    set_participant_permission.short_description = _("设为参与者权限")

    def set_viewer_permission(self, request, queryset):
        queryset.update(permission_level=PermissionLevel.VIEWER)

    set_viewer_permission.short_description = _("设为查看者权限")


# ===================== 评论资源配置（导入导出） =====================
class CommentResource(resources.ModelResource):
    """评论导入导出配置：适配新模型字段（修复null参数错误）"""
    id = Field(attribute='id', column_name='评论ID')
    knowledge_base = Field(
        attribute='knowledge_base',
        column_name='所属知识库',
        widget=resources.widgets.ForeignKeyWidget(KnowledgeBase, 'name')
    )
    comment_text = Field(attribute='comment_text', column_name='评论内容')
    commented_by = Field(
        attribute='commented_by',
        column_name='评论者',
        widget=resources.widgets.ForeignKeyWidget(User, 'username')
    )
    comment_date = Field(attribute='comment_date', column_name='评论时间')
    root_id = Field(attribute='root_id', column_name='根评论ID')
    type = Field(attribute='type', column_name='评论类型')
    to_user = Field(
        attribute='to_user',
        column_name='被回复用户',
        widget=resources.widgets.ForeignKeyWidget(User, 'username')
    )
    hot = Field(attribute='hot', column_name='热评权重')
    updated_at = Field(attribute='updated_at', column_name='更新时间')

    class Meta:
        model = Comment
        fields = ('id', 'knowledge_base', 'comment_text', 'commented_by',
                  'comment_date', 'root_id', 'type', 'to_user', 'hot', 'updated_at')
        export_order = fields
        import_id_fields = ['id']
        skip_unchanged = True
        report_skipped = True
        # 可选：允许导入时to_user字段为空（对应模型的null=True）
        fields_with_nulls = ['to_user']


# ===================== 评论 Admin 配置 =====================
@admin.register(Comment)
class CommentAdmin(ImportExportModelAdmin):
    """评论Admin：适配新模型字段"""
    resource_class = CommentResource
    # 列表显示字段（适配knowledge_base/to_user）
    list_display = (
        'id_short', 'knowledge_base_name', 'commented_by', 'type',
        'hot', 'comment_date', 'root_id_short', 'to_user_name', 'is_answer'
    )
    # 搜索字段
    search_fields = (
        'comment_text', 'commented_by__username', 'knowledge_base__name',
        'root_id', 'to_user__username'
    )
    # 筛选条件
    list_filter = (
        ('type', admin.ChoicesFieldListFilter),
        'hot', 'comment_date', 'updated_at', 'knowledge_base'
    )
    # 只读字段
    readonly_fields = ('id', 'comment_date', 'updated_at', 'root_id')
    # 字段分组
    fieldsets = (
        ('关联信息', {
            'fields': ('id', 'knowledge_base', 'root_id', 'type')
        }),
        ('评论内容', {
            'fields': ('comment_text', 'commented_by', 'to_user')
        }),
        ('排序/权重', {
            'fields': ('hot',)
        }),
        ('系统信息', {
            'fields': ('comment_date', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    ordering = ['-comment_date']

    # 自定义短ID显示（提升可读性）
    def id_short(self, obj):
        return obj.id[:8]

    id_short.short_description = '评论ID'

    def root_id_short(self, obj):
        return obj.root_id[:8] if obj.root_id else '-'

    root_id_short.short_description = '根评论ID'

    # 自定义知识库名称显示
    def knowledge_base_name(self, obj):
        return obj.knowledge_base.name

    knowledge_base_name.short_description = '所属知识库'

    # 自定义被回复用户显示
    def to_user_name(self, obj):
        return obj.to_user.username if obj.to_user else '-'

    to_user_name.short_description = '被回复用户'

    # 标记是否为回复评论
    def is_answer(self, obj):
        return obj.type == CommentType.ANSWER

    is_answer.short_description = '是否为回复'
    is_answer.boolean = True


# ===================== 评论通知 Admin 配置 =====================
@admin.register(CommentNotification)
class CommentNotificationAdmin(admin.ModelAdmin):
    """评论通知Admin：只读，适配新模型"""
    list_display = ('id_short', 'notified_user_name', 'is_read', 'created_at', 'content_short')
    search_fields = ('notified_user__username', 'content', 'reply_comment__comment_text')
    list_filter = ('is_read', 'created_at')
    # 完全只读（通知不可手动修改）
    readonly_fields = ('id', 'notified_user', 'reply_comment', 'content', 'is_read', 'created_at')
    can_add = False
    can_delete = False
    can_change = False
    fieldsets = (
        ('通知信息', {
            'fields': ('id', 'notified_user', 'content', 'is_read')
        }),
        ('关联评论', {
            'fields': ('reply_comment',)
        }),
        ('系统信息', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    ordering = ['-created_at']

    # 自定义短ID显示
    def id_short(self, obj):
        return obj.id[:8]

    id_short.short_description = '通知ID'

    # 自定义被通知用户显示
    def notified_user_name(self, obj):
        return obj.notified_user.username

    notified_user_name.short_description = '被通知用户'

    # 自定义内容短显示
    def content_short(self, obj):
        return obj.content[:30] + '...' if len(obj.content) > 30 else obj.content

    content_short.short_description = '通知内容'


# ===================== 文章评论 Admin 配置 =====================
@admin.register(NodeComment)
class NodeCommentAdmin(admin.ModelAdmin):
    """文章评论Admin：适配NodeComment模型"""
    # 列表显示字段
    list_display = (
        "id_short", "article_name", "commented_by_name", "type",
        "hot", "comment_date", "root_id_short", "to_user_name"
    )
    # 搜索字段
    search_fields = (
        "comment_text", "commented_by__username", "article__name",
        "root_id", "to_user__username"
    )
    # 筛选条件
    list_filter = (
        ("type", admin.ChoicesFieldListFilter),
        "hot", "comment_date", "updated_at", "article__knowledge_base"
    )
    # 只读字段
    readonly_fields = ("id", "comment_date", "updated_at")
    # 字段分组
    fieldsets = (
        ("关联信息", {
            "fields": ("id", "article", "root_id", "type")
        }),
        ("评论内容", {
            "fields": ("comment_text", "commented_by", "to_user")
        }),
        ("扩展信息", {
            "fields": ("hot", "comment_date", "updated_at")
        }),
    )
    # 排序
    ordering = ["-comment_date"]

    # 自定义短ID显示
    def id_short(self, obj):
        return str(obj.id)[:8]

    id_short.short_description = "评论ID"

    def root_id_short(self, obj):
        return str(obj.root_id)[:8] if obj.root_id else "-"

    root_id_short.short_description = "根评论ID"

    # 自定义文章名称显示
    def article_name(self, obj):
        return obj.article.name

    article_name.short_description = "所属文章"

    # 自定义评论者名称显示
    def commented_by_name(self, obj):
        return obj.commented_by.username

    commented_by_name.short_description = "评论者"

    # 自定义被回复用户显示
    def to_user_name(self, obj):
        return obj.to_user.username if obj.to_user else "-"

    to_user_name.short_description = "被回复用户"


# ===================== 文章评论通知 Admin 配置 =====================
@admin.register(NodeCommentNotification)
class NodeCommentNotificationAdmin(admin.ModelAdmin):
    """文章评论通知Admin：只读配置"""
    list_display = ("id_short", "notified_user_name", "is_read", "created_at", "content_short")
    search_fields = ("notified_user__username", "content", "reply_comment__comment_text")
    list_filter = ("is_read", "created_at")
    # 完全只读
    readonly_fields = ("id", "notified_user", "reply_comment", "content", "is_read", "created_at")
    can_add = False
    can_delete = False
    can_change = False  # 禁止修改，仅可查看
    # 字段分组
    fieldsets = (
        ("通知信息", {
            "fields": ("id", "notified_user", "content", "is_read")
        }),
        ("关联评论", {
            "fields": ("reply_comment",)
        }),
        ("系统信息", {
            "fields": ("created_at",)
        }),
    )
    ordering = ["-created_at"]

    # 自定义短ID显示
    def id_short(self, obj):
        return str(obj.id)[:8]

    id_short.short_description = "通知ID"

    # 自定义被通知用户显示
    def notified_user_name(self, obj):
        return obj.notified_user.username

    notified_user_name.short_description = "被通知用户"

    # 自定义内容短显示
    def content_short(self, obj):
        return obj.content[:30] + "..." if len(obj.content) > 30 else obj.content

    content_short.short_description = "通知内容"
