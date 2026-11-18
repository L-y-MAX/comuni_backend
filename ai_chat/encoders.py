#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2026/2/22 1:29
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : encoders.py
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
import json
from rest_framework.utils.encoders import JSONEncoder

class CustomJSONEncoder(JSONEncoder):
    """
    自定义JSON编码器，处理EncodeError等无法序列化的异常类型
    """
    def default(self, obj):
        # 处理EncodeError及其他异常类型
        if isinstance(obj, BaseException):
            return {
                'error_type': type(obj).__name__,
                'error_message': str(obj),
                'args': obj.args
            }
        # 处理其他不可序列化对象（如datetime等）
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)