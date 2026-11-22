#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# @Time    : 2025/12/9 23:54
# @Author  : https://github.com/Skixkk
# @Email   : skixkk7@gmail.com
# @File    : urls.py
# @Version : 0.0.1 (SemVer规范：主版本.次版本.修订号)
# @Project : comuni_backend
# @IDE     : PyCharm 
# ----------------------------------------------------------------------------
# 协作规范区
# @Dependencies: 
#     - requests>=2.25.1 (通过`requirements.txt`管理)
#     - package<version (版本冲突规避说明将在此写明，如无则通过`requirements.txt`配置)
# ----------------------------------------------------------------------------
# 法律声明区
# @License     : MIT
# @SPDX-License-Identifier: MIT
# @Copyright   : Copyright (c) 2025 by Skixkk , All Rights Reserved
# @Description : [Functional description of the file]
#     [功能描述]  Register the main URL
#     [技术架构]
# ----------------------------------------------------------------------------
from django.urls import path, include
from django.shortcuts import redirect
from rest_framework.routers import DefaultRouter

from users.views import (
    index, UserViewSetV1, GroupViewSetV1, UserVipInfoViewSet,
    MyObtainTokenPairView, LoginView, UserInfoViewSet,
    CustomAuthToken, WeChatMiniLoginAPIView, PasswordLoginAPIView,
    BindWeChatAPIView, FollowViewSet)
from users.student_profile_views import (
    StudentProfileParseTaskView,
    StudentProfileParseResultView,
    StudentProfileDetailView,
)

from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView  # TokenObtainPairView,

# 定义重定向视图（也可直接用redirect函数）
def index_redirect(request):
    # 永久重定向（301）到根路径，
    # 也可用 redirect('/', permanent=False) 临时重定向（302）
    return redirect('/', permanent=True)

router_v1 = DefaultRouter()
router_v1.register(r"users/user", UserViewSetV1, basename="user")
router_v1.register(r"auth/group", GroupViewSetV1, basename="group")
router_v1.register(r'user-info', UserInfoViewSet, basename='user-info')
router_v1.register(r"user/vip", UserVipInfoViewSet, basename="vip")
router_v1.register(r"user/follow", FollowViewSet, basename="follow")
urlpatterns = [
    path('', index, name='index'),
    path('index/', index_redirect, name='index_redirect'),
    path('api/v1/auth/', include(router_v1.urls)),
    # 学生能力画像（异步解析 + 最近一次结果）
    path(
        'api/v1/auth/user/student-profile/parse/task/',
        StudentProfileParseTaskView.as_view(),
        name='student_profile_parse_task',
    ),
    path(
        'api/v1/auth/user/student-profile/parse/result/',
        StudentProfileParseResultView.as_view(),
        name='student_profile_parse_result',
    ),
    path(
        'api/v1/auth/user/student-profile/',
        StudentProfileDetailView.as_view(),
        name='student_profile_detail',
    ),
    # 登录接口
    path('api/v1/login/', LoginView.as_view()),
    # 微信小程序登录
    path('api/v1/auth/wechat/mini/login/', WeChatMiniLoginAPIView.as_view(), name='wechat_mini_login'),
    path("api/v1/auth/password/login/", PasswordLoginAPIView.as_view(), name="password_login"),
    # 微信绑定(需登录)
    path('api/v1/auth/wechat/mini/bind', BindWeChatAPIView.as_view(), name='bind_wechat'),
    path('api/v1/token/', CustomAuthToken.as_view(), name='api_token_auth'),
    # 认证相关
    path('api/v1/token/rest/token', MyObtainTokenPairView.as_view(), name='token_obtain_pair'),  # 获取 Token TokenObtainPairView
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),  # 刷新 Token
    path('api/v1/token/verify/', TokenVerifyView.as_view(), name='token_verify'),  # 验证 Token
]
