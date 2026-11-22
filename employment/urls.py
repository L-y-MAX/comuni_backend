#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/3/9 22:47
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
# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (RecruitmentInfoViewSet, EnterpriseNameViewSet, EnterpriseNatureViewSet,
                    JobNameViewSet, IndustryViewSet, RecruitMajorViewSet, MonthlySalaryViewSet,
                    RecruitNumberViewSet, CheckInStatusViewSet, IsAlumniEnterpriseViewSet)
from .career_favorite_views import CareerResourceFavoriteView

router = DefaultRouter()

# 注册招聘信息主接口
router.register(r'employment/recruitments', RecruitmentInfoViewSet, basename='recruitment')

# 注册各个字段的去重筛选接口
router.register(r'employment/filters/enterprise-names', EnterpriseNameViewSet, basename='filter-enterprise-names')
router.register(r'employment/filters/enterprise-natures', EnterpriseNatureViewSet, basename='filter-enterprise-natures')
router.register(r'employment/filters/job-names', JobNameViewSet, basename='filter-job-names')
router.register(r'employment/filters/industries', IndustryViewSet, basename='filter-industries')
router.register(r'employment/filters/recruit-majors', RecruitMajorViewSet, basename='filter-recruit-majors')
router.register(r'employment/filters/monthly-salaries', MonthlySalaryViewSet, basename='filter-monthly-salaries')
router.register(r'employment/filters/recruit-numbers', RecruitNumberViewSet, basename='filter-recruit-numbers')
router.register(r'employment/filters/check-in-statuses', CheckInStatusViewSet, basename='filter-check-in-statuses')
router.register(r'employment/filters/is-alumni-enterprises', IsAlumniEnterpriseViewSet,
                basename='filter-is-alumni-enterprises')

urlpatterns = [
    path(
        "api/v1/employment/career-resource-favorites/",
        CareerResourceFavoriteView.as_view(),
        name="career-resource-favorites",
    ),
    path("api/v1/", include(router.urls)),
]
