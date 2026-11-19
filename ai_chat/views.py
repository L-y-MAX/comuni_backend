# 1. 移除错误的 Celery status 导入
# from celery.bin.control import status  # 错误导入，已删除
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
# 2. 导入 DRF 正确的 status 模块（包含 HTTP 状态码常量）
from rest_framework import status  # 正确导入
from celery.result import AsyncResult
from django.conf import settings
from .encoders import CustomJSONEncoder
import json

from .tasks import call_qwen_api


class AIChatTaskView(APIView):
    """创建AI聊天异步任务（前端发起请求的入口）"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user or not user.is_active:
            return Response({"detail": "未找到该用户", "code": "user_not_found"}, status=401)
        # 1. 校验前端参数
        current_article = request.data.get('current_article', {})
        history_messages = request.data.get('history_messages', [])
        user_message = request.data.get('user_message', '')

        if not user_message:
            return Response(
                {'error': '用户问题不能为空'},
                # 3. 使用 DRF status 模块的正确常量
                status=status.HTTP_400_BAD_REQUEST  # 修复：使用DRF的状态码
            )

        # 2. 提交异步任务到Celery
        try:
            task = call_qwen_api.delay(current_article, history_messages, user_message)
        except Exception as e:
            # 常见原因：Redis 没启动 / 密码不对 / Celery broker 地址不对
            return Response(
                {'error': f'AI 任务队列不可用：{e}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 3. 立即返回任务ID，前端用这个ID轮询结果（核心：不等待阿里云响应）
        return Response({
            'task_id': task.id,
            'status': 'pending',
            'message': 'Submitted, processing'
        }, 
        # 4. 使用 DRF status 模块的正确常量
        status=status.HTTP_202_ACCEPTED)  # 修复：使用DRF的状态码

class AIChatResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        查询异步任务结果接口
        关键修复：
        1. 彻底隔离原始异常对象，确保响应数据仅包含可序列化类型
        2. 使用自定义编码器处理可能的序列化问题
        """
        task_id = request.GET.get('task_id')
        if not task_id:
            return Response({
                "status": "FAILURE",
                "data": {"status": "failed", "error": "缺少task_id参数"}
            }, status=status.HTTP_400_BAD_REQUEST)  # 统一使用DRF状态码

        try:
            # 获取Celery任务结果
            task = AsyncResult(task_id)

            # 初始化响应数据
            response_data = {
                "task_id": task_id,
                "status": task.state,
                "data": {}
            }

            # 任务状态处理（核心修复）
            if task.state == 'SUCCESS':
                # 确保任务返回结果是标准化字典
                result_data = task.result if isinstance(task.result, dict) else {
                    "status": "failed",
                    "error": f"任务返回格式异常: {str(task.result)}"
                }
                response_data["data"] = result_data

            elif task.state == 'FAILURE':
                # 关键修复：绝不返回原始异常对象，只返回字符串描述
                error_msg = str(task.result) if task.result else "任务执行失败"
                response_data["data"] = {
                    "status": "failed",
                    "error": error_msg,
                    "error_type": type(task.result).__name__ if task.result else "UnknownError"
                }

            else:
                # 任务仍在处理中
                response_data["message"] = "任务处理中，请稍后查询"

            # 使用自定义编码器确保数据可序列化
            serialized_data = json.loads(json.dumps(response_data, cls=CustomJSONEncoder))
            return Response(serialized_data)

        except Exception as e:
            # 捕获视图层所有异常，确保返回可序列化的错误信息
            error_response = {
                "task_id": task_id,
                "status": "FAILURE",
                "data": {
                    "status": "failed",
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            }
            # 使用自定义编码器处理
            serialized_error = json.loads(json.dumps(error_response, cls=CustomJSONEncoder))
            return Response(serialized_error, status=status.HTTP_500_INTERNAL_SERVER_ERROR)  # 统一使用DRF状态码