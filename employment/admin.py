from django.contrib import admin
from .models import RecruitmentInfo


@admin.register(RecruitmentInfo)
class RecruitmentInfoAdmin(admin.ModelAdmin):
    # 列表仅展示指定字段（移除了身份证号字段）
    list_display = [
        "credit_code", "enterprise_name", "enterprise_nature", "enterprise_scale",
        "industry", "job_name", "recruit_major", "recruit_number", "monthly_salary",
        "contact_person", "contact_phone", "license_plate", "company_address",
        "registration_time", "audit_status", "booth_number", "check_in_status",
        "is_alumni_enterprise", "email"
    ]
    # 筛选字段同步匹配列表展示字段
    list_filter = list_display
    # 搜索字段保留原有核心检索字段
    search_fields = ["enterprise_name", "credit_code", "job_name", "contact_person"]
    # 分页配置保持不变
    list_per_page = 20
    # 按报名时间倒序排序（最新报名的排在最前面）
    ordering = ['-registration_time']
