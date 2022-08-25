import aws_cdk
import pytest
from aws_cdk.assertions import Match, Template

from xw_batch.users_and_groups import (
    GROUP_DATA_LAKE_DEBUGGING,
    OrgUsersAndGroups,
    add_users_on_dev,
)


class _UaGStack(aws_cdk.Stack):
    def __init__(self):
        super().__init__()
        self.ouag = OrgUsersAndGroups(self, "OrgUsersAndGroups")
        self.ouag.add_org_group(GROUP_DATA_LAKE_DEBUGGING)
        add_users_on_dev(self.ouag)


@pytest.fixture(name="ouag_stack", scope="module")
def ouag_stack_fixture() -> _UaGStack:
    return _UaGStack()


@pytest.fixture(name="ouag_template", scope="module")
def ouag_template_fixture(ouag_stack: _UaGStack) -> Template:
    stack = ouag_stack
    template = Template.from_stack(stack)
    return template


def test_org_users_and_groups_structure(
    ouag_template: Template,
    ouag_stack: _UaGStack,
):
    ouag_template.has_resource_properties(
        "AWS::IAM::Group",
        {
            "GroupName": GROUP_DATA_LAKE_DEBUGGING,
        },
    )
    resolved_wanted_policy_arn = ouag_stack.resolve(
        ouag_stack.ouag.policy_allow_password_changes.managed_policy_arn
    )
    ouag_template.has_resource_properties(
        "AWS::IAM::User",
        {
            "LoginProfile": {
                "Password": Match.any_value(),
                "PasswordResetRequired": True,
            },
            "ManagedPolicyArns": Match.array_with([resolved_wanted_policy_arn]),
            "UserName": "example.user",
        },
    )

    ouag_template.has_resource_properties(
        "AWS::IAM::ManagedPolicy",
        {
            "ManagedPolicyName": "AllowPasswordChanges",
            "PolicyDocument": {
                "Statement": [
                    {
                        "Action": "iam:GetAccountPasswordPolicy",
                        "Effect": "Allow",
                        "Resource": "*",
                        "Sid": "ViewAccountPasswordRequirements",
                    },
                    {
                        "Action": ["iam:GetUser", "iam:ChangePassword"],
                        "Effect": "Allow",
                        "Resource": "arn:aws:iam::*:user/${aws:username}",
                        "Sid": "ChangeOwnPassword",
                    },
                ],
            },
        },
    )


def test_org_users_and_groups_snapshot(snapshot, ouag_template):
    assert ouag_template.to_json() == snapshot
