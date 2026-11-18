import uuid
import shortuuid
from django.db import models, IntegrityError  # 导入 IntegrityError
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError  # 导入 ValidationError
from django.utils.translation import gettext_lazy as _  # 导入国际化翻译函数

from users.utils import rename_avatar

"""
users App：用户账号核心信息
负责用户登录、注册、身份标识，
基于 Django 内置AbstractUser扩展（保留手机号 / 微信 OpenID 等小程序登录必要字段）。
"""


class User(AbstractUser):
    """ 自定义用户模型 扩展用户模型，添加TOTP双因素认证字段 """
    # 扩展字段（根据需求添加）
    GENDER_CHOICES = (
        ('male', '男'),
        ('female', '女'),
        ('other', '隐藏'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # 展示用用户编码（方便记忆/显示）
    user_id = models.CharField(
        max_length=22,  # 限制长度，避免过长
        unique=True,  # 数据库级别保证唯一
        verbose_name="用户ID",
        help_text="支持数字、字母组合，长度1-20位，不可重复"
    )
    email = models.EmailField(unique=True, blank=False, null=False, verbose_name="邮箱")  # email 字段设置为唯一约束 unique=True
    gender = models.CharField(max_length=255, choices=GENDER_CHOICES, blank=True, verbose_name="性别")
    wechat_openid = models.CharField(max_length=255, unique=True, blank=True, null=True, verbose_name="微信OpenID(微信登录用)")
    # 核心修改：upload_to指向自定义重命名函数
    avatar = models.ImageField(
        upload_to=rename_avatar,
        blank=True,
        null=True,
        verbose_name="头像"
    )
    # 使用了ImageField（头像字段），pip install Pillow
    bio = models.TextField(blank=True, null=True)
    # 新增：公开/私密控制（默认公开，私密用户不被搜索）
    is_private = models.BooleanField(
        default=False,
        verbose_name="是否私密",
        help_text="私密用户不会出现在公开搜索结果中"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    # TOTP密钥（base32格式，用于生成动态验证码）
    totp_secret = models.CharField(max_length=32, blank=True, null=True)
    # 是否启用双因素认证
    is_totp_enabled = models.BooleanField(default=False)
    # 备用验证码（用于丢失设备时恢复，多个用逗号分隔）
    backup_codes = models.TextField(blank=True, null=True)

    # 解决反向关联冲突：给groups和user_permissions指定唯一related_name
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='users_user_groups',  # 唯一名称
        blank=True,
        verbose_name='groups',
        related_query_name='users_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='users_user_permissions',  # 唯一名称
        blank=True,
        verbose_name='user permissions',
        related_query_name='users_user',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "用户"
        verbose_name_plural = "用户"
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=["user_id"]),  # 给自定义ID加索引，提升查询效率
            models.Index(fields=['wechat_openid']),
        ]

    def __str__(self):
        return self.username


    def generate_totp_secret(self):
        """生成TOTP密钥（base32格式）"""
        if not self.totp_secret:
            self.totp_secret = pyotp.random_base32()
            self.save()
        return self.totp_secret

    def get_totp_provisioning_uri(self):
        """生成TOTP配置URI（用于生成二维码）"""
        if not self.totp_secret:
            self.generate_totp_secret()
        # 格式：otpauth://totp/[Issuer]:[Account]?secret=[Secret]&issuer=[Issuer]
        return pyotp.totp.TOTP(self.totp_secret).provisioning_uri(
            name=self.username,
            issuer_name="KnowledgeBase"  # 替换为你的应用名称
        )

    def verify_totp_code(self, code):
        """验证TOTP动态码是否有效"""
        if not self.totp_secret or not self.is_totp_enabled:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        # 允许±1步的时间误差（防止网络延迟）
        return totp.verify(code, valid_window=1)

    def generate_backup_codes(self, count=5):
        """生成备用验证码（丢失设备时使用）"""
        import random
        codes = [f"{random.randint(100000, 999999)}" for _ in range(count)]
        self.backup_codes = ",".join(codes)
        self.save()
        return codes

    # 校验自定义ID格式（仅允许数字、字母）
    def clean_user_id(self):
        """独立的ID格式校验方法，返回合规的ID或抛异常"""
        user_id = (self.user_id or "").strip()
        # 1. 检查是否为空
        if not user_id:
            raise ValidationError(_("用户ID不能为空"))
        # 2. 检查长度
        if len(user_id) > 22:
            raise ValidationError(_("用户ID长度不能超过22位"))
        # 3. 检查格式（仅允许数字、字母）
        if not user_id.isalnum():
            raise ValidationError(_("用户ID仅支持数字和字母组合"))
        return user_id

    def save(self, *args, **kwargs):
        """重写save方法：自动生成初始ID + 校验唯一性 + 处理并发"""
        # 1. 首次创建用户：自动生成初始ID（短UUID）
        if not self.user_id:  # 任何场景下（包括创建超级用户）只要 user_id 为空，就自动生成短 UUID
            # 生成短UUID（22位，比标准UUID更友好）
            self.user_id = shortuuid.uuid()

        try:
            # 2. 先校验ID格式（抛ValidationError）
            self.user_id = self.clean_user_id()

            # 3. 唯一性校验（排除自身，避免修改时和原ID重复）
            if User.objects.filter(user_id=self.user_id).exclude(pk=self.pk).exists():
                raise ValidationError(_(f"用户ID {self.user_id} 已被使用，请更换"))

            # 关键修改：检查pk是否存在且数据库中确实有该记录
            if self.pk and User.objects.filter(pk=self.pk).exists():
                old_instance = User.objects.get(pk=self.pk)
                # 处理旧实例相关的操作-删除旧实例的头像
                if old_instance.avatar and old_instance.avatar != self.avatar:
                    old_instance.avatar.delete(save=False)
            # 没有的话就是创建新用户
            else:
                # 新用户创建时，无需处理旧实例
                pass

            # 4. 调用父类save方法保存实例（传递所有参数）
            try:
                super().save(*args, **kwargs)
            except IntegrityError as e:
                # 检查错误信息，区分是email还是user_id冲突
                if 'users_user_email_key' in str(e):
                    raise ValidationError("此邮箱已注册，请更换其他邮箱")
                elif 'users_user_user_id_key' in str(e):
                    raise ValidationError(f"用户ID {self.user_id} 已被占用，请更换其他ID")
                else:
                    raise  # 其他完整性错误直接抛出

        # 5. 捕获数据库层面的唯一约束冲突（并发场景兜底）
        except IntegrityError:
            raise ValidationError(_(f"用户ID {self.user_id} 已被占用，请更换其他ID"))

    # 兼容Django的create_superuser方法（确保创建超级用户时生成user_id）
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        # 确保生成user_id
        if not extra_fields.get('user_id'):
            extra_fields['user_id'] = shortuuid.uuid()
        return self._create_user(username, email, password, **extra_fields)


# ===================== 新增：用户关注关系模型 =====================
class UserFollow(models.Model):
    """用户关注关系表（关联自定义User模型）"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # 关注者（当前登录用户）：外键关联自定义User模型
    follower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='following',  # 反向查询：user.following.all() → 该用户关注的所有人
        verbose_name="关注者"
    )
    # 被关注者：外键关联自定义User模型
    followed = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='followers',  # 反向查询：user.followers.all() → 该用户的所有粉丝
        verbose_name="被关注者"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="关注时间")

    class Meta:
        # 唯一约束：一个用户不能重复关注同一个人（数据库级别防重复）
        unique_together = ('follower', 'followed')
        verbose_name = "用户关注列表"
        verbose_name_plural = "用户关注列表"
        ordering = ['-created_at']  # 按关注时间倒序
        # 加索引提升查询效率（关注列表/粉丝列表查询高频）
        indexes = [
            models.Index(fields=['follower', 'created_at']),
            models.Index(fields=['followed', 'created_at']),
        ]

    def __str__(self):
        return f"{self.follower.username} 关注 {self.followed.username}"

    def clean(self):
        """数据校验：禁止关注自己"""
        if self.follower == self.followed:
            raise ValidationError(_("不能关注自己！"))

    def save(self, *args, **kwargs):
        """重写save：先执行校验，再保存"""
        self.clean()  # 执行自定义校验
        try:
            super().save(*args, **kwargs)
        except IntegrityError:
            # 并发场景下的重复关注兜底
            raise ValidationError(_(f"你已关注 {self.followed.username}，无需重复关注"))


# 会员信息模型（核心）
class VipInfo(models.Model):
    # 显式添加 UUID 类型主键，与 User 模型保持一致
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # 修复：related_name 避免用中文，防止编码/查询异常
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='vip_info',  # 原中文“会员用户信息”改为英文
        verbose_name='会员用户'
    )
    is_vip = models.BooleanField(default=False, verbose_name='是否会员')
    expire_date = models.DateTimeField(blank=True, null=True, verbose_name='会员过期时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='开通时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '会员信息'
        verbose_name_plural = '会员信息'

    def __str__(self):
        return f"{self.user.username} - {'会员' if self.is_vip else '非会员'}"
