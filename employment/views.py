# views.py
from rest_framework import viewsets, status, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import RecruitmentInfo
from .serializers import RecruitmentInfoSerializer


class BaseDistinctFieldViewSet(viewsets.ViewSet):
    """
    通用基类：用于获取单个字段()的去重列表

    'enterprise_name',  # 企业名称
    'enterprise_nature',  # 企业性质: 私营企业
    'job_name',  # 按 岗位名称 筛选
    'industry',  # 按 行业 筛选
    'recruit_major',  # 按 招聘专业 筛选
    'monthly_salary',  # 按 月薪 筛选
    'recruit_number',  # 按 招聘人数 筛选
    'check_in_status',  # 按 签到状态 筛选
    'is_alumni_enterprise',  # 按 是否校友企业 筛选

    子类只需定义 `field_name` 属性
    """
    permission_classes = [IsAuthenticated]
    field_name = None  # 子类必须覆盖此字段

    def list(self, request):
        if not self.field_name:
            return Response({"detail": "Configuration error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 获取数据并去重
        values = RecruitmentInfo.objects.values_list(self.field_name, flat=True)
        # 过滤空值、去重、排序
        unique_values = sorted(list({v for v in values if v is not None and v != ''}))
        return Response(unique_values, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        return Response({"detail": "Method not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


# --- 具体字段的视图集 ---

class EnterpriseNameViewSet(BaseDistinctFieldViewSet):
    field_name = 'enterprise_name'


class EnterpriseNatureViewSet(BaseDistinctFieldViewSet):
    field_name = 'enterprise_nature'


class JobNameViewSet(BaseDistinctFieldViewSet):
    field_name = 'job_name'


class IndustryViewSet(BaseDistinctFieldViewSet):
    field_name = 'industry'


class RecruitMajorViewSet(BaseDistinctFieldViewSet):
    field_name = 'recruit_major'


class MonthlySalaryViewSet(BaseDistinctFieldViewSet):
    field_name = 'monthly_salary'


class RecruitNumberViewSet(BaseDistinctFieldViewSet):
    field_name = 'recruit_number'


class CheckInStatusViewSet(BaseDistinctFieldViewSet):
    field_name = 'check_in_status'


class IsAlumniEnterpriseViewSet(BaseDistinctFieldViewSet):
    field_name = 'is_alumni_enterprise'


class RecruitmentInfoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    招聘信息视图集 - 提供列表和详情，支持搜索、排序以及按企业性质过滤
    """
    queryset = RecruitmentInfo.objects.all()
    serializer_class = RecruitmentInfoSerializer
    permission_classes = [IsAuthenticated]

    # 添加 DjangoFilterBackend 实现按字段精确过滤
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # 定义允许过滤的字段（支持 ?enterprise_nature=私营企业 这样的查询）
    filterset_fields = [
        'enterprise_name',  # 企业名称
        'enterprise_nature',  # 企业性质: 私营企业
        'job_name',  # 按 岗位名称 筛选
        'industry',  # 按 行业 筛选
        'recruit_major',  # 按 招聘专业 筛选
        'monthly_salary',  # 按 月薪 筛选
        'recruit_number',  # 按 招聘人数 筛选
        'check_in_status',  # 按 签到状态 筛选
        'is_alumni_enterprise',  # 按 是否校友企业 筛选
    ]

    # 搜索字段（?search=关键词）- 所有字段为“或”关系
    search_fields = [
        'enterprise_name',  # 搜索企业名称 & 筛选一个企业的岗位（True）
        'job_name',  # 搜索岗位名称
        'credit_code',  # 进入详情页 & 筛选一个企业的岗位(/直接搜索名称True)
        'industry',  # 分类 行业
        'recruit_major',  # 分类 招聘专业
        'monthly_salary',  # 分类 月薪
        'recruit_number',  # 分类 招聘人数
        'check_in_status',  # 分类 签到状态
        'is_alumni_enterprise'  # 分类 是否校友企业
    ]

    # 排序字段（?ordering=registration_time 或 ?ordering=-registration_time）
    ordering_fields = [
        'enterprise_name',
        'registration_time',
        'job_name',  # 按岗位名称排序
        'monthly_salary',
        'industry',
        'is_alumni_enterprise',
        'check_in_status',
        'recruit_number',
        'recruit_major',
    ]
    ordering = ['-registration_time']  # 默认排序
