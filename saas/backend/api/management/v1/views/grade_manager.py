# -*- coding: utf-8 -*-
"""
TencentBlueKing is pleased to support the open source community by making 蓝鲸智云-权限中心(BlueKing-IAM) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from backend.api.authentication import ESBAuthentication
from backend.api.management.constants import ManagementAPIEnum, VerifyAPIParamLocationEnum
from backend.api.management.mixins import ManagementAPIPermissionCheckMixin
from backend.api.management.v1.permissions import ManagementAPIPermission
from backend.api.management.v1.serializers import (
    ManagementGradeManagerBasicInfoSLZ,
    ManagementGradeManagerCreateSLZ,
    ManagementGradeManagerMembersDeleteSLZ,
    ManagementGradeManagerMembersSLZ,
    ManagementGradeManagerUpdateSLZ,
    ManagementSourceSystemSLZ,
)
from backend.apps.role.audit import (
    RoleCreateAuditProvider,
    RoleMemberCreateAuditProvider,
    RoleMemberDeleteAuditProvider,
    RoleUpdateAuditProvider,
)
from backend.apps.role.models import Role, RoleSource, RoleUser
from backend.apps.role.serializers import RoleIdSLZ
from backend.audit.audit import audit_context_setter, view_audit_decorator
from backend.biz.role import RoleBiz, RoleCheckBiz
from backend.common.pagination import CustomPageNumberPagination
from backend.service.constants import RoleSourceTypeEnum, RoleType
from backend.trans.open_management import GradeManagerTrans


class ManagementGradeManagerViewSet(ManagementAPIPermissionCheckMixin, GenericViewSet):
    """分级管理员"""

    authentication_classes = [ESBAuthentication]
    permission_classes = [ManagementAPIPermission]
    management_api_permission = {
        "create": (VerifyAPIParamLocationEnum.SYSTEM_IN_BODY.value, ManagementAPIEnum.GRADE_MANAGER_CREATE.value),
        "update": (VerifyAPIParamLocationEnum.ROLE_IN_PATH.value, ManagementAPIEnum.GRADE_MANAGER_UPDATE.value),
        "list": (VerifyAPIParamLocationEnum.SYSTEM_IN_QUERY.value, ManagementAPIEnum.GRADE_MANAGER_LIST.value),
    }

    lookup_field = "id"
    queryset = Role.objects.filter(type=RoleType.RATING_MANAGER.value).order_by("-updated_time")
    pagination_class = CustomPageNumberPagination

    biz = RoleBiz()
    role_check_biz = RoleCheckBiz()
    trans = GradeManagerTrans()

    @swagger_auto_schema(
        operation_description="创建分级管理员",
        request_body=ManagementGradeManagerCreateSLZ(label="创建分级管理员"),
        responses={status.HTTP_201_CREATED: RoleIdSLZ(label="分级管理员ID")},
        tags=["management.role"],
    )
    @view_audit_decorator(RoleCreateAuditProvider)
    def create(self, request, *args, **kwargs):
        """
        创建分级管理员
        """
        serializer = ManagementGradeManagerCreateSLZ(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # API里数据鉴权: 不可超过接入系统可管控的授权系统范围
        source_system_id = data["system"]
        auth_system_ids = list({i["system"] for i in data["authorization_scopes"]})
        self.verify_system_scope(source_system_id, auth_system_ids)

        # 名称唯一性检查
        self.role_check_biz.check_unique_name(data["name"])
        # 检查该系统可创建的分级管理员数量是否超限
        self.role_check_biz.check_grade_manager_of_system_limit(source_system_id)

        # 转换为RoleInfoBean，用于创建时使用
        role_info = self.trans.to_role_info(data)

        with transaction.atomic():
            # 创建角色
            role = self.biz.create(role_info, request.user.username)

            # 记录role创建来源信息
            RoleSource.objects.create(
                role_id=role.id, source_type=RoleSourceTypeEnum.API.value, source_system_id=source_system_id
            )

        # 审计
        audit_context_setter(role=role)

        return Response({"id": role.id})

    @swagger_auto_schema(
        operation_description="更新分级管理员",
        request_body=ManagementGradeManagerUpdateSLZ(label="更新分级管理员"),
        responses={status.HTTP_200_OK: serializers.Serializer()},
        tags=["management.role"],
    )
    @view_audit_decorator(RoleUpdateAuditProvider)
    def update(self, request, *args, **kwargs):
        """
        更新分级管理员
        Note: 这里可授权范围和可授权人员范围均是全覆盖的，只对body里传入的字段进行更新
        """
        role = self.get_object()

        serializer = ManagementGradeManagerUpdateSLZ(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 数据校验
        if "name" in data:
            # 名称唯一性检查
            self.role_check_biz.check_unique_name(data["name"], role.name)

        if "authorization_scopes" in data:
            # API里数据鉴权: 不可超过接入系统可管控的授权系统范围
            role_source = RoleSource.objects.get(source_type=RoleSourceTypeEnum.API.value, role_id=role.id)
            auth_system_ids = list({i["system"] for i in data["authorization_scopes"]})
            self.verify_system_scope(role_source.source_system_id, auth_system_ids)

        # 转换为RoleInfoBean
        role_info = self.trans.to_role_info_for_update(data)

        # 更新
        self.biz.update(role, role_info, request.user.username)

        # 审计
        audit_context_setter(role=role)

        return Response({})

    @swagger_auto_schema(
        operation_description="分级管理员列表",
        query_serializer=ManagementSourceSystemSLZ(),
        responses={status.HTTP_200_OK: ManagementGradeManagerBasicInfoSLZ(many=True)},
        tags=["management.role.member"],
    )
    def list(self, request, *args, **kwargs):
        serializer = ManagementSourceSystemSLZ(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 分页参数
        limit, offset = CustomPageNumberPagination().get_limit_offset_pair(request)

        count, roles = self.biz.list_paging_role_for_system(data["system"], limit, offset)
        results = ManagementGradeManagerBasicInfoSLZ(roles, many=True).data
        return Response({"count": count, "results": results})


class ManagementGradeManagerMemberViewSet(GenericViewSet):
    """分级管理员成员"""

    pagination_class = None  # 去掉swagger中的limit offset参数

    authentication_classes = [ESBAuthentication]
    permission_classes = [ManagementAPIPermission]
    management_api_permission = {
        "create": (VerifyAPIParamLocationEnum.ROLE_IN_PATH.value, ManagementAPIEnum.GRADE_MANAGER_MEMBER_ADD.value),
        "list": (VerifyAPIParamLocationEnum.ROLE_IN_PATH.value, ManagementAPIEnum.GRADE_MANAGER_MEMBER_LIST.value),
        "destroy": (
            VerifyAPIParamLocationEnum.ROLE_IN_PATH.value,
            ManagementAPIEnum.GRADE_MANAGER_MEMBER_DELETE.value,
        ),
    }

    lookup_field = "id"
    queryset = Role.objects.filter(type=RoleType.RATING_MANAGER.value).order_by("-updated_time")

    biz = RoleBiz()
    role_check_biz = RoleCheckBiz()

    @swagger_auto_schema(
        operation_description="分级管理员成员列表",
        responses={status.HTTP_200_OK: serializers.ListSerializer(child=serializers.CharField(label="成员"))},
        tags=["management.role.member"],
    )
    def list(self, request, *args, **kwargs):
        role = self.get_object()
        # 成员
        return Response(role.members)

    @swagger_auto_schema(
        operation_description="批量添加分级管理员成员",
        request_body=ManagementGradeManagerMembersSLZ(label="分级管理员成员"),
        responses={status.HTTP_200_OK: serializers.Serializer()},
        tags=["management.role.member"],
    )
    @view_audit_decorator(RoleMemberCreateAuditProvider)
    def create(self, request, *args, **kwargs):
        role = self.get_object()

        serializer = ManagementGradeManagerMembersSLZ(data=request.data)
        serializer.is_valid(raise_exception=True)

        members = list(set(serializer.validated_data["members"]))
        # 检查成员数量是否满足限制
        self.role_check_biz.check_member_count(role.id, len(members))

        # 批量添加成员(添加时去重)
        self.biz.add_grade_manager_members(role.id, members)

        # 审计
        audit_context_setter(role=role, members=members)

        return Response({})

    @swagger_auto_schema(
        operation_description="批量删除分级管理员成员",
        query_serializer=ManagementGradeManagerMembersDeleteSLZ(label="分级管理员成员"),
        responses={status.HTTP_200_OK: serializers.Serializer()},
        tags=["management.role.member"],
    )
    @view_audit_decorator(RoleMemberDeleteAuditProvider)
    def destroy(self, request, *args, **kwargs):
        role = self.get_object()

        serializer = ManagementGradeManagerMembersDeleteSLZ(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        members = list(set(serializer.validated_data["members"]))
        RoleUser.objects.delete_grade_manager_member(role.id, members)

        # 审计
        audit_context_setter(role=role, members=members)

        return Response({})
