from django.http import Http404
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied  # 导入DRF的权限异常
from rest_framework import viewsets, status, pagination, serializers, permissions, filters
from django_redis import get_redis_connection
import json
import uuid
from uuid import UUID  # 新增：导入UUID类型
from json import JSONEncoder  # 新增：导入JSON编码器基类
from django.db.models import Q
from django.db.models import F
from django.shortcuts import get_object_or_404
import re  # 新增：导入正则表达式用于输入校验

from rest_framework.viewsets import GenericViewSet

from users.serializers import UserSearchSerializer
from .models import (
    User, KnowledgeBase, KnowledgeShare, KnowledgeNode, PermissionLevel,
    Comment, NodeTag, NodeHistory, CommentType, CommentNotification,
    UserFollowKnowledgeBase
)
from .pagination import KnowledgeNodeListPagination
from .serializers import (
    NodeTagSerializer, KnowledgeBaseSerializer, KnowledgeNodeSerializer,
    NodeHistorySerializer, KnowledgeShareSerializer, KnowledgeNodeListSerializer,
    CommentRootSerializer, CommentAnswerSerializer, CommentNotificationSerializer,
    NodeCommentAnswerSerializer, NodeCommentRootSerializer, NodeCommentCreateSerializer,
    NodeCommentNotificationSerializer, NodeComment, NodeCommentNotification,
    CommentTypeChoices, UserFollowKnowledgeBaseSerializer, KnowledgeBaseMiniSerializer
)
from .utils.permission import (
    check_knowledge_permission,
    require_view_permission,
    require_edit_permission,
    require_admin_permission, NodeCommentPermission
)


# 新增：SQL注入防护工具函数
def sanitize_input(input_str: str) -> str:
    """
    清理用户输入，移除SQL注入相关危险字符
    仅用于补充防护，核心防护仍依赖ORM参数化查询
    """
    if not input_str:
        return ""
    # 移除SQL注入常见危险字符/关键词（大小写不敏感）
    dangerous_patterns = [
        r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|UNION|JOIN)\b',
        r'(--|#|;|\'|"|\\|\/|\*|\%|\=|\>|\<)',
        r'\b(OR|AND|NOT)\s+1\=1\b',
        r'\bNULL\b',
        r'\bLIKE\b.*\%',
    ]
    sanitized = input_str
    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
    # 限制输入长度（防止超长输入攻击）
    return sanitized[:500]  # 限制最大长度为500字符


def validate_uuid(uuid_str: str) -> bool:
    """校验UUID格式是否合法，防止恶意UUID注入"""
    try:
        UUID(uuid_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_numeric_id(id_str: str) -> bool:
    """校验数字ID是否合法，防止非数字注入"""
    if not id_str:
        return False
    return re.match(r'^\d+$', id_str) is not None


# 新增：自定义JSON编码器，处理UUID类型
class UUIDEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # 将UUID对象转换为字符串（核心修复逻辑）
            return str(obj)
        # 其他类型沿用默认序列化逻辑
        return super().default(obj)


# ========== 1. 知识库视图集（含共享/评论扩展） ==========
class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """知识库视图集（含共享权限控制）"""
    serializer_class = KnowledgeBaseSerializer
    # 基础权限：仅登录用户可访问（解决403的核心）
    permission_classes = [IsAuthenticated]

    # 【新增】复制节点到当前知识库的接口
    @action(detail=True, methods=["post"], url_path="nodes/(?P<node_id>[^/.]+)/copy")
    def copy_node(self, request, pk=None, node_id=None):
        """
        复制指定节点到当前知识库
        URL: /api/v1/knowledge-bases/{kb_id}/nodes/{node_id}/copy/
        权限：需要目标知识库的编辑权限
        """
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(pk):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not validate_uuid(node_id):
                return Response(
                    {"detail": "无效的节点ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 1. 校验目标知识库的编辑权限
            target_kb = require_edit_permission(request.user, pk)
            # 2. 获取源节点并校验访问权限
            source_node = get_object_or_404(KnowledgeNode, id=node_id)
            # 校验源节点的访问权限（至少能查看）
            require_view_permission(request.user, source_node.knowledge_base.id)

            # 3. 复制节点核心逻辑（排除id/knowledge_base，新增名称标识）
            # SQL注入防护：清理节点名称输入
            sanitized_name = sanitize_input(source_node.name)
            node_data = {
                "name": f"『复制』{sanitized_name}",  # 『复制』【复制】新增复制标识
                "content": source_node.content,
                "description": source_node.description,
                "node_type": source_node.node_type,
                "sort_order": source_node.sort_order,
                "creator": request.user.id,  # 复制者为当前用户
                "knowledge_base": target_kb.id,  # 目标知识库
                # 可根据需要复制其他字段（标签/历史等）
            }

            # 4. 创建新节点
            serializer = KnowledgeNodeSerializer(data=node_data)
            serializer.is_valid(raise_exception=True)
            new_node = serializer.save()

            # 5. 返回成功响应
            return Response({
                "code": 200,
                "msg": "节点复制成功",
                "data": KnowledgeNodeSerializer(new_node).data
            }, status=status.HTTP_201_CREATED)

        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeNode.DoesNotExist:
            return Response(
                {"detail": "源节点不存在"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"复制节点失败：{str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # 以下为原有代码（保持不变）
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return KnowledgeBase.objects.none()

        # 获取用户已关注的公开知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        # 自己创建的 + 被共享的 + 公开且已关注的知识库
        return KnowledgeBase.objects.filter(
            Q(creator=user) |
            Q(shares__shared_to=user) |
            Q(id__in=followed_public_kb_ids)
        ).distinct().order_by("-updated_at")

    # 重写查询集：用户只能看到自己创建的 + 被共享的 + 公开且已关注的知识库
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return KnowledgeBase.objects.none()

        # 获取用户已关注的公开知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        # 自己创建的 + 被共享的 + 公开且已关注的知识库
        return KnowledgeBase.objects.filter(
            Q(creator=user) |
            Q(shares__shared_to=user) |
            Q(id__in=followed_public_kb_ids)
        ).distinct().order_by("-updated_at")

    # ========== 新增：三个独立的知识库分类接口 ==========
    @action(detail=False, methods=["get"], url_path="my-knowledge-bases")
    def my_knowledge_bases(self, request):
        """
        我的知识库接口：仅返回当前用户创建的知识库
        URL: /api/v1/knowledge/knowledgebase/my-knowledge-bases/
        """
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"code": 401, "msg": "请先登录"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # 仅筛选当前用户创建的知识库
        queryset = KnowledgeBase.objects.filter(
            creator=user
        ).distinct().order_by("-updated_at")
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "count": queryset.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=["get"], url_path="shared-to-me")
    def shared_to_me(self, request):
        """
        分享给我的知识库接口：仅返回共享给当前用户的知识库
        URL: /api/v1/knowledge/knowledgebase/shared-to-me/
        """
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"code": 401, "msg": "请先登录"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # 仅筛选共享给当前用户的知识库
        queryset = KnowledgeBase.objects.filter(
            shares__shared_to=user
        ).distinct().order_by("-updated_at")
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "count": queryset.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=["get"], url_path="followed-knowledge-bases")
    def followed_knowledge_bases(self, request):
        """
        关注的知识库接口：仅返回当前用户关注的知识库（已激活的关注记录）
        URL: /api/v1/knowledge/knowledgebase/followed-knowledge-bases/
        """
        user = request.user
        if not user.is_authenticated:
            return Response(
                {"code": 401, "msg": "请先登录"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # 先获取当前用户已激活的关注记录
        follow_records = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True
        )
        # 提取关注的知识库ID并查询详情
        kb_ids = follow_records.values_list("knowledge_base_id", flat=True)
        queryset = KnowledgeBase.objects.filter(
            id__in=kb_ids
        ).distinct().order_by("-updated_at")
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "count": queryset.count(),
            "results": serializer.data
        })

    # 3. 创建知识库：自动关联创建者，无需额外权限（创建者默认有最高权限）
    def perform_create(self, serializer):
        """创建时自动绑定当前登录用户为创建者"""
        # SQL注入防护：清理知识库名称和描述
        if 'name' in serializer.validated_data:
            serializer.validated_data['name'] = sanitize_input(serializer.validated_data['name'])
        if 'description' in serializer.validated_data:
            serializer.validated_data['description'] = sanitize_input(serializer.validated_data['description'])
        serializer.save(creator=self.request.user)

    # 4. 核心CRUD接口（绑定你的权限校验函数）
    def retrieve(self, request, *args, **kwargs):
        """查看知识库：校验查看权限"""
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(kwargs["pk"]):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            knowledge_base = require_view_permission(request.user, kwargs["pk"])
            serializer = self.get_serializer(knowledge_base)
            return Response(serializer.data)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    def update(self, request, *args, **kwargs):
        """编辑知识库：校验编辑权限（participant/admin）"""
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(kwargs["pk"]):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # SQL注入防护：清理输入数据
            sanitized_data = request.data.copy()
            if 'name' in sanitized_data:
                sanitized_data['name'] = sanitize_input(sanitized_data['name'])
            if 'description' in sanitized_data:
                sanitized_data['description'] = sanitize_input(sanitized_data['description'])

            knowledge_base = require_edit_permission(request.user, kwargs["pk"])
            serializer = self.get_serializer(knowledge_base, data=sanitized_data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    def destroy(self, request, *args, **kwargs):
        """删除知识库：校验管理权限（仅admin/创建者）"""
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(kwargs["pk"]):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            knowledge_base = require_admin_permission(request.user, kwargs["pk"])
            knowledge_base.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    # 5. 共享相关接口（基于你的权限函数）
    @action(detail=True, methods=["post"], url_path="share")
    def share_knowledge(self, request, pk=None):
        """
        共享知识库：仅管理员/创建者可操作
        共享知识库给指定用户
        请求数据：{ "shared_to_id": "用户ID", "permission_level": "admin/participant/viewer" }
        """
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(pk):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # SQL注入防护：校验用户ID格式
            shared_to_id = request.data.get("shared_to_id")
            if shared_to_id and not (validate_uuid(shared_to_id) or validate_numeric_id(shared_to_id)):
                return Response(
                    {"detail": "无效的用户ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            knowledge_base = require_admin_permission(request.user, pk)
            permission_level = request.data.get("permission_level")

            # 参数校验
            if not shared_to_id or permission_level not in PermissionLevel.values:
                return Response(
                    {"code": 400, "msg": "参数错误：shared_to_id必填，permission_level需为admin/participant/viewer"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 创建/更新共享关系
            share, created = KnowledgeShare.objects.update_or_create(
                knowledge_base=knowledge_base,
                shared_to_id=shared_to_id,
                defaults={"permission_level": permission_level}
            )

            return Response({
                "code": 200,
                "msg": "共享成功" if created else "权限更新成功",
                "data": KnowledgeShareSerializer(share).data
            })
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["delete"], url_path="unshare")
    def unshare_knowledge(self, request, pk=None):
        """移除共享：仅管理员/创建者可操作"""
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(pk):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # SQL注入防护：校验用户ID格式
            shared_to_id = request.data.get("shared_to_id")
            if shared_to_id and not (validate_uuid(shared_to_id) or validate_numeric_id(shared_to_id)):
                return Response(
                    {"detail": "无效的用户ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not shared_to_id:
                return Response(
                    {"code": 400, "msg": "shared_to_id必填"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 移除共享关系
            KnowledgeShare.objects.filter(
                knowledge_base=knowledge_base,
                shared_to_id=shared_to_id
            ).delete()
            return Response({"code": 200, "msg": "移除共享成功"})
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["get"], url_path="share-list")
    def get_share_list(self, request, pk=None):
        """查看共享列表：仅有权限的用户可操作"""
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(pk):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            knowledge_base = require_view_permission(request.user, pk)
            shares = KnowledgeShare.objects.filter(knowledge_base=knowledge_base)
            return Response({
                "code": 200,
                "data": KnowledgeShareSerializer(shares, many=True).data
            })
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    # 6. 评论相关接口
    @action(detail=True, methods=["post"], url_path="add-comment")
    def add_comment(self, request, pk=None):
        """添加评论：仅需查看权限"""
        try:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(pk):
                return Response(
                    {"detail": "无效的知识库ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            knowledge_base = require_view_permission(request.user, pk)
            node_id = request.data.get("node_id")

            # SQL注入防护：校验节点ID格式
            if node_id and not validate_uuid(node_id):
                return Response(
                    {"detail": "无效的节点ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # SQL注入防护：清理评论内容
            content = sanitize_input(request.data.get("comment_text", ""))

            if not content:
                return Response(
                    {"code": 400, "msg": "评论内容不能为空"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 创建评论（关联当前登录用户为评论者）
            # 修复：content → comment_text（模型实际字段名）
            comment = Comment.objects.create(
                knowledge_base=knowledge_base,
                node_id=node_id,
                commented_by=request.user,  # commented_by（模型字段名）
                comment_text=content  # comment_text
            )

            return Response({
                "code": 200,
                "data": CommentRootSerializer(comment).data
            })
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )


# ========== 新增：用户关注知识库视图集 ==========
class UserFollowKnowledgeBaseViewSet(viewsets.ModelViewSet):
    """
    用户关注知识库视图集
    核心功能：
    - 关注/取消关注知识库（软删除，通过is_active字段控制）
    - 仅返回当前用户的关注记录
    - 禁用物理删除，强制使用软删除
    """
    serializer_class = UserFollowKnowledgeBaseSerializer
    permission_classes = [IsAuthenticated]  # 仅登录用户可操作
    http_method_names = ["get", "post", "patch", "head", "options"]  # 禁用delete

    def get_queryset(self):
        """仅返回当前用户的关注记录，支持按关注状态筛选"""
        queryset = UserFollowKnowledgeBase.objects.filter(user=self.request.user)

        # 支持按关注状态筛选：?is_active=true/false
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset.order_by("-follow_time")

    def create(self, request, *args, **kwargs):
        """创建关注记录：校验知识库存在 + 避免重复关注"""
        knowledge_base_id = request.data.get("knowledge_base")

        # SQL注入防护：校验UUID格式
        if not knowledge_base_id or not validate_uuid(knowledge_base_id):
            return Response(
                {"code": 400, "msg": "知识库ID（knowledge_base）不能为空且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 校验知识库存在
        try:
            knowledge_base = KnowledgeBase.objects.get(id=knowledge_base_id)
        except (KnowledgeBase.DoesNotExist, ValueError):
            return Response(
                {"code": 404, "msg": "指定的知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 检查是否已关注（避免重复）
        existing_follow = UserFollowKnowledgeBase.objects.filter(
            user=request.user,
            knowledge_base=knowledge_base
        ).first()

        if existing_follow:
            # 如果已关注但is_active=False，恢复关注
            if not existing_follow.is_active:
                existing_follow.is_active = True
                existing_follow.save(update_fields=["is_active"])
                return Response({
                    "code": 200,
                    "msg": "恢复关注成功",
                    "data": UserFollowKnowledgeBaseSerializer(existing_follow).data
                })
            else:
                return Response(
                    {"code": 400, "msg": "你已关注该知识库，无需重复关注"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 绑定当前用户并创建关注记录
        request.data["user"] = request.user.id
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """自定义部分更新：仅允许修改is_active字段（取消/恢复关注）"""
        instance = self.get_object()

        # 仅允许更新is_active字段
        if "is_active" not in request.data:
            return Response(
                {"error": "仅允许更新is_active字段（true/false）"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 调用序列化器的校验逻辑处理取消时间
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """禁用物理删除，引导使用软删除"""
        return Response(
            {"error": "不允许删除关注记录，请通过PATCH修改is_active字段取消关注"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=False, methods=["get"], url_path="followed-bases")
    def get_followed_bases(self, request):
        """快捷接口：获取当前用户已关注的所有知识库详情"""
        # 筛选已激活的关注记录
        follow_records = self.get_queryset().filter(is_active=True)
        # 提取知识库ID并查询详情
        kb_ids = follow_records.values_list("knowledge_base_id", flat=True)
        knowledge_bases = KnowledgeBase.objects.filter(id__in=kb_ids)

        return Response({
            "code": 200,
            "count": knowledge_bases.count(),
            "results": KnowledgeBaseSerializer(knowledge_bases, many=True).data
        })

    # ========== 新增：专门的取消关注接口 ==========
    @action(detail=False, methods=["post"], url_path="unfollow")
    def unfollow(self, request):
        """
        取消关注知识库接口（简化前端调用）
        URL: /api/v1/knowledge/user-follow-knowledgebase/unfollow/
        请求体：{ "knowledge_base": "知识库UUID" }
        逻辑：将指定知识库的关注记录标记为is_active=False
        """
        # 1. 获取并校验参数
        knowledge_base_id = request.data.get("knowledge_base")

        # SQL注入防护：校验UUID格式
        if not knowledge_base_id or not validate_uuid(knowledge_base_id):
            return Response(
                {"code": 400, "msg": "知识库ID（knowledge_base）不能为空且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 校验知识库存在
        try:
            knowledge_base = KnowledgeBase.objects.get(id=knowledge_base_id)
        except (KnowledgeBase.DoesNotExist, ValueError):
            return Response(
                {"code": 404, "msg": "指定的知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 3. 查询当前用户对该知识库的关注记录
        follow_record = UserFollowKnowledgeBase.objects.filter(
            user=request.user,
            knowledge_base=knowledge_base,
            is_active=True
        ).first()

        if not follow_record:
            return Response(
                {"code": 400, "msg": "你尚未关注该知识库"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. 标记为取消关注（软删除）
        follow_record.is_active = False
        follow_record.save(update_fields=["is_active"])

        return Response({
            "code": 200,
            "msg": "取消关注成功",
            "data": UserFollowKnowledgeBaseSerializer(follow_record).data
        })


# ========== 2. 知识库节点视图集 ==========
class KnowledgeNodeViewSet(viewsets.ModelViewSet):
    """节点视图集（权限继承知识库）"""
    serializer_class = KnowledgeNodeSerializer
    lookup_field = "id"  # 明确指定UUID查询

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return KnowledgeNode.objects.none()

        # 获取用户已关注的公开知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        # 可访问的知识库：自己创建 + 被共享 + 公开且已关注
        accessible_kbs = KnowledgeBase.objects.filter(
            Q(creator=user) | Q(shares__shared_to=user) | Q(id__in=followed_public_kb_ids)
        )

        return KnowledgeNode.objects.filter(
            knowledge_base__in=accessible_kbs
        ).order_by("sort_order", "-created_at")

    # 核心修复：重写get_object，强制应用权限过滤
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        node_id = self.kwargs[lookup_url_kwarg]

        # SQL注入防护：校验UUID格式
        if not validate_uuid(node_id):
            raise Http404("Invalid node ID format.")

        try:
            obj = queryset.get(id=node_id)
        except KnowledgeNode.DoesNotExist:
            raise Http404("No KnowledgeNode matches the given query.")

        self.check_object_permissions(self.request, obj)
        return obj

    # 创建节点（需要编辑权限）
    def create(self, request, *args, **kwargs):
        try:
            knowledge_base_id = request.data.get("knowledge_base")

            # SQL注入防护：校验UUID格式
            if not knowledge_base_id or not validate_uuid(knowledge_base_id):
                return Response(
                    {"detail": "知识库ID不能为空且格式必须为UUID"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # SQL注入防护：清理输入数据
            sanitized_data = request.data.copy()
            if 'name' in sanitized_data:
                sanitized_data['name'] = sanitize_input(sanitized_data['name'])
            if 'content' in sanitized_data:
                sanitized_data['content'] = sanitize_input(sanitized_data['content'])
            if 'description' in sanitized_data:
                sanitized_data['description'] = sanitize_input(sanitized_data['description'])

            require_edit_permission(request.user, knowledge_base_id)  # 校验知识库的编辑权限
            serializer = self.get_serializer(data=sanitized_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    # 删除节点（需要管理权限）
    def destroy(self, request, *args, **kwargs):
        try:
            node = self.get_object()
            require_admin_permission(request.user, node.knowledge_base.id)
            return super().destroy(request, *args, **kwargs)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Http404:
            return Response(
                {"detail": "节点不存在或你无访问权限"},
                status=status.HTTP_404_NOT_FOUND
            )

    # 扩展：批量设置为文件夹（对接 admin.py 逻辑）
    @action(detail=False, methods=["post"])
    def batch_make_folder(self, request):
        """批量将节点设置为文件夹"""
        node_ids = request.data.get("node_ids", [])
        if not node_ids:
            return Response(
                {"error": "请传入节点ID列表"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SQL注入防护：校验所有节点ID格式
        for node_id in node_ids:
            if not validate_uuid(node_id):
                return Response(
                    {"error": f"无效的节点ID格式：{node_id}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        try:
            # 过滤用户有权限的节点
            user = request.user
            # 获取用户可编辑的知识库ID
            editable_kb_ids = []
            # 自己创建的知识库
            editable_kb_ids.extend(KnowledgeBase.objects.filter(creator=user).values_list("id", flat=True))
            # 被共享为participant/admin的知识库
            editable_kb_ids.extend(
                KnowledgeShare.objects.filter(
                    shared_to=user,
                    permission_level__in=[PermissionLevel.PARTICIPANT, PermissionLevel.ADMIN]
                ).values_list("knowledge_base_id", flat=True)
            )

            queryset = KnowledgeNode.objects.filter(
                id__in=node_ids,
                knowledge_base_id__in=editable_kb_ids
            )
            # 校验编辑权限（批量操作时）
            for node in queryset:
                require_edit_permission(user, node.knowledge_base.id)

            queryset.update(node_type=KnowledgeNode.NodeType.FOLDER)
            return Response({
                "message": f"成功将 {queryset.count()} 个节点设置为文件夹",
                "count": queryset.count()
            })
        except PermissionDenied as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Http404:
            return Response(
                {"detail": "该节点不存在，或你无访问权限"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"获取节点失败：{str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ========== 3. 知识库共享视图集 ==========
class KnowledgeShareViewSet(viewsets.ModelViewSet):
    """知识库共享视图集（补充权限控制）"""
    serializer_class = KnowledgeShareSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return KnowledgeShare.objects.none()
        # 只能看到自己创建的知识库的共享记录 + 共享给自己的记录
        return KnowledgeShare.objects.filter(
            Q(knowledge_base__creator=user) | Q(shared_to=user)
        ).distinct()

    # 创建共享（复用KnowledgeBaseViewSet的share接口，此处仅做权限校验）
    def create(self, request, *args, **kwargs):
        try:
            knowledge_base_id = request.data.get("knowledge_base")

            # SQL注入防护：校验UUID格式
            if not knowledge_base_id or not validate_uuid(knowledge_base_id):
                return Response(
                    {"detail": "知识库ID不能为空且格式必须为UUID"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # SQL注入防护：校验用户ID格式
            shared_to_id = request.data.get("shared_to_id")
            if shared_to_id and not (validate_uuid(shared_to_id) or validate_numeric_id(shared_to_id)):
                return Response(
                    {"detail": "无效的用户ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            require_admin_permission(request.user, knowledge_base_id)
            return super().create(request, *args, **kwargs)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "知识库不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    # 更新共享权限
    def update(self, request, *args, **kwargs):
        try:
            share = self.get_object()

            # SQL注入防护：校验用户ID格式
            shared_to_id = request.data.get("shared_to_id")
            if shared_to_id and not (validate_uuid(shared_to_id) or validate_numeric_id(shared_to_id)):
                return Response(
                    {"detail": "无效的用户ID格式"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            require_admin_permission(request.user, share.knowledge_base.id)
            return super().update(request, *args, **kwargs)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeShare.DoesNotExist:
            return Response(
                {"detail": "共享记录不存在"},
                status=status.HTTP_404_NOT_FOUND
            )

    # 删除共享记录
    def destroy(self, request, *args, **kwargs):
        try:
            share = self.get_object()
            require_admin_permission(request.user, share.knowledge_base.id)
            return super().destroy(request, *args, **kwargs)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeShare.DoesNotExist:
            return Response(
                {"detail": "共享记录不存在"},
                status=status.HTTP_404_NOT_FOUND
            )


# ===================== 评论分页配置（根评论分页，抖音风格） =====================
class CommentPagination(pagination.PageNumberPagination):
    """根评论分页配置：每页10条根评论（可按需调整）"""
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


# ===================== 回复评论分页配置 =====================
class NodeCommentAnswerPagination(pagination.PageNumberPagination):
    """回复评论分页配置：每页5条（适配前端按需加载）"""
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 20


# ===================== 评论视图集（高性能实现） =====================
class CommentViewSet(viewsets.ModelViewSet):
    """
    抖音风格评论视图集：
    1. 根评论分页查询（避免一次性加载所有）
    2. 批量查询评论+用户信息（避免N+1）
    3. 回复评论时自动创建通知
    4. 支持按需加载子评论
    """
    queryset = Comment.objects.all()
    pagination_class = CommentPagination

    # 修复：动态返回序列化器
    def get_serializer_class(self):
        """根据请求场景返回对应序列化器"""
        # 根评论列表/详情：使用根评论序列化器
        if self.action in ["list", "retrieve"] and self.request.query_params.get("type") == "root":
            return CommentRootSerializer
        # 回复评论/创建评论：使用回复评论序列化器
        return CommentAnswerSerializer

    def get_queryset(self):
        """高性能查询：根据场景过滤，避免冗余数据"""
        user = self.request.user
        article_id = self.request.query_params.get("article_id")

        # SQL注入防护：校验文章ID格式
        if article_id and not validate_uuid(article_id):
            return Comment.objects.none()

        if not article_id or not user.is_authenticated:
            return Comment.objects.none()

        # 获取用户可访问的知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        accessible_kb_ids = KnowledgeBase.objects.filter(
            Q(creator=user) | Q(shares__shared_to=user) | Q(id__in=followed_public_kb_ids)
        ).values_list("id", flat=True)

        # 先校验文章所属知识库是否可访问
        try:
            article = KnowledgeNode.objects.get(id=article_id)
            if article.knowledge_base_id not in accessible_kb_ids:
                return Comment.objects.none()
        except KnowledgeNode.DoesNotExist:
            return Comment.objects.none()

        # 场景1：查询根评论（分页）
        if self.request.query_params.get("type") == "root":
            return Comment.objects.filter(
                article_id=article_id,
                type=CommentType.ROOT
            ).order_by("-hot", "-comment_date")  # 优先热评，再按时间倒序

        # 场景2：按需加载子评论（根据根评论ID）
        root_id = self.request.query_params.get("root_id")

        # SQL注入防护：校验根评论ID格式
        if root_id and not validate_uuid(root_id):
            return Comment.objects.none()

        if root_id:
            return Comment.objects.filter(
                article_id=article_id,
                type=CommentType.ANSWER,
                root_id=root_id
            ).order_by("comment_date")  # 子评论按时间正序

        # 场景3：默认查询所有（用于管理后台）
        return Comment.objects.filter(article_id=article_id)

    # 修复创建评论时的序列化器引用
    def create(self, request, *args, **kwargs):
        try:
            # 校验文章所属知识库权限
            article_id = request.data.get("article_id")

            # SQL注入防护：校验文章ID格式
            if not article_id or not validate_uuid(article_id):
                return Response(
                    {"code": 400, "msg": "文章ID（article_id）不能为空且格式必须为UUID"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            article = KnowledgeNode.objects.get(id=article_id)
            require_view_permission(request.user, article.knowledge_base.id)

            # SQL注入防护：清理评论内容
            sanitized_data = request.data.copy()
            if 'comment_text' in sanitized_data:
                sanitized_data['comment_text'] = sanitize_input(sanitized_data['comment_text'])

            # 使用get_serializer()获取正确的序列化器
            serializer = self.get_serializer(data=sanitized_data)
            serializer.is_valid(raise_exception=True)

            # 补充当前登录用户为评论者
            serializer.validated_data["commented_by"] = request.user

            # 保存评论
            comment = serializer.save()

            # 回复评论：创建通知
            if comment.type == CommentType.ANSWER:
                content = f"{request.user.username}回复了你的评论：{sanitize_input(comment.comment_text[:20])}..."
                CommentNotification.objects.create(
                    notified_user=comment.to_user,  # to_user
                    reply_comment=comment,
                    content=content
                )

            # 修复：返回时使用正确的序列化器
            return Response(
                self.get_serializer(comment).data,
                status=status.HTTP_201_CREATED
            )
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeNode.DoesNotExist:
            return Response(
                {"detail": "文章不存在"},
                status=status.HTTP_404_NOT_FOUND
            )


# ===================== 通知视图（查看/标记已读） =====================
class CommentNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """评论通知视图：查看未读通知、标记已读"""
    serializer_class = CommentNotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """仅返回当前用户的通知"""
        return CommentNotification.objects.filter(
            notified_user=self.request.user
        ).order_by("-created_at")

    def partial_update(self, request, *args, **kwargs):
        """标记通知为已读"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "已读"})


# ========== 5. 节点标签视图集 ==========
class NodeTagViewSet(viewsets.ModelViewSet):
    """节点标签视图集（补充权限控制）"""
    serializer_class = NodeTagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return NodeTag.objects.none()
        # 只能看到自己创建的标签, 按创建时间倒序
        return NodeTag.objects.filter(creator=user).order_by("-created_at")

    # 创建标签时自动绑定创建者
    def perform_create(self, serializer):
        """创建标签：清理标签名称防止SQL注入"""
        if 'name' in serializer.validated_data:
            serializer.validated_data['name'] = sanitize_input(serializer.validated_data['name'])
        serializer.save(creator=self.request.user)


# ========== 6. 节点编辑历史视图集 ==========
class NodeHistoryViewSet(viewsets.ModelViewSet):
    """节点编辑历史视图集（补充权限控制）"""
    serializer_class = NodeHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return NodeHistory.objects.none()

        # 获取用户已关注的公开知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        # 只能看到有权限的知识库/公开且已关注知识库 下的节点编辑历史
        return NodeHistory.objects.filter(
            node__knowledge_base__in=KnowledgeBase.objects.filter(
                Q(creator=user) | Q(shares__shared_to=user) | Q(id__in=followed_public_kb_ids)
            )
        ).order_by("-edited_at")


# ========== 7. 按知识库筛选节点视图集 ==========
class KnowledgeNodeByKBViewSet(viewsets.ModelViewSet):
    """
    知识库节点专属视图集（按知识库ID筛选+完整CRUD）
    接口路径：/api/v1/knowledge/nodes/
    类型：私有节点（自己创建/被共享）+ 公开节点（已关注的公开知识库）
    支持：GET(列表/详情)、POST(新增)、PUT/PATCH(编辑)、DELETE(删除)
    """
    serializer_class = KnowledgeNodeListSerializer
    pagination_class = KnowledgeNodeListPagination
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "delete", "patch"]
    lookup_field = "id"

    # ========== 新增：封装公开知识库ID获取逻辑（核心补充） ==========
    def _get_public_knowledge_base_ids(self, user, only_followed=False):
        """
        获取公开知识库ID列表（可复用，支持两种场景）
        :param user: 当前登录用户
        :param only_followed: 是否仅返回已关注的公开知识库， 返回全部的公开知识库（默认False，和原有逻辑一致）
        :return: 公开知识库ID列表（UUID格式）
        """
        if only_followed:
            # 场景1：仅返回用户已关注的公开知识库ID（和你原有逻辑一致，推荐）
            followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
                user=user,
                is_active=True,  # 仅有效关注（未取消）
                knowledge_base__is_public=True  # 跨表查询：关注的知识库是公开的
            ).values_list("knowledge_base_id", flat=True)
            return list(followed_public_kb_ids)
        else:
            # 场景2：返回所有公开知识库ID（谨慎使用，需业务评估）
            # 这才是我要的，上面的，如果服务器压力大就需要上面的关注返回，正常逻辑是全部公开知识库都可以访问
            all_public_kb_ids = KnowledgeBase.objects.filter(
                is_public=True
            ).values_list("id", flat=True)
            return list(all_public_kb_ids)

    # 核心修复：重写get_object，应用公开知识库权限（保持你原有逻辑）
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        node_id = self.kwargs[lookup_url_kwarg]

        # SQL注入防护：校验UUID格式
        if not validate_uuid(node_id):
            # 无效的节点ID格式
            raise Http404("Invalid node ID format.")

        try:
            obj = queryset.get(id=node_id)
        except KnowledgeNode.DoesNotExist:
            # 节点不存在或你无访问权限
            raise Http404("No KnowledgeNode matches the given query.")

        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        """
        核心查询逻辑：
        1. 仅返回MD文件类型节点
        2. 按知识库ID筛选（查询参数knowledge_base_id）
        3. 权限控制：仅返回用户有权限的知识库下的节点
            1. 私有范围：自己创建的知识库节点 + 被共享的知识库节点
            2. 公开范围：已关注的公开知识库节点
        """
        user = self.request.user
        if not user.is_authenticated:
            return KnowledgeNode.objects.none()

        # ========== 优化：调用封装的函数获取公开知识库ID（替代原有硬编码逻辑） ==========
        # only_followed=False : 获取公开知识库
        followed_public_kb_ids = self._get_public_knowledge_base_ids(user, only_followed=False)

        # 基础筛选：仅MD文件 + 自己创建/被共享/公开知识库 | 公开且已关注知识库（保守的原有逻辑only_followed=Ture）
        base_qs = KnowledgeNode.objects.filter(
            node_type=KnowledgeNode.NodeType.MARKDOWN,
            knowledge_base__in=KnowledgeBase.objects.filter(
                Q(creator=user) | Q(shares__shared_to=user) | Q(id__in=followed_public_kb_ids)
            )
        ).order_by("sort_order", "-created_at")

        # 获取并校验知识库ID查询参数
        kb_id = self.request.query_params.get("knowledge_base_id")
        if kb_id:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(kb_id):
                # UUID格式错误时返回空列表
                return KnowledgeNode.objects.none()
            try:
                kb_uuid = uuid.UUID(kb_id)
                # 追加筛选：指定知识库下的节点
                base_qs = base_qs.filter(knowledge_base_id=kb_uuid)
            except ValueError:
                # UUID格式错误时返回空列表
                return KnowledgeNode.objects.none()

        return base_qs

    def list(self, request, *args, **kwargs):
        """
        重写列表查询：强化参数校验 + 统一返回格式（原有逻辑不变）
        """
        # 1. 校验knowledge_base_id必填（列表查询时）
        kb_id = request.query_params.get("knowledge_base_id")
        if not kb_id:
            return Response(
                {"knowledge_base_id": ["该字段是必填项，请传入知识库UUID。"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 校验UUID格式（已通过validate_uuid函数强化）
        if not validate_uuid(kb_id):
            return Response(
                {"knowledge_base_id": ["无效的UUID格式，请传入正确的知识库ID。"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. 校验知识库存在 + 查看权限
        try:
            # 调用require_view_permission校验查看权限（会抛PermissionDenied）
            require_view_permission(request.user, kb_id)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "指定的知识库不存在。"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. 执行父类列表逻辑（含分页+序列化）
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        新增节点：
        1. 调用permission.py中的require_edit_permission校验编辑权限
        2. 强制绑定到指定知识库
        3. 确保节点类型为MD文件（原有逻辑不变）
        """
        # 1. 获取并校验知识库ID
        kb_id = request.data.get("knowledge_base") or request.query_params.get("knowledge_base_id")

        # SQL注入防护：校验UUID格式
        if not kb_id or not validate_uuid(kb_id):
            return Response(
                {"knowledge_base": ["新增节点必须指定所属知识库ID且格式为UUID。"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 校验知识库存在 + 编辑权限（核心：调用permission.py的函数）
        try:
            # 转换为UUID（兼容字符串ID）
            kb_uuid = uuid.UUID(kb_id)
            # 调用require_edit_permission，失败会抛PermissionDenied
            require_edit_permission(request.user, kb_uuid)
            # 校验知识库存在
            knowledge_base = KnowledgeBase.objects.get(id=kb_uuid)
        except ValueError:
            return Response(
                {"knowledge_base": ["无效的UUID格式，请传入正确的知识库ID。"]},
                status=status.HTTP_400_BAD_REQUEST
            )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"knowledge_base": ["指定的知识库不存在。"]},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. 强制设置节点类型为MD文件（该接口仅处理文章）
        request.data["node_type"] = KnowledgeNode.NodeType.MARKDOWN
        # 4. 绑定创建者为当前用户
        request.data["creator"] = request.user.id
        # 5. 强制绑定到指定知识库
        request.data["knowledge_base"] = kb_uuid

        # 6. SQL注入防护：清理输入数据
        sanitized_data = request.data.copy()
        if 'name' in sanitized_data:
            sanitized_data['name'] = sanitize_input(sanitized_data['name'])
        if 'content' in sanitized_data:
            sanitized_data['content'] = sanitize_input(sanitized_data['content'])
        if 'description' in sanitized_data:
            sanitized_data['description'] = sanitize_input(sanitized_data['description'])

        # 7. 执行创建逻辑
        serializer = self.get_serializer(data=sanitized_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def update(self, request, *args, **kwargs):
        """
        编辑节点：
        1. 调用permission.py中的require_edit_permission校验编辑权限
        2. 禁止修改节点类型（确保始终为MD文件）（原有逻辑不变）
        """
        partial = kwargs.pop('partial', False)

        # SQL注入防护：清理输入数据
        sanitized_data = request.data.copy()
        if 'name' in sanitized_data:
            sanitized_data['name'] = sanitize_input(sanitized_data['name'])
        if 'content' in sanitized_data:
            sanitized_data['content'] = sanitize_input(sanitized_data['content'])
        if 'description' in sanitized_data:
            sanitized_data['description'] = sanitize_input(sanitized_data['description'])

        try:
            instance = self.get_object()

            # 1. 从节点实例中获取知识库ID，校验编辑权限
            kb_id = instance.knowledge_base.id
            # 调用require_edit_permission，失败会抛PermissionDenied
            require_edit_permission(request.user, kb_id)

            # 2. 禁止修改节点类型（该接口仅处理MD文件）
            if "node_type" in sanitized_data and sanitized_data["node_type"] != KnowledgeNode.NodeType.MARKDOWN:
                return Response(
                    {"node_type": ["该接口仅支持编辑MD文件类型节点，禁止修改节点类型。"]},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 3. 执行更新逻辑
            serializer = self.get_serializer(instance, data=sanitized_data, partial=partial)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            if getattr(instance, '_prefetched_objects_cache', None):
                instance._prefetched_objects_cache = {}

            return Response(serializer.data)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Http404:
            return Response(
                {"detail": "节点不存在或你无访问权限"},
                status=status.HTTP_404_NOT_FOUND
            )

    def destroy(self, request, *args, **kwargs):
        """
        删除节点：调用permission.py中的require_admin_permission校验管理权限（原有逻辑不变）
        """
        try:
            instance = self.get_object()

            # 1. 从节点实例中获取知识库ID，校验管理员权限
            kb_id = instance.knowledge_base.id
            # 调用require_admin_permission，失败会抛PermissionDenied
            require_admin_permission(request.user, kb_id)

            # 2. 额外校验：仅允许删除MD文件
            if instance.node_type != KnowledgeNode.NodeType.MARKDOWN:
                return Response(
                    {"detail": "该接口仅允许删除MD文件类型节点。"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 3. 执行删除逻辑
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PermissionDenied as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Http404:
            return Response(
                {"detail": "节点不存在或你无访问权限"},
                status=status.HTTP_404_NOT_FOUND
            )

    def perform_create(self, serializer):
        """覆盖创建逻辑：绑定创建者（原有逻辑不变）"""
        serializer.save(creator=self.request.user)

    @action(detail=False, methods=["get"])
    def public_knowledge_bases(self, request):
        """
        新增接口：获取公开知识库列表
        路径：/api/v1/knowledge/nodes/public_knowledge_bases/
        - 应该分页的
        """
        user = request.user
        # 调用封装的方法，获取公开知识库ID
        public_kb_ids = self._get_public_knowledge_base_ids(user, only_followed=False)

        # 查询公开知识库详情（按需返回字段）
        public_kbs = KnowledgeBase.objects.filter(
            id__in=public_kb_ids
        ).values("id", "short_id", "name", "description", "creator__username", "created_at")

        return Response({
            "count": len(public_kbs),
            "results": list(public_kbs)
        })

    @action(detail=False, methods=["get"])
    def follow_public_knowledge_bases(self, request):
        """
        新增接口：我关注的公开知识库知识库列表
        路径：/api/v1/knowledge/nodes/follow_public_knowledge_bases/
        """
        user = request.user
        # 调用封装的方法，获取公开知识库ID
        public_kb_ids = self._get_public_knowledge_base_ids(user, only_followed=True)

        # 查询公开知识库详情（按需返回字段）
        public_kbs = KnowledgeBase.objects.filter(
            id__in=public_kb_ids
        ).values("id", "short_id", "name", "description", "creator__username", "created_at")

        return Response({
            "count": len(public_kbs),
            "results": list(public_kbs)
        })

# ========== 8. 分页类 ==========
class SearchPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'


# ========== 9. 全局搜索视图（修复语法错误） ==========
class GlobalSearchAPIView(APIView):
    """全局搜索：支持搜索知识库、节点、标签、评论（带权限过滤）"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        keyword = sanitize_input(request.query_params.get("keyword", "").strip())  # SQL注入防护：清理搜索关键词

        if not keyword:
            return Response(
                {"code": 400, "msg": "请传入搜索关键词（keyword）"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 获取用户可访问的知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        accessible_kb_ids = KnowledgeBase.objects.filter(
            Q(creator=user) | Q(shares__shared_to=user) | Q(id__in=followed_public_kb_ids)
        ).values_list("id", flat=True)

        # 用户搜索逻辑
        user_qs = User.objects.filter(
            Q(username__icontains=keyword) |
            Q(user_id__icontains=keyword) |
            Q(email__icontains=keyword) |
            Q(bio__icontains=keyword)
        ).exclude(
            id=user.id,
            is_private=True
        ).select_related('vip_info')

        user_serializer = UserSearchSerializer(
            user_qs,
            many=True,
            context={'request': request}
        )

        all_results = {
            "users": user_serializer.data,
            "knowledge_bases": KnowledgeBaseSerializer(
                KnowledgeBase.objects.filter(
                    Q(id__in=accessible_kb_ids) &
                    (Q(name__icontains=keyword) | Q(description__icontains=keyword))
                ), many=True
            ).data,
            "nodes": KnowledgeNodeSerializer(
                KnowledgeNode.objects.filter(
                    Q(knowledge_base_id__in=accessible_kb_ids) &
                    (Q(name__icontains=keyword) | Q(content__icontains=keyword) | Q(description__icontains=keyword))
                ),
                many=True
            ).data,
            "tags": NodeTagSerializer(
                NodeTag.objects.filter(Q(creator=user) & Q(name__icontains=keyword)), many=True
            ).data,
            # comment_text__icontains
            "comments": CommentRootSerializer(
                Comment.objects.filter(
                    Q(knowledge_base_id__in=accessible_kb_ids) & Q(comment_text__icontains=keyword)
                ), many=True
            ).data,
        }

        total_count = (
                len(all_results["users"]) +
                len(all_results["knowledge_bases"]) +
                len(all_results["nodes"]) +
                len(all_results["tags"]) +
                len(all_results["comments"])
        )

        paginated_response = {
            "code": 200,
            "msg": "success" if total_count > 0 else f"未找到与「{keyword}」相关的内容",
            "count": total_count,
            "next": None,
            "previous": None,
            "results": all_results
        }
        return Response(paginated_response)
        # http://127.0.0.1:8000/api/v1/search/global?keyword=%E4%B8%8D%E5%BB%BA%E8%AE%AE


# ========== 10. 全局搜索ViewSet ==========
class GlobalSearchViewSet(viewsets.GenericViewSet):
    """
    全局搜索ViewSet（适配前端分页预期，参考wiki项目写法）
    - 接口：GET /api/v1/search/global/
    - 参数：keyword(必传)、page(可选)、page_size(可选)
    """
    queryset = KnowledgeBase.objects.none()
    pagination_class = SearchPagination
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='global')
    def global_search(self, request):
        """
        全局搜索接口（修复UUID序列化问题）
        新增：用户搜索逻辑，支持搜索用户名/用户ID/邮箱/简介，过滤私密用户
        返回格式：{code:200, msg:"success", count:总条数, next:下一页URL, previous:上一页URL, results: 分页数据}
        """
        # 1. 提取参数
        keyword = sanitize_input(request.query_params.get("keyword", "").strip())  # SQL注入防护：清理搜索关键词
        page = request.query_params.get(self.pagination_class.page_query_param, 1)
        page_size = request.query_params.get(self.pagination_class.page_size_query_param,
                                             self.pagination_class.page_size)

        # 2. 参数校验
        if not keyword:
            return Response(
                {"code": 400, "msg": "请传入搜索关键词（keyword）"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. 缓存逻辑
        redis_conn = get_redis_connection("default")
        cache_key = f"knowledge_search:all:{keyword}:page_{page}:size_{page_size}"
        cache_data = redis_conn.get(cache_key)

        # 4. 缓存命中：直接返回
        if cache_data:
            result = json.loads(cache_data)
            return Response(result)

        # 5. 缓存未命中：数据库查询
        user = request.user

        # 获取用户可访问的知识库ID
        followed_public_kb_ids = UserFollowKnowledgeBase.objects.filter(
            user=user,
            is_active=True,
            knowledge_base__is_public=True
        ).values_list("knowledge_base_id", flat=True)

        accessible_kb_ids = KnowledgeBase.objects.filter(
            Q(creator=user) | Q(shares__shared_to=user) | Q(id__in=followed_public_kb_ids)
        ).values_list("id", flat=True)

        # ========== 新增：用户搜索逻辑（返回完整用户数据） ==========
        # 5.0 搜索用户（过滤条件：非私密 + 关键词匹配 + 排除自己）
        user_qs = User.objects.filter(
            # 关键词匹配：用户名/用户ID/邮箱/简介
            Q(username__icontains=keyword) |
            Q(user_id__icontains=keyword) |
            Q(email__icontains=keyword) |
            Q(bio__icontains=keyword)
        ).exclude(
            # 排除自己 + 排除私密用户（私密用户不展示在搜索结果）
            id=user.id,
            is_private=True
        ).select_related('vip_info')  # 关联查询会员信息，减少数据库查询

        # 序列化用户数据（传递request上下文，返回全部字段）
        user_serializer = UserSearchSerializer(
            user_qs,
            many=True,
            context={'request': request}  # 必须传递request，否则is_followed字段无法计算
        )
        # ========== 用户搜索逻辑结束 ==========

        # 5.1 组装所有搜索结果（新增users字段，包含完整用户数据）
        all_results = {
            "users": user_serializer.data,  # 新增用户搜索结果 即使为空也返回空列表
            "knowledge_bases": KnowledgeBaseSerializer(
                KnowledgeBase.objects.filter(
                    Q(id__in=accessible_kb_ids) &
                    (Q(name__icontains=keyword) | Q(description__icontains=keyword))
                ), many=True
            ).data,
            "nodes": KnowledgeNodeSerializer(
                KnowledgeNode.objects.filter(
                    Q(knowledge_base_id__in=accessible_kb_ids) &
                    (Q(name__icontains=keyword) | Q(content__icontains=keyword) | Q(description__icontains=keyword))
                ),
                many=True
            ).data,
            "tags": NodeTagSerializer(
                NodeTag.objects.filter(Q(creator=user) & Q(name__icontains=keyword)), many=True
            ).data,
            # comment_text__icontains + 指定正确序列化器
            "comments": CommentRootSerializer(
                Comment.objects.filter(
                    Q(knowledge_base_id__in=accessible_kb_ids) & Q(comment_text__icontains=keyword)
                ), many=True
            ).data,
        }

        # 5.2 计算总条数（包含用户）
        total_count = (
                len(all_results["users"]) +  # 新增用户数量
                len(all_results["knowledge_bases"]) +
                len(all_results["nodes"]) +
                len(all_results["tags"]) +
                len(all_results["comments"])
        )

        # 6. 分页处理（逻辑不变，自动包含用户数据）
        paginated_response = {
            "code": 200,
            "msg": "success" if total_count > 0 else f"未找到与「{keyword}」相关的内容",
            "count": total_count,
            "next": None,
            "previous": None,
            "results": all_results
        }

        # 7. 缓存结果（关键修改：指定自定义UUIDEncoder）
        redis_conn.setex(
            cache_key,
            600,
            json.dumps(paginated_response, cls=UUIDEncoder)  # 使用自定义编码器处理UUID
        )

        # 8. 返回响应
        return Response(paginated_response)

# ===================== 文章评论视图集 =====================
class NodeCommentViewSet(viewsets.ModelViewSet):
    """
    文章评论核心视图集（支持路径参数/查询参数两种方式）：
    - 路径参数：/api/v1/knowledge-nodes/{article_id}/comments/（推荐）
    - 查询参数：/api/v1/node-comments/?article_id=xxx（兼容原有方式）
    - 强制校验文章存在，否则返回404
    - 支持根评论/回复评论筛选、热评查询
    """
    permission_classes = [NodeCommentPermission]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["comment_date", "hot"]
    ordering = ["-hot", "-comment_date"]

    def get_serializer_class(self):
        """动态选择序列化器"""
        if self.action in ["create", "update", "partial_update"]:
            return NodeCommentCreateSerializer  # 创建/更新用专用序列化器
        # 列表/详情：按类型选择根评论/回复评论序列化器
        type_param = self.request.query_params.get("type", CommentTypeChoices.ROOT)
        return NodeCommentAnswerSerializer if type_param == CommentTypeChoices.ANSWER else NodeCommentRootSerializer

    def get_article_id(self):
        """
        优先从路径参数获取文章ID，其次从查询参数获取
        适配嵌套路由的参数名：article_pk（drf-nested-routers）/ article_id（手动配置）
        """
        # 1. 适配 drf-nested-routers 的参数名（lookup="article" → article_pk）
        article_id = self.kwargs.get("article_pk")
        # 2. 适配手动配置的参数名
        if not article_id:
            article_id = self.kwargs.get("article_id") or self.kwargs.get("pk")
        # 3. 最后从查询参数获取（兼容原有方式）
        if not article_id:
            article_id = self.request.query_params.get("article_id")

        # SQL注入防护：校验文章ID格式（UUID）
        if article_id and not validate_uuid(article_id):
            return None
        return article_id

    def get_queryset(self):
        """
        仅返回指定文章的评论，禁止无筛选查询：
        1. 优先从路径参数取article_id，其次从查询参数取
        2. 校验文章存在，否则返回空
        """
        article_id = self.get_article_id()
        if not article_id:
            return NodeComment.objects.none()

        # 校验文章存在（核心：确保article_id对应有效的文章）
        try:
            article = get_object_or_404(KnowledgeNode, id=article_id)
            # 校验用户是否有权限访问该文章
            require_view_permission(self.request.user, article.knowledge_base.id)
        except (Http404, PermissionDenied):
            return NodeComment.objects.none()

        # 基础筛选：指定文章的评论
        queryset = NodeComment.objects.filter(article_id=article_id)

        # 可选筛选：根评论ID（回复列表）- SQL注入防护：校验UUID格式
        root_id = self.request.query_params.get("root_id")
        if root_id:
            if not validate_uuid(root_id):
                return NodeComment.objects.none()
            queryset = queryset.filter(root_id=root_id)

        # 可选筛选：评论类型
        type_param = self.request.query_params.get("type")
        if type_param in [CommentTypeChoices.ROOT, CommentTypeChoices.ANSWER]:
            queryset = queryset.filter(type=type_param)

        return queryset

    def list(self, request, *args, **kwargs):
        """重写列表接口：强制校验文章ID存在"""
        article_id = self.get_article_id()
        if not article_id:
            return Response(
                {"error": "必须通过路径参数(article_id)或查询参数(article_id)指定文章ID，且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )
        # 校验文章存在（避免返回空列表但实际是文章不存在）
        try:
            article = get_object_or_404(KnowledgeNode, id=article_id)
            require_view_permission(request.user, article.knowledge_base.id)
        except Http404:
            return Response(
                {"error": f"文章ID {article_id} 不存在"},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        """创建评论：自动生成通知（仅回复评论）+ SQL注入防护：清理评论内容"""
        # 清理评论内容，防止SQL注入
        if 'comment_text' in serializer.validated_data:
            serializer.validated_data['comment_text'] = sanitize_input(serializer.validated_data['comment_text'])
        comment = serializer.save()  # serializer已处理文章/用户绑定

        # 回复评论：创建通知
        if comment.type == CommentTypeChoices.ANSWER:
            from .models import NodeCommentNotification  # 避免循环导入
            NodeCommentNotification.objects.create(
                notified_user=comment.to_user,
                reply_comment=comment,
                content=f"{self.request.user.username}回复了你的评论：{sanitize_input(comment.comment_text[:20])}..."
            )

    @action(detail=False, methods=["get"])
    def hot_comments(self, request, *args, **kwargs):
        """
        热评接口：返回指定文章的前10条根评论（支持路径/查询参数）
        - 路径参数：/api/v1/knowledge-nodes/{article_id}/comments/hot_comments/
        - 查询参数：/api/v1/node-comments/hot_comments/?article_id=xxx
        """
        article_id = self.get_article_id()
        if not article_id:
            return Response(
                {"error": "必须通过路径参数(article_id)或查询参数(article_id)指定文章ID，且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )
        # 校验文章存在
        try:
            article = get_object_or_404(KnowledgeNode, id=article_id)
            require_view_permission(request.user, article.knowledge_base.id)
        except Http404 as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )

        # 查询热评根评论
        hot_comments = NodeComment.objects.filter(
            article_id=article_id,
            type=CommentTypeChoices.ROOT
        ).order_by("-hot", "-comment_date")[:10]

        serializer = NodeCommentRootSerializer(hot_comments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="root-comment/(?P<root_comment_pk>[^/.]+)/answers")
    def root_comment_answers(self, request, *args, **kwargs):
        """
        指定根评论的回复列表接口（核心API）：
        URL: /api/v1/node-comments/root-comment/{root_comment_pk}/answers/
        或嵌套路由：/api/v1/knowledge-nodes/{article_id}/comments/root-comment/{root_comment_pk}/answers/
        参数：
          - article_id：文章ID（路径/查询参数均可）
          - page：页码（可选，默认1）
          - page_size：每页条数（可选，默认5）
        返回：分页的回复评论列表（仅该根评论下的回复）
        """
        # 1. 获取并校验核心参数
        article_id = self.get_article_id()
        root_comment_pk = kwargs.get("root_comment_pk")

        # 校验文章ID
        if not article_id:
            return Response(
                {"error": "必须通过路径参数(article_id)或查询参数(article_id)指定文章ID，且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 校验根评论ID - SQL注入防护：校验UUID格式
        if not root_comment_pk or not validate_uuid(root_comment_pk):
            return Response(
                {"error": "必须指定根评论ID（root_comment_pk），且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 校验文章和根评论存在
        try:
            # 校验文章存在
            article = get_object_or_404(KnowledgeNode, id=article_id)
            require_view_permission(request.user, article.knowledge_base.id)
            # 校验根评论存在且属于该文章、类型为ROOT
            root_comment = get_object_or_404(
                NodeComment,
                id=root_comment_pk,
                article=article,
                type=CommentTypeChoices.ROOT
            )
        except Http404 as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. 筛选该根评论下的回复评论
        queryset = NodeComment.objects.filter(
            article=article,
            root_id=root_comment_pk,
            type=CommentTypeChoices.ANSWER
        ).order_by("comment_date")  # 回复按时间正序展示

        # 4. 分页处理
        paginator = NodeCommentAnswerPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # 5. 序列化返回
        serializer = NodeCommentAnswerSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=["post"], url_path="root-comment/(?P<root_comment_pk>[^/.]+)/answers")
    def create_root_comment_answer(self, request, *args, **kwargs):
        """
        创建指定根评论的回复接口：
        URL: /api/v1/node-comments/root-comment/{root_comment_pk}/answers/
        或嵌套路由：/api/v1/knowledge-nodes/{article_id}/comments/root-comment/{root_comment_pk}/answers/
        请求体：
          - comment_text：回复内容（必填）
          - to_user_id：被回复用户ID（必填，根评论作者ID）
        """
        # 1. 获取并校验核心参数
        article_id = self.get_article_id()
        root_comment_pk = kwargs.get("root_comment_pk")

        # 基础参数校验
        if not article_id:
            return Response(
                {"error": "必须通过路径参数(article_id)或查询参数(article_id)指定文章ID，且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )
        # 校验根评论ID - SQL注入防护：校验UUID格式
        if not root_comment_pk or not validate_uuid(root_comment_pk):
            return Response(
                {"error": "必须指定根评论ID（root_comment_pk），且格式必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 校验被回复用户ID - SQL注入防护：校验UUID/数字格式
        to_user_id = request.data.get("to_user_id")
        if not to_user_id or not (validate_uuid(to_user_id) or validate_numeric_id(to_user_id)):
            return Response(
                {"error": "必须指定被回复用户ID（to_user_id），且格式必须为UUID或数字"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 清理评论内容 - SQL注入防护：移除危险字符
        comment_text = request.data.get("comment_text", "")
        if not comment_text:
            return Response(
                {"error": "回复内容（comment_text）不能为空"},
                status=status.HTTP_400_BAD_REQUEST
            )
        sanitized_comment_text = sanitize_input(comment_text)
        if not sanitized_comment_text:
            return Response(
                {"error": "回复内容包含非法字符，请修改后重试"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 校验文章和根评论存在
        try:
            article = get_object_or_404(KnowledgeNode, id=article_id)
            require_view_permission(request.user, article.knowledge_base.id)
            root_comment = get_object_or_404(
                NodeComment,
                id=root_comment_pk,
                article=article,
                type=CommentTypeChoices.ROOT
            )
        except Http404 as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. 构造创建回复的参数
        create_data = request.data.copy()
        # 自动填充必选字段（避免前端传错）
        create_data["article"] = article.id
        create_data["root_id"] = root_comment_pk
        create_data["type"] = CommentTypeChoices.ANSWER
        create_data["commented_by"] = request.user.id  # 绑定当前登录用户
        # 替换为清理后的评论内容
        create_data["comment_text"] = sanitized_comment_text

        # 4. 序列化并创建回复
        serializer = NodeCommentCreateSerializer(data=create_data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()

        # 5. 创建回复通知（清理通知内容）
        NodeCommentNotification.objects.create(
            notified_user=comment.to_user,
            reply_comment=comment,
            content=f"{request.user.username}回复了你的评论：{sanitized_comment_text[:20]}..."
        )

        # 6. 返回序列化结果
        return Response(
            NodeCommentAnswerSerializer(comment).data,
            status=status.HTTP_201_CREATED
        )


# ===================== 文章评论通知视图集 =====================
class NodeCommentNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """文章评论通知视图集：仅返回当前用户的通知"""
    serializer_class = NodeCommentNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """仅返回当前用户的通知，支持筛选未读"""
        queryset = NodeCommentNotification.objects.filter(notified_user=self.request.user)

        # SQL注入防护：校验筛选参数格式（仅允许布尔值）
        unread_param = self.request.query_params.get("unread")
        if unread_param:
            if unread_param.lower() not in ["true", "false"]:
                return NodeCommentNotification.objects.none()
            queryset = queryset.filter(is_read=False)

        return queryset.order_by("-created_at")

    @action(detail=True, methods=["patch"])
    def mark_read(self, request, pk=None):
        """标记单条通知为已读 + SQL注入防护：校验UUID格式"""
        # 校验通知ID格式
        if not pk or not validate_uuid(pk):
            return Response(
                {"error": "通知ID格式错误，必须为UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        notification = self.get_object()
        notification.is_read = True
        # 修复：update_fields应为is_read（原代码错误写为is_active）
        notification.save(update_fields=["is_read"])
        return Response({"status": "通知已标记为已读"})

    @action(detail=False, methods=["patch"])
    def mark_all_read(self, request):
        """标记当前用户所有未读通知为已读"""
        NodeCommentNotification.objects.filter(
            notified_user=request.user, is_read=False
        ).update(is_read=True)
        return Response({"status": "所有未读通知已标记为已读"})


class UserPublicKnowledgeBasesViewSet(GenericViewSet, ListModelMixin):
    """
    获取指定用户的所有公开知识库（适配DRF DefaultRouter）
    支持两种参数：
    - id: 用户UUID主键（如：/api/v1/knowledge/user-public-kbs/?id=xxx-xxx-xxx）
    - user_id: 用户自定义ID（如：/api/v1/knowledge/user-public-kbs/?user_id=123456）
    """
    serializer_class = KnowledgeBaseMiniSerializer
    # 基础查询集（实际会在list方法中重写过滤逻辑）
    queryset = KnowledgeBase.objects.filter(is_public=True).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        # 获取请求参数（逻辑与原APIView完全一致）
        user_id_param = request.query_params.get("user_id")
        id_param = request.query_params.get("id")

        # 参数校验：必须提供id或user_id
        if not user_id_param and not id_param:
            return Response(
                {"error": "必须提供id（用户UUID）或user_id（用户自定义ID）参数"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 查询用户
        try:
            if id_param:
                # 通过UUID主键查询用户
                user = get_object_or_404(User, id=id_param)
            else:
                # 通过自定义user_id查询用户（需确保User模型有user_id字段）
                user = get_object_or_404(User, user_id=user_id_param)
        except Exception as e:
            return Response(
                {"error": f"用户不存在：{str(e)}"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 查询该用户的所有公开知识库
        public_kbs = self.queryset.filter(creator=user)
        serializer = self.get_serializer(public_kbs, many=True)

        return Response({
            "count": public_kbs.count(),
            "results": serializer.data
        }, status=status.HTTP_200_OK)


class PublicKnowledgeNodeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    公开知识库节点查询视图集（仅查询）
    接口路径：/api/v1/knowledge/public-nodes/
    核心逻辑：仅查询is_public=True的知识库下的MD节点，登录用户无需关注即可访问
    支持：GET(列表/详情)
    """
    serializer_class = KnowledgeNodeListSerializer
    pagination_class = KnowledgeNodeListPagination
    permission_classes = [IsAuthenticated]  # 仅登录用户可访问
    http_method_names = ["get"]  # 仅开放查询接口，禁用新增/编辑/删除
    lookup_field = "id"

    # 重写get_object：仅返回公开知识库下的节点
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        node_id = self.kwargs[lookup_url_kwarg]

        # SQL注入防护：校验UUID格式
        if not validate_uuid(node_id):
            raise Http404("Invalid node ID format.")

        try:
            obj = queryset.get(id=node_id)
        except KnowledgeNode.DoesNotExist:
            raise Http404("No public KnowledgeNode matches the given query.")

        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        """
        核心查询逻辑：
        1. 仅返回MD文件类型节点
        2. 仅返回is_public=True的公开知识库下的节点
        3. 按知识库ID筛选（查询参数knowledge_base_id）
        """
        user = self.request.user
        if not user.is_authenticated:
            return KnowledgeNode.objects.none()

        # 基础筛选：仅MD文件 + 公开知识库
        base_qs = KnowledgeNode.objects.filter(
            node_type=KnowledgeNode.NodeType.MARKDOWN,
            knowledge_base__is_public=True  # 核心：仅公开知识库
        ).order_by("sort_order", "-created_at")

        # 获取并校验知识库ID查询参数
        kb_id = self.request.query_params.get("knowledge_base_id")
        if kb_id:
            # SQL注入防护：校验UUID格式
            if not validate_uuid(kb_id):
                return KnowledgeNode.objects.none()
            try:
                kb_uuid = uuid.UUID(kb_id)
                # 追加筛选：指定公开知识库下的节点
                base_qs = base_qs.filter(knowledge_base_id=kb_uuid)
            except ValueError:
                return KnowledgeNode.objects.none()

        return base_qs

    def list(self, request, *args, **kwargs):
        """
        重写列表查询：强化参数校验 + 校验知识库是否为公开
        """
        # 1. 校验knowledge_base_id必填
        kb_id = request.query_params.get("knowledge_base_id")
        if not kb_id:
            return Response(
                {"knowledge_base_id": ["该字段是必填项，请传入公开知识库UUID。"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 校验UUID格式
        if not validate_uuid(kb_id):
            return Response(
                {"knowledge_base_id": ["无效的UUID格式，请传入正确的公开知识库ID。"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. 校验知识库存在且为公开
        try:
            knowledge_base = KnowledgeBase.objects.get(id=kb_id)
            if not knowledge_base.is_public:
                return Response(
                    {"detail": "该知识库非公开，无法访问其节点。"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except KnowledgeBase.DoesNotExist:
            return Response(
                {"detail": "指定的公开知识库不存在。"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. 执行父类列表逻辑（含分页+序列化）
        return super().list(request, *args, **kwargs)
