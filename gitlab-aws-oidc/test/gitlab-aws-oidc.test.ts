import * as cdk from "aws-cdk-lib";
import {Template, Match} from "aws-cdk-lib/assertions";
import {GitlabAWSOIDCStack} from "../lib/gitlab-aws-oidc-stack";

describe("test cdk stack", () => {
    const app = new cdk.App();
    const projectName = "whatever";
    const allowedRepoToPush = "department-name/team-name/repo-name"
    const allowedBranchesToPush: string[] = [
        "main",
        "develop",
    ];

    const stackWithTwoBranchPattern = new GitlabAWSOIDCStack(app, "MyTestStackWithTwoBranchPattern", {
        projectName,
        allowedRepoToPush,
        allowedBranchesToPush: [
            "main",
            "develop",
        ],
        gitlabHost: "gitlab.example.com",
    });

    const stackWithSingleBranchPattern = new GitlabAWSOIDCStack(
        app,
        "MyTestStackWithOnlyOneBranchPattern",
        {
            projectName,
            allowedRepoToPush,
            allowedBranchesToPush: ["main"],
            gitlabHost: "gitlab.example.com",
        }
    );

    test("OIDC Provider created", () => {
        const template = Template.fromStack(stackWithTwoBranchPattern);

        template.hasResourceProperties("Custom::AWSCDKOpenIdConnectProvider", {
            Url: "https://gitlab.example.com",
            ClientIDList: ["https://gitlab.example.com"],
        });
    });

    test("IAM role with multiple branch patterns exists", () => {
        const template = Template.fromStack(stackWithTwoBranchPattern);

        template.hasResourceProperties("AWS::IAM::Role", {
            AssumeRolePolicyDocument: {
                Statement: [
                    {
                        Action: "sts:AssumeRoleWithWebIdentity",
                        Condition: {
                            StringEquals: {
                                "gitlab.example.com:sub": [
                                    "project_path:department-name/team-name/repo-name:ref_type:branch:ref:main",
                                    "project_path:department-name/team-name/repo-name:ref_type:branch:ref:develop",
                                ],
                            },
                        },
                        Effect: "Allow",
                    },
                ],
            },
        });
    });

    test("IAM role with single branch pattern exists", () => {
        const template = Template.fromStack(stackWithSingleBranchPattern);

        template.hasResourceProperties("AWS::IAM::Role", {
            AssumeRolePolicyDocument: {
                Statement: [
                    {
                        Action: "sts:AssumeRoleWithWebIdentity",
                        Condition: {
                            StringEquals: {
                                "gitlab.example.com:sub": [
                                    "project_path:department-name/team-name/repo-name:ref_type:branch:ref:main",
                                ],
                            },
                        },
                        Effect: "Allow",
                    },
                ],
            },
        });
    });

    test("IAM Policy for OIDC role allows required actions", () => {
        const template = Template.fromStack(stackWithSingleBranchPattern);
        const pipelineRole = stackWithSingleBranchPattern.gitlabPipelineRole
        const resolvedGitlabPipelineRoleName = stackWithSingleBranchPattern.resolve(pipelineRole.roleName)

        template.hasResourceProperties("AWS::IAM::Policy", {
            "Roles": Match.arrayWith(resolvedGitlabPipelineRoleName),
            // change the next to what your gitlab deployment pipeline needs
            "PolicyDocument": {
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Effect": "Allow",
                        "Resource": [
                            "arn:aws:iam::*:role/cdk-*-lookup-role-*",
                            "arn:aws:iam::*:role/cdk-*-image-publishing-role-*",
                            "arn:aws:iam::*:role/cdk-*-file-publishing-role-*",
                            "arn:aws:iam::*:role/cdk-*-deploy-role-*",
                        ]
                    }
                ],
            },
        });
    });

    test('Snapshot of whole stack stays stable', () => {
        // This needs adjustments for almost every change to the stack, so it's mostly good to test refactorings
        // and check if the actual diff makes sense
        // to update the snapshot: run `npm test -- -u`
        const template = Template.fromStack(stackWithSingleBranchPattern);
        expect(template.toJSON()).toMatchSnapshot();
    });
});