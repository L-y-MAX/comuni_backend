# -*- coding: utf-8 -*-
"""账号安全：修改密码。"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = str(request.data.get('old_password') or '')
        new_password = str(request.data.get('new_password') or '')
        confirm_password = str(request.data.get('confirm_password') or '')

        if not old_password or not new_password:
            return Response(
                {'detail': '原密码和新密码不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_password != confirm_password:
            return Response(
                {'detail': '两次输入的新密码不一致'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.user.check_password(old_password):
            return Response(
                {'detail': '原密码不正确'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if old_password == new_password:
            return Response(
                {'detail': '新密码不能与原密码相同'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(new_password) < 6:
            return Response(
                {'detail': '新密码至少 6 位'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        return Response({'message': '密码修改成功'})
