# -*- coding: utf-8 -*-
"""学生能力画像 API。

路由：
- POST /api/v1/auth/user/student-profile/parse/task/
- GET  /api/v1/auth/user/student-profile/parse/result/?task_id=...
- GET  /api/v1/auth/user/student-profile/
"""

import uuid

from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .tasks import (
    TASK_CACHE_TTL,
    parse_student_profile_task,
    profile_cache_key,
    task_cache_key,
)


class StudentProfileParseTaskView(APIView):
    """创建一个学生画像解析任务，立即返回 task_id。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data
        if not isinstance(payload, dict):
            return Response(
                {'error': '请求体必须是 JSON 对象'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not str(payload.get('major') or '').strip():
            return Response(
                {'error': '专业不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not str(payload.get('skills_text') or '').strip():
            return Response(
                {'error': '专业技能不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_id = uuid.uuid4().hex
        cache.set(
            task_cache_key(task_id),
            {'status': 'PENDING', 'user_id': str(request.user.id)},
            TASK_CACHE_TTL,
        )

        try:
            parse_student_profile_task.delay(
                task_id,
                str(request.user.id),
                dict(payload),
            )
        except Exception as exc:
            cache.set(
                task_cache_key(task_id),
                {'status': 'FAILURE', 'error': f'任务队列不可用：{exc}'},
                TASK_CACHE_TTL,
            )
            return Response(
                {'error': f'任务队列不可用：{exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {'task_id': task_id, 'status': 'PENDING'},
            status=status.HTTP_202_ACCEPTED,
        )


class StudentProfileParseResultView(APIView):
    """轮询任务结果。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        task_id = str(request.query_params.get('task_id') or '').strip()
        if not task_id:
            return Response(
                {'status': 'FAILURE', 'error': '缺少 task_id 参数'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = cache.get(task_cache_key(task_id))
        if not result:
            return Response({
                'status': 'FAILURE',
                'error': '任务不存在或已过期，请重新生成',
            })

        if str(result.get('user_id') or '') != str(request.user.id):
            return Response(
                {'status': 'FAILURE', 'error': '无权查看该任务'},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(result)


class StudentProfileDetailView(APIView):
    """读取最近一次画像。

    没有画像时返回 200 + profile:null，而不是 404：
    前端把 404 当“未生成”，但控制台会留下红色报错，比赛演示不好看。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = cache.get(profile_cache_key(str(request.user.id)))
        return Response({'profile': profile})
