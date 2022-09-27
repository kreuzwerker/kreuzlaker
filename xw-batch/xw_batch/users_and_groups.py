"""
Create users and groups for our org
"""
import re
import typing

from aws_cdk import SecretValue, aws_iam
from constructs import Construct

# We use this as initial password which has to be changed on first login.
# TODO: use `secretsmanager.Secret.fromSecretAttributes` to reference a secret in Secrets Manager? Prob not worth it.
INITIAL_PASSWORD = "N0tV3ryS3cr3t!"

# Default policy: be able to change passwords
# Yes, you have to give the user a non-managed policy for that...
# https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_aws_my-sec-creds-self-manage-password-only.html
# https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_passwords_enable-user-change.html

POLICY_DOCUMENT_ALLOW_PASSWORD_CHANGES = aws_iam.PolicyDocument(
    statements=[
        aws_iam.PolicyStatement(
            sid="ViewAccountPasswordRequirements",
            effect=aws_iam.Effect.ALLOW,
            actions=["iam:GetAccountPasswordPolicy"],
            resources=["*"],
        ),
        aws_iam.PolicyStatement(
            sid="ChangeOwnPassword",
            effect=aws_iam.Effect.ALLOW,
            actions=["iam:GetUser", "iam:ChangePassword"],
            resources=["arn:aws:iam::*:user/${aws:username}"],
        ),
    ]
)


def _validate_user_name(user_name: str):
    """Raises if a name for a user or group is not according to AWS spec

    :param: user_name: the name which should conform to the AWS rules
    """

    # Spec according to error message:
    # userName [...] must contain only alphanumeric characters and/or the following: +=,.@_-
    if not re.match(r"^[a-z+=,.@_-]+$", user_name):
        raise RuntimeError(f"Bad user name: {user_name}; Only [a-z+=,.@_-]+ allowed")


def _validate_group_name(group_name: str):
    """Raises if a name for a group is not according to AWS spec

    :param: user_name: the name which should conform to the AWS rules
    """

    # Spec according to https://docs.aws.amazon.com/IAM/latest/UserGuide/id_groups_create.html
    if not re.match(r"^[A-Za-z0-9+=,.@_-]+$", group_name):
        raise RuntimeError(
            f"Bad group name: {group_name}; Only [A-Za-z0-9+=,.@_-]+ allowed"
        )


def _to_id(name: str) -> str:
    """Converts a name lower case with minus between words.

    :param: name: the name to be converted to a construct id
    :return: the id this name gets converted to
    """
    name = re.sub("(.)([A-Z][a-z]+)", r"\1-\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1-\2", name).lower()


class OrgUsersAndGroups(Construct):
    """A construct to create groups and users with some defaults

    Users are created with a default password and must change it on first login
    """

    def __init__(self, scope: Construct, id: str):
        super().__init__(scope, id)

        self.policy_allow_password_changes = aws_iam.ManagedPolicy(
            self,
            "policy-allow-password-changes",
            document=POLICY_DOCUMENT_ALLOW_PASSWORD_CHANGES,
            # Do not set to not have problems when deploying any changes to the policy. See best practises for cdk
            # managed_policy_name="AllowPasswordChanges",
            description="Allow password changed for users.",
        )

        # Users
        self.users: typing.Dict[str, aws_iam.User] = {}
        self.groups: typing.Dict[str, aws_iam.Group] = {}

    def add_org_group(self, group_name: str) -> aws_iam.Group:
        """
        Create an IAM group

        :param: group_name: The name if the group
        :return: group: the aws_iam.Group which got created
        """
        _validate_group_name(group_name)
        id_ = _to_id(group_name)
        if id_ in self.groups:
            raise RuntimeError(f"Group '{group_name}' (id={id_})  already exists.")

        group = aws_iam.Group(self, id=id_, group_name=group_name)
        self.groups[id_] = group
        return group

    def get_group(self, group_name: str) -> aws_iam.Group:
        """
        Return the already created Group for the name

        :param: group_name: the name of the group
        :return: the group if it was already created or raise error
        """
        key = _to_id(group_name)
        if key not in self.groups:
            raise KeyError(f"Group with name {group_name} (id={key}) does not exist.")
        return self.groups[key]

    def add_org_user(
        self,
        user_name: str,
        *,
        groups: typing.Union[str, typing.List[str]] = None,
    ) -> aws_iam.User:
        """Create an IAM user who must change their password immediately.

        :param: groups: The group(s) to which this user should belong
        :param: user_name: The name of the user
        :return: user: the aws_iam.User which got created
        """
        # Validate the users name
        _validate_user_name(user_name)
        id_ = _to_id(user_name)
        if id_ in self.users:
            raise RuntimeError(f"User '{user_name}' (id={id_}) already exists.")

        # make sure the groups exist
        if groups is None:
            resolved_groups = []
        elif isinstance(groups, str):
            resolved_groups = [self.get_group(groups)]
        else:
            resolved_groups = [self.get_group(group) for group in groups]

        # Create the user with some default config and policies
        user = aws_iam.User(
            scope=self,
            # Todo: Not sure what the requirements are and if this is already enough
            id=user_name.lower().replace(".", "-"),
            user_name=user_name,
            password=SecretValue.unsafe_plain_text(INITIAL_PASSWORD),
            password_reset_required=True,
        )

        user.add_managed_policy(self.policy_allow_password_changes)

        for group in resolved_groups:
            user.add_to_group(group)

        self.users[user_name] = user

        return user


# From here it's the actual group and user structure

# Pattern: add groups, then add users with group membership
# 1. Do not attach users to groups, but groups to users
#    (easier off boarding, just delete the add_org_user() call)
# 2. Do not attach policies here, only where you define the service
#    (keep everything service related together)
# TODO: have some though about structuring/naming groups to make them consistent


# constants for groups to make the editor do the hard work...
"""Debugging ability (like reading logs and all data)"""
GROUP_DATA_LAKE_DEBUGGING = "DataLakeDebugging"
"""Run athena queries against the data lake and publish these results in (personal) glue databases"""
GROUP_DATA_LAKE_ATHENA_USER = "DataLakeAthenaUser"


def create_org_groups(scope: Construct):
    """
    Create the OrgUsersAndGroups construct and add all groups

    :param: scope: The parent construct where this should be added to
    :return: the instantiated UsersAndGroups construct
    """
    uag = OrgUsersAndGroups(scope, "org-users-and-groups")
    # Groups

    uag.add_org_group(group_name=GROUP_DATA_LAKE_DEBUGGING)
    uag.add_org_group(group_name=GROUP_DATA_LAKE_ATHENA_USER)
    return uag


def add_users_on_dev(org_groups: OrgUsersAndGroups) -> None:
    """
    Create users which should be present on a dev environment

    :param: org_groups: The already created construct for groups and users
    """
    org_groups.add_org_user(
        "example.user",
        groups=[
            GROUP_DATA_LAKE_DEBUGGING,
            GROUP_DATA_LAKE_ATHENA_USER,
        ],
    )


def add_users_on_prod(org_groups: OrgUsersAndGroups) -> None:
    """
    Create users which should be present on the prod environment

    :param: org_groups: The already created construct for groups and users
    """
    org_groups.add_org_user("example.user", groups=[GROUP_DATA_LAKE_DEBUGGING])
