# -*- coding: utf-8 -*-
"""就业资源收藏接口。

前端只同步“收藏标题”，资源详情仍在本地 CAREER_RESOURCES 里查。
为比赛演示避免数据库迁移，收藏列表存在 Redis，按用户隔离。
"""

from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

FAVORITE_CACHE_TTL = 30 * 24 * 60 * 60
MAX_FAVORITES = 200


def _favorite_key(user_id) -> str:
    return f'career_resource_favorites:{user_id}'


class CareerResourceFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        titles = cache.get(_favorite_key(request.user.id)) or []
        if not isinstance(titles, list):
            titles = []
        return Response({'titles': titles})

    def post(self, request):
        title = str(request.data.get('title') or '').strip()
        if not title:
            return Response(
                {'error': 'title 不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        titles = cache.get(_favorite_key(request.user.id)) or []
        if not isinstance(titles, list):
            titles = []
        if title not in titles:
            titles.append(title)
            titles = titles[-MAX_FAVORITES:]
            cache.set(_favorite_key(request.user.id), titles, FAVORITE_CACHE_TTL)

        return Response({'title': title}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        title = str(request.query_params.get('title') or '').strip()
        if not title:
            return Response(
                {'error': 'title 不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        titles = cache.get(_favorite_key(request.user.id)) or []
        if isinstance(titles, list) and title in titles:
            titles = [item for item in titles if item != title]
            cache.set(_favorite_key(request.user.id), titles, FAVORITE_CACHE_TTL)

        return Response(status=status.HTTP_204_NO_CONTENT)
