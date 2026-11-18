from django.contrib import admin
from .models import User, VipInfo, UserFollow  # 新增导入 UserFollow 模型

admin.site.site_header = '知识库用户管理平台'  # 设置网站页头
admin.site.site_title = '知识库用户管理平台'  # 设置页面标题
admin.site.index_title = '欢迎进入comuni用户管理平台'  # 设置首页标语


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """用户模型后台管理配置"""
    list_display = ('id', 'username', 'email', 'gender', 'user_id', 'wechat_openid', 'is_active', 'created_at')
    search_fields = ('username', 'email', 'wechat_openid', 'user_id')  # 新增 user_id 搜索
    list_filter = ('gender', 'created_at', 'is_active')  # 新增 is_active 过滤
    readonly_fields = ('created_at', 'updated_at')
    # 优化列表分页（避免数据量大时卡顿）
    list_per_page = 50


@admin.register(VipInfo)  # 注册 VipInfo 模型
class VipInfoAdmin(admin.ModelAdmin):
    """会员信息模型后台管理配置"""
    list_display = ('id', 'user', 'is_vip', 'expire_date', 'created_at')  # 列表页显示的字段
    search_fields = ('user__username', 'user__email', 'user__user_id')  # 新增 user_id 搜索
    list_filter = ('is_vip', 'created_at', 'expire_date')  # 新增 expire_date 过滤
    readonly_fields = ('created_at', 'updated_at')  # 只读字段（创建/更新时间）
    raw_id_fields = ('user',)  # 外键字段使用 raw_id 避免下拉框加载过多数据
    list_per_page = 50


# ===================== 新增：关注关系后台管理配置 =====================
@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    """用户关注关系后台管理配置"""
    # 列表页显示核心字段（关注者、被关注者、关注时间）
    list_display = (
        'id',
        'follower_info',  # 自定义显示：关注者（用户名+user_id）
        'followed_info',  # 自定义显示：被关注者（用户名+user_id）
        'created_at'
    )
    # 支持按关注者/被关注者的用户名、user_id、邮箱搜索
    search_fields = (
        'follower__username',
        'follower__user_id',
        'follower__email',
        'followed__username',
        'followed__user_id',
        'followed__email'
    )
    # 过滤器（按关注时间筛选）
    list_filter = ('created_at',)
    # 只读字段（关注时间自动生成，不可修改）
    readonly_fields = ('created_at',)
    # 外键使用 raw_id 避免下拉框加载大量用户数据（性能优化）
    raw_id_fields = ('follower', 'followed')
    # 分页配置（避免数据量大时卡顿）
    list_per_page = 50
    # 排序（默认按关注时间倒序）
    ordering = ('-created_at',)

    def follower_info(self, obj):
        """自定义显示关注者信息：用户名 + user_id（提升可读性）"""
        return f"{obj.follower.username} (ID: {obj.follower.user_id})"
    # 设置列标题
    follower_info.short_description = '关注者'

    def followed_info(self, obj):
        """自定义显示被关注者信息：用户名 + user_id"""
        return f"{obj.followed.username} (ID: {obj.followed.user_id})"
    followed_info.short_description = '被关注者'

    # # 生产许可（或严格管理-后台使用人员情况）：限制后台只能查看/删除，禁止手动添加（避免违反业务规则）
    # 若需要后台手动添加关注关系，删除 has_add_permission 方法，或改为 return True，并启用 save_model 方法触发校验：
    # def has_add_permission(self, request):
    #     """禁止后台手动添加关注关系（仅允许前端/接口操作）"""
    #     return False

    # 可选：如需允许添加，可重写 save_model 触发模型校验（防止关注自己/重复关注）
    def save_model(self, request, obj, form, change):
        """保存时触发模型校验，防止关注自己/重复关注"""
        try:
            obj.clean()  # 触发模型的 clean 校验（禁止关注自己）
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            self.message_user(request, str(e), level=admin.ERROR)   # `f"添加失败：{str(e)}"`