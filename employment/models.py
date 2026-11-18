from django.db import models


class RecruitmentInfo(models.Model):
    """企业招聘信息模型 - 对应所有指定字段"""
    # 基础信息
    enterprise_name = models.CharField(verbose_name="企业名称", max_length=255)
    credit_code = models.CharField(verbose_name="信用代码", max_length=50)
    enterprise_nature = models.CharField(verbose_name="企业性质", max_length=100)
    enterprise_scale = models.CharField(verbose_name="企业规模", max_length=50)
    enterprise_intro = models.TextField(verbose_name="企业简介", blank=True, null=True)
    industry = models.CharField(verbose_name="行业", max_length=255)

    # 招聘信息
    job_name = models.CharField(verbose_name="岗位名称", max_length=255)
    recruit_major = models.CharField(verbose_name="招聘专业", max_length=500)
    recruit_number = models.CharField(verbose_name="招聘人数", max_length=50)  # 含"6~10人"、"不限"等格式
    monthly_salary = models.CharField(verbose_name="月薪", max_length=50)

    # 联系信息
    contact_person = models.CharField(verbose_name="联系人", max_length=100)
    contact_phone = models.CharField(verbose_name="联系电话", max_length=20)
    id_card = models.CharField(verbose_name="身份证号", max_length=50, blank=True, null=True)
    license_plate = models.CharField(verbose_name="车牌号", max_length=50, blank=True, null=True)
    company_address = models.CharField(verbose_name="公司地址", max_length=500)
    email = models.CharField(verbose_name="邮箱", max_length=255)

    # 流程信息
    registration_time = models.DateField(verbose_name="报名时间")
    audit_status = models.CharField(verbose_name="审核状态", max_length=50)
    booth_number = models.CharField(verbose_name="展位号", max_length=50)
    check_in_status = models.CharField(verbose_name="签到状态", max_length=50)
    is_alumni_enterprise = models.CharField(verbose_name="是否校友企业", max_length=10)

    class Meta:
        verbose_name = "企业招聘信息"
        verbose_name_plural = "企业招聘信息"
        ordering = ["-registration_time"]  # 按报名时间倒序排列

    def __str__(self):
        return f"{self.enterprise_name} - {self.job_name}"
