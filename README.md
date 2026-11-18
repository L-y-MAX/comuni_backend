# KnowledgeBase

可优笔记(ComUni 为“可优” 谐音)是一个Markdown标记语言和富文本编辑的笔记工具小程序

## 项目目的
解决用户 markdown 标记语法文件/内容 不能共享的问题

- copied ChatGPT Grok Gemini 豆包 deepseek 元宝 等 AI 回答，保存到本 平台即可实现 回答->笔记->共享知识库

这是一个基于 知识库 0 节点 + 知识节点的多层次结构项目

KnowledgeBase&amp;KnowledgeNode

## 项目名称



## 项目简介

### employment

```python
filterset_fields = [
    # 企业名称, 信用代码, 企业性质
    "enterprise_name", "credit_code", "enterprise_nature",
    # 企业规模, 企业简介, 行业
    "enterprise_scale", "enterprise_intro", "industry",
    # 岗位名称, 招聘专业, 招聘人数
    "job_name", "recruit_major", "recruit_number",
    # 月薪, 联系人, 联系电话, ~~身份证号~~
    "monthly_salary", "contact_person", "contact_phone",
    # ~~车牌号~~, 公司地址, ~~报名时间~~, 展位号
    "company_address", "booth_number",
    # 签到状态, 是否校友企业, 邮箱
    "check_in_status", "is_alumni_enterprise", "email"
]
```

## 项目捐款

## 技术栈
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






我们现在要对这个数据中暴露给前端的数据为：
        fields = [
            "enterprise_name", "credit_code", "enterprise_nature",
            "enterprise_scale", "enterprise_intro", "industry",
            "job_name", "recruit_major", "recruit_number",
            "monthly_salary", "contact_person", "contact_phone",
            "company_address", "booth_number",
            "check_in_status", "is_alumni_enterprise", "email"
        ]


1.需要后端DRF实现对"enterprise_name", "credit_code","contact_phone""email","contact_person","booth_number","check_in_status","is_alumni_enterprise"的搜索功能的实现
2.筛选功能："enterprise_nature""enterprise_scale" "industry" "job_name" "recruit_major" ,"recruit_number""monthly_salary":需要提供一个筛选接口




需要实现以上两个功能，给出完整版代码


将以下字段：
enterprise_nature，enterprise_scale，industry，recruit_major，booth_number，check_in_status，is_alumni_enterprise
添加到
class RecruitmentInfoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    招聘信息视图集 - 提供列表和详情，支持搜索、过滤、排序
    """
    queryset = RecruitmentInfo.objects.all()  # 指定该视图集使用的查询集，获取所有招聘信息对象
    serializer_class = RecruitmentInfoSerializer  # 指定序列化器，用于数据的序列化和反序列化
    permission_classes = [IsAuthenticated]  # 权限类，要求用户必须已认证（JWT）才能访问
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]  # 过滤器后端，支持搜索和排序功能
    search_fields = ['enterprise_name', 'job_name']  # 指定可搜索的字段，允许通过搜索参数（如 ?search=关键词）进行模糊匹配
    ordering_fields = ['registration_time']  # 指定可排序的字段，允许通过排序参数（如 ?ordering=registration_time）进行排序
    ordering = ['-registration_time']  # 默认排序，按报名时间倒序排列
的`search_fields`字段中

## 用法



## 资费与量词计算

- 月份非自然月。如2022年11月15日20点30分付款，1个月的有效期至12月15日0点。 付款后立即生效。可随时升配套餐或转按量计费，均立即生效。规则详见 [计费文档](https://XXXX.com)。
- 会员时长精准计算：
  - 非自然月规则：付款时间 + N 天（月度 30 天 / 年度 365 天），最终过期时间时分秒置为 0 点（如 2022-11-15 20:30 付款→2022-12-15 00:00 过期）；
  - 累加规则：若用户当前会员未过期，新时长叠加到原过期时间后；若已过期 / 非会员，从付款时间开始计算；
  - 立即生效：付款成功后is_vip立即置为 True，无延迟。

## 许可证

```
MIT license
```

开源使用此许可证，暂不开源。