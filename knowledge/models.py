import uuid
import shortuuid  # 可选：用于生成短UUID，简化path长度（需安装：pip install shortuuid）
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


User = get_user_model()


# ===================== 1. 标签模型（独立模型，支持多节点关联多标签） =====================
class NodeTag(models.Model):
    """节点标签模型：支持多标签分类，可复用"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="标签ID")
    name = models.CharField(max_length=64, unique=True, verbose_name="标签名称", help_text="例如：Python、前端、笔记")
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_tags",
        verbose_name="创建者"
    )
    color = models.CharField(max_length=7, default="#1890ff", verbose_name="标签颜色", help_text="十六进制颜色码，如#1890ff")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "节点标签"
        verbose_name_plural = "节点标签"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["name"])]  # 标签名索引，优化查询

    def __str__(self):
        return f"{self.name}（{self.color}）"

    def clean(self):
        # 标签名非空校验
        if not self.name.strip():
            raise ValidationError(_("标签名称不能为空"))
        # 标签名长度校验
        if len(self.name) > 64:
            raise ValidationError(_("标签名称长度不能超过64位"))


# ===================== 2.知识库根模型（核心容器） =====================
class KnowledgeBase(models.Model):
    """知识库根容器：每个知识库独立管理一组文件夹/MD文件"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="知识库ID")
    # 知识库短标识（用于path字段，简化路径）
    short_id = models.CharField(max_length=22, unique=True, editable=False, verbose_name="知识库短ID")
    name = models.CharField(max_length=128, verbose_name="知识库名称", help_text="例如：Python学习笔记")
    description = models.TextField(blank=True, null=True, verbose_name="知识库描述")
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_knowledge_bases",
        verbose_name="创建者"
    )
    is_public = models.BooleanField(default=False, verbose_name="是否公开", help_text="公开后其他用户可查看")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "知识库"
        verbose_name_plural = "知识库"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["creator", "is_public"]),  # 优化：按创建者+公开状态查询
        ]

    def save(self, *args, **kwargs):
        # 首次创建时生成短ID
        if not self.short_id:
            self.short_id = shortuuid.uuid()[:8]  # 取前8位，足够唯一且短
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}（{self.creator.username}）"

# ===================== 用户关注知识库模型 =====================
class UserFollowKnowledgeBase(models.Model):
    """用户关注知识库模型：记录用户与知识库的关注关系"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="关注记录ID")
    # 关联关注的用户
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="followed_knowledge_bases",
        verbose_name="关注用户"
    )
    # 关联被关注的知识库
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name="followers",
        verbose_name="被关注的知识库"
    )
    # 关注时间
    follow_time = models.DateTimeField(auto_now_add=True, verbose_name="关注时间")
    # 取消关注时间（可选：软删除，保留关注历史）
    unfollow_time = models.DateTimeField(null=True, blank=True, verbose_name="取消关注时间")
    # 是否有效（软删除标识，True=已关注，False=已取消）
    is_active = models.BooleanField(default=True, verbose_name="关注是否有效")

    class Meta:
        verbose_name = "用户关注知识库"
        verbose_name_plural = "用户关注知识库"
        ordering = ["-follow_time"]
        # 核心约束：同一用户不能重复关注同一个知识库（仅有效关注）
        unique_together = ["user", "knowledge_base", "is_active"]
        indexes = [
            models.Index(fields=["user", "is_active"]),  # 按用户+关注状态查询
            models.Index(fields=["knowledge_base", "is_active"]),  # 按知识库+关注状态查询
            models.Index(fields=["follow_time"]),  # 按关注时间排序
        ]

    def __str__(self):
        status = "已关注" if self.is_active else "已取消关注"
        return f"{self.user.username} {status} {self.knowledge_base.name}"

    def clean(self):
        # 校验：取消关注时必须填写取消时间
        if not self.is_active and not self.unfollow_time:
            raise ValidationError(_("取消关注时必须填写取消关注时间"))
        # 校验：恢复关注时清空取消时间
        if self.is_active and self.unfollow_time:
            self.unfollow_time = None

# ===================== 3. 节点模型（扩展标签、优化MD上传 文件夹/MD文件统一存储 新增path字段，支持物化路径查询） =====================
class KnowledgeNode(models.Model):
    """节点：统一存储文件夹和MD文件，支持无限嵌套，path字段优化查询"""
    # 节点类型枚举（文件夹/MD文件）
    class NodeType(models.TextChoices):
        FOLDER = "folder", _("文件夹")
        MARKDOWN = "markdown", _("MD文件")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="节点ID")
    # 节点短标识（用于path字段）
    short_id = models.CharField(max_length=22, unique=True, editable=False, verbose_name="节点短ID")
    # 关联所属知识库（必选：每个节点必须属于一个知识库）
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name="所属知识库"
    )
    # 父节点（自关联：实现嵌套，null表示根节点下的一级节点）
    parent_node = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="child_nodes",
        null=True,
        blank=True,
        verbose_name="父节点",
        help_text="null表示根节点下的节点，文件夹可作为父节点"
    )
    # 节点类型（区分文件夹/MD文件）
    node_type = models.CharField(
        max_length=16,
        choices=NodeType.choices,
        default=NodeType.MARKDOWN, # 默认 markdown 类型
        verbose_name="节点类型"
    )
    # 节点名称（文件夹名称/MD文件名，无需后缀）
    name = models.CharField(max_length=128, verbose_name="节点名称",
                            help_text="例如：基础语法（文件夹）/变量定义.md（文件，无需手动加后缀）")
    # 新增：编辑模式（记录是 Markdown 还是富文本）
    editor_mode = models.CharField(
        max_length=16,
        choices=[("markdown", "Markdown 模式"), ("rich-text", "富文本模式")],
        default="markdown",
        verbose_name="编辑模式",
        help_text="用于前端渲染时判断处理方式"
    )

    # MD/note 笔记文件内容（仅node_type=markdown时有效，字符串存储）
    content = models.TextField(blank=True, null=True, verbose_name="MD文件内容",
                               help_text="Markdown格式的字符串，支持上传文件内容存入, 前端解析渲染")
    description = models.TextField(blank=True, null=True, verbose_name="文件夹描述")
    # 物化路径（格式：知识库短ID/父节点短ID/当前节点短ID/）
    path = models.CharField(max_length=1024, editable=False, verbose_name="节点路径",
                            help_text="自动生成，用于快速查询子节点")
    # 新增：标签多对多关联
    tags = models.ManyToManyField(
        NodeTag,
        related_name="nodes",
        blank=True,
        verbose_name="节点标签",
        help_text="可为节点绑定多个标签，支持分类筛选"
    )
    # 关联创建者（权限控制）
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_nodes",
        verbose_name="创建者"
    )
    # 排序字段（可选：用于自定义节点显示顺序）
    sort_order = models.IntegerField(default=0, verbose_name="排序权重", help_text="数值越大，显示越靠后")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "知识库节点"
        verbose_name_plural = "知识库节点"
        ordering = ["sort_order", "-created_at"]  # 先按排序权重，再按创建时间倒序
        indexes = [
            models.Index(fields=["knowledge_base", "parent_node"]),  # 优化：按知识库+父节点查询子节点
            models.Index(fields=["node_type", "creator"]),  # 优化：按类型+创建者查询
            models.Index(fields=["path"]),  # 新增：给path字段加索引，优化startswith查询
        ]
        unique_together = ["parent_node", "name"]

    def save(self, *args, **kwargs):
        """重写save：自动生成短ID + 计算path + 数据校验 + 级联更新子节点path"""
        # 1. 首次创建时生成节点短ID
        if not self.short_id:
            self.short_id = shortuuid.uuid()[:8]

        # 2. 计算物化路径path
        self._update_path()

        # 3. 执行数据校验
        self.clean()

        # 4. 保存前：若为MD文件且内容变更，自动创建编辑历史
        is_update = self.pk is not None
        old_content = None

        # 修复核心：只有编辑操作且是MD文件时，才查询旧内容（增加异常处理）
        if is_update and self.node_type == self.NodeType.MARKDOWN:
            try:
                # 使用filter+first避免get()抛出异常
                # first() 返回实例对象（存在）或 None（不存在）
                old_instance = KnowledgeNode.objects.filter(pk=self.pk).first()
                if old_instance and old_instance.content != self.content:
                    old_content = old_instance.content
            except Exception as e:
                # 记录异常但不中断保存（可选：可以加日志）
                old_content = None

        # 5. 保存当前节点（必须先保存，才能获取pk用于创建历史记录）
        super().save(*args, **kwargs)

        # 6. 创建编辑历史（仅MD文件内容变更时）
        if old_content is not None:
            NodeHistory.objects.create(
                node=self,
                editor=self.creator,
                old_content=old_content,
                new_content=self.content
            )
        # 7. 级联更新子节点的path（若当前节点是文件夹且path变化）
        if self.node_type == self.NodeType.FOLDER:
            self._update_child_nodes_path()

    def _update_path(self):
        """核心：计算当前节点的path"""
        # 基础路径：知识库短ID/
        base_path = f"{self.knowledge_base.short_id}/"

        # 若有父节点：父节点path + 父节点短ID/
        if self.parent_node:
            # 确保父节点已保存（有path）
            if not self.parent_node.path:
                self.parent_node.save()  # 递归保存父节点，生成path
            self.path = f"{self.parent_node.path}{self.parent_node.short_id}/"
        else:
            # 无父节点（根节点）：知识库短ID/
            self.path = base_path

        # 最终path：基础路径 + 当前节点短ID/
        self.path = f"{self.path}{self.short_id}/"

    def _update_child_nodes_path(self):
        """级联更新所有子节点的path（当当前节点path变化时）"""
        child_nodes = KnowledgeNode.objects.filter(parent_node=self)
        for child in child_nodes:
            child._update_path()  # 重新计算子节点path
            child.save(update_fields=["path", "updated_at"])  # 仅更新path和更新时间

    def clean(self):
        """数据校验：确保文件夹不能包含MD文件内容，MD文件必须有内容"""
        # 1. 文件夹校验：无content content必须为空
        if self.node_type == self.NodeType.FOLDER and self.content:
            raise ValidationError(_("文件夹不能包含MD文件内容"))
        # 2. MD文件校验：有content content不能为空，且name建议不重复（已通过unique_together约束）（上传/编辑都需满足）
        if self.node_type == self.NodeType.MARKDOWN and not self.content.strip():
            raise ValidationError(_("MD文件内容不能为空"))
        # 3. 父节点校验：必须是文件夹类型（如果有父节点）
        if self.parent_node and self.parent_node.node_type != self.NodeType.FOLDER:
            raise ValidationError(_("父节点必须是文件夹类型"))

    def __str__(self):
        return f"{self.get_node_type_display()}：{self.name}（路径/所属知识库：{self.path}）"


# ===================== 4. 编辑历史模型（MD文件专属） =====================
class NodeHistory(models.Model):
    """MD文件编辑历史：记录每次内容变更，支持回滚"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="历史记录ID")
    # 关联MD文件节点（仅关联markdown类型节点）
    node = models.ForeignKey(
        KnowledgeNode,
        on_delete=models.CASCADE,
        related_name="edit_histories",
        verbose_name="关联MD文件",
        limit_choices_to={"node_type": KnowledgeNode.NodeType.MARKDOWN}  # 仅显示MD文件
    )
    # 编辑者（可与创建者不同）
    editor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="edited_histories",
        verbose_name="编辑者"
    )
    # 编辑前后内容（完整存储，支持回滚）
    old_content = models.TextField(verbose_name="编辑前内容")
    new_content = models.TextField(verbose_name="编辑后内容")
    # 编辑备注（可选）
    remark = models.CharField(max_length=256, blank=True, null=True, verbose_name="编辑备注", help_text="例如：修复语法错误、补充示例代码")
    # 时间戳
    edited_at = models.DateTimeField(auto_now_add=True, verbose_name="编辑时间")

    class Meta:
        verbose_name = "节点编辑历史"
        verbose_name_plural = "节点编辑历史"
        ordering = ["-edited_at"]  # 按编辑时间倒序，最新的在前面
        indexes = [
            models.Index(fields=["node", "edited_at"]),  # 按MD文件+编辑时间查询
            models.Index(fields=["editor"]),  # 按编辑者查询
        ]

    def __str__(self):
        return f"{self.node.name} - {self.editor.username} 于 {self.edited_at.strftime('%Y-%m-%d %H:%M')} 编辑"

    def clean(self):
        # 校验：编辑前后内容不能相同
        if self.old_content.strip() == self.new_content.strip():
            raise ValidationError(_("编辑前后内容无变化，无需记录历史"))
        # 校验：内容不能为空
        if not self.old_content.strip() or not self.new_content.strip():
            raise ValidationError(_("编辑前后内容不能为空"))


# ===================== 5.权限枚举（核心） =====================
class PermissionLevel(models.TextChoices):
    """三级权限枚举：管理者 > 参与者 > 查看者"""
    ADMIN = "admin", _("管理者")    # 最高权限：查看+评论+编辑+删除+管理共享
    PARTICIPANT = "participant", _("参与者")  # 参与权限：查看+评论+编辑+添加节点
    VIEWER = "viewer", _("查看者")  # 基础权限：查看+评论

    @classmethod
    @property
    def values(cls):
        """返回所有权限值列表，供接口校验"""
        return [choice[0] for choice in cls.choices]

# ===================== 6.知识库共享模型（中间表） =====================
class KnowledgeShare(models.Model):
    """知识库共享关系表：记录哪个用户拥有哪个知识库的什么权限"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # 关联的知识库
    knowledge_base = models.ForeignKey(
        "KnowledgeBase",
        on_delete=models.CASCADE,
        related_name="shares",
        verbose_name="关联知识库"
    )
    # 被共享的用户（接收共享的人）
    shared_to = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="shared_knowledge_bases",
        verbose_name="被共享用户"
    )
    # 权限等级
    permission_level = models.CharField(
        max_length=16,
        choices=PermissionLevel.choices,
        default=PermissionLevel.VIEWER,
        verbose_name="权限等级"
    )
    # 共享时间
    shared_at = models.DateTimeField(auto_now_add=True, verbose_name="共享时间")
    # 最后更新权限时间
    updated_at = models.DateTimeField(auto_now=True, verbose_name="权限更新时间")

    class Meta:
        verbose_name = "知识库共享"
        verbose_name_plural = "知识库共享"
        # 唯一约束：同一用户不能被重复共享同一知识库
        unique_together = ["knowledge_base", "shared_to"]
        indexes = [
            models.Index(fields=["knowledge_base", "shared_to"]),
            models.Index(fields=["shared_to", "permission_level"]),
        ]
        # ========== 排序规则 ==========
        ordering = ["-shared_at", "permission_level"]  # 按共享时间倒序 + 权限等级排序

    def __str__(self):
        return f"{self.knowledge_base.name} - 共享给 {self.shared_to.username} - {self.get_permission_level_display()}"


# ===================== 评论类型枚举 =====================
class CommentType(models.TextChoices):
    """评论类型：根评论/回复评论"""
    ROOT = "root", _("根评论")
    ANSWER = "answer", _("回复评论")


# ===================== 评论模型（核心，修复外键关联） =====================
class Comment(models.Model):
    """
    抖音风格评论模型（修复外键关联问题）
    核心修复点：
    1. article_id → knowledge_base（与KnowledgeNode等模型字段名统一，关联KnowledgeBase）
    2. 所有User外键明确关联自定义users.User模型
    3. 完善字段校验，避免save方法递归问题
    4. 优化root_id赋值逻辑，防止主键未生成导致的错误
    """
    # 基础主键（UUID，与其他模型保持一致）
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="评论ID")

    # 外键关联知识库（字段名改为knowledge_base，与KnowledgeNode等模型统一）
    knowledge_base = models.ForeignKey(
        "KnowledgeBase",  # 关联当前app的KnowledgeBase模型
        on_delete=models.CASCADE,
        related_name="comments",  # 反向查询：knowledge_base.comments.all()
        verbose_name="所属知识库",
        help_text="评论关联的知识库（与KnowledgeNode的knowledge_base字段对应）"
    )

    # 评论内容
    comment_text = models.TextField(verbose_name="评论内容")

    # 关联自定义User模型（评论者）
    commented_by = models.ForeignKey(
        User,  # 通过get_user_model()获取users.User，避免硬编码路径
        on_delete=models.CASCADE,
        related_name="posted_comments",  # 反向查询：user.posted_comments.all()
        verbose_name="评论者"
    )

    # 评论时间（自动生成，用于排序）
    comment_date = models.DateTimeField(auto_now_add=True, verbose_name="评论时间")

    # 根评论ID（核心：回复评论关联根评论，根评论自身的root_id=自身ID）
    root_id = models.UUIDField(null=True, blank=True, verbose_name="根评论ID")

    # 评论类型（根评论/回复评论）
    type = models.CharField(
        max_length=8,
        choices=CommentType.choices,
        default=CommentType.ROOT,
        verbose_name="评论类型"
    )

    # 关联自定义User模型（被回复用户）
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_replies",  # 反向查询：user.received_replies.all()
        null=True,
        blank=True,
        verbose_name="被回复用户",
        help_text="仅回复评论需要填写，关联users.User模型"
    )

    # 热评权重（用于热评排序）
    hot = models.IntegerField(default=0, verbose_name="热评权重")

    # 更新时间（用于数据同步）
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "评论"
        verbose_name_plural = "评论"
        # 核心索引：优化查询性能（与业务查询逻辑匹配）
        indexes = [
            # 按知识库+类型查询（批量获取根评论/回复评论）
            models.Index(fields=["knowledge_base", "type"]),
            # 按根评论ID查询所有回复（按需加载子评论）
            models.Index(fields=["root_id", "comment_date"]),
            # 热评排序索引
            models.Index(fields=["knowledge_base", "hot", "-comment_date"]),
            # 根评论分页查询索引
            models.Index(fields=["knowledge_base", "type", "-comment_date"]),
        ]
        ordering = ["-comment_date"]

    def __str__(self):
        if self.type == CommentType.ROOT:
            return f"根评论-{self.id[:8]}：{self.comment_text[:20]}"
        return f"回复评论-{self.id[:8]}：{self.comment_text[:20]}"

    def clean(self):
        """新增校验：避免逻辑错误"""
        # 回复评论必须填写根评论ID和被回复用户
        if self.type == CommentType.ANSWER:
            if not self.root_id:
                raise ValidationError(_("回复评论必须指定根评论ID"))
            if not self.to_user:
                raise ValidationError(_("回复评论必须指定被回复用户"))
        # 根评论的root_id必须为自身（保存时自动赋值）
        if self.type == CommentType.ROOT and self.root_id and self.root_id != self.id:
            raise ValidationError(_("根评论的root_id必须等于自身ID"))

    def save(self, *args, **kwargs):
        """重写save：修复根评论ID赋值逻辑，避免递归保存问题"""
        # 先执行校验
        self.clean()

        # 根评论：自动设置root_id为自身ID（修复递归保存问题）
        if self.type == CommentType.ROOT and not self.root_id:
            # 若未保存（无主键），先临时保存获取ID
            if not self.pk:
                # 使用force_insert=True避免递归调用save
                super().save(force_insert=True, *args, **kwargs)
            # 赋值root_id为自身ID
            self.root_id = self.id

        # 正式保存（更新root_id）
        super().save(*args, **kwargs)


# ===================== 评论通知模型 =====================
class CommentNotification(models.Model):
    """评论回复通知模型"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="通知ID")

    # 关联自定义User模型（被通知用户）
    notified_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comment_notifications",  # 反向查询：user.comment_notifications.all()
        verbose_name="被通知用户"
    )

    # 关联修复后的Comment模型（回复评论）
    reply_comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="notifications",  # 反向查询：comment.notifications.all()
        verbose_name="回复评论",
        limit_choices_to={"type": CommentType.ANSWER}  # 仅显示回复评论
    )

    # 通知内容（如："XXX回复了你的评论：XXX"）
    content = models.CharField(max_length=256, verbose_name="通知内容")

    # 通知状态（已读/未读）
    is_read = models.BooleanField(default=False, verbose_name="是否已读")

    # 通知创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="通知创建时间")

    class Meta:
        verbose_name = "评论通知"
        verbose_name_plural = "评论通知"
        indexes = [
            models.Index(fields=["notified_user", "is_read"]),  # 按用户+已读状态查询
            models.Index(fields=["created_at"]),  # 按创建时间排序
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"通知-{self.id[:8]}：{self.notified_user.username} - {self.content[:20]}"

    def save(self, *args, **kwargs):
        """自动生成通知内容（可选，简化业务逻辑）"""
        if not self.content and self.reply_comment:
            replier = self.reply_comment.commented_by.username
            comment_text = self.reply_comment.comment_text[:20]
            self.content = f"{replier}回复了你的评论：{comment_text}..."
        super().save(*args, **kwargs)


# 评论类型枚举
class CommentTypeChoices(models.TextChoices):
    ROOT = "root", "根评论"
    ANSWER = "answer", "回复评论"

class NodeComment(models.Model):
    """
    文章（KnowledgeNode）专属评论模型
    - 严格绑定到具体文章（KnowledgeNode）
    - 支持根评论/回复评论嵌套
    - 记录热评权重、评论时间等
    """
    # 基础字段
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="评论ID")
    article = models.ForeignKey(
        "KnowledgeNode",
        on_delete=models.CASCADE,
        related_name="node_comments",
        verbose_name="所属文章（知识库节点）"
    )
    commented_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="node_comments",
        verbose_name="评论者"
    )
    comment_text = models.TextField(verbose_name="评论内容")
    # 嵌套回复相关
    root_id = models.UUIDField(null=True, blank=True, verbose_name="根评论ID（回复时关联）")
    type = models.CharField(
        max_length=10,
        choices=CommentTypeChoices.choices,
        default=CommentTypeChoices.ROOT,
        verbose_name="评论类型"
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_node_comments",
        verbose_name="被回复用户"
    )
    # 扩展字段
    hot = models.IntegerField(default=0, verbose_name="热评权重")
    comment_date = models.DateTimeField(auto_now_add=True, verbose_name="评论时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "文章评论"
        verbose_name_plural = "文章评论"
        ordering = ["-hot", "-comment_date"]  # 默认排序：热评优先、最新优先
        indexes = [
            models.Index(fields=["article", "type"]),  # 按文章+类型索引
            models.Index(fields=["root_id"]),  # 按根评论ID索引
        ]

    def __str__(self):
        return f"{self.commented_by.username} 评论《{self.article.name}》：{self.comment_text[:20]}..."

# 评论通知模型（关联NodeComment）
class NodeCommentNotification(models.Model):
    """文章评论通知模型"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notified_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="node_comment_notifications",
        verbose_name="被通知用户"
    )
    reply_comment = models.ForeignKey(
        NodeComment,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="关联回复评论"
    )
    content = models.CharField(max_length=200, verbose_name="通知内容")
    is_read = models.BooleanField(default=False, verbose_name="是否已读")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="通知创建时间")

    class Meta:
        verbose_name = "文章评论通知"
        verbose_name_plural = "文章评论通知"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notified_user.username} 的评论通知：{self.content[:30]}"