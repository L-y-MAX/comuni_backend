#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/3/9 22:46
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : serializers.py
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
from rest_framework import serializers
from .models import RecruitmentInfo


class RecruitmentInfoSerializer(serializers.ModelSerializer):
    """序列化指定的招聘信息字段（仅返回业务核心字段）"""

    class Meta:
        model = RecruitmentInfo
        # 字段需与模型一致，或用fields = "__all__"返回所有字段
        fields = [
            "id", "enterprise_name", "credit_code", "enterprise_nature",
            "enterprise_scale", "enterprise_intro", "industry", "job_name",
            "recruit_major", "recruit_number", "monthly_salary", "contact_person",
            "contact_phone", "company_address", "booth_number", "check_in_status",
            "is_alumni_enterprise", "email"
        ]

class EnterpriseNatureSerializer(serializers.Serializer):
    """
    企业性质序列化器 - 用于返回企业性质选项列表
    实际返回字符串列表，该序列化器仅用于文档/验证，不是必须的
    """
    value = serializers.CharField()