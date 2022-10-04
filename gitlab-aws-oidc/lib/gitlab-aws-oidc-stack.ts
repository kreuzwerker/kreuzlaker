import {Stack, StackProps} from "aws-cdk-lib";
import {Construct} from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as cdk from 'aws-cdk-lib';

export interface GitlabAWSOIDCStackProps extends StackProps {
    projectName: string;
    allowedRepoToPush: string;
    allowedBranchesToPush: string[];
    gitlabHost: string;
    thumbprints: string[];
}

export class GitlabAWSOIDCStack extends Stack {
    public gitlabPipelineRole: iam.Role;

    constructor(scope: Construct, id: string, props: GitlabAWSOIDCStackProps) {
        super(scope, id, props);
        const {projectName, allowedRepoToPush, allowedBranchesToPush, gitlabHost, thumbprints} = props;

        const gitlabOIDCProvider = new iam.OpenIdConnectProvider(
            this,
            "GitlabPipeline",
            {
                // See https://docs.gitlab.com/ee/ci/cloud_services/aws/
                url: `https://${gitlabHost}`,
                clientIds: [`https://${gitlabHost}`],
                thumbprints: thumbprints,
            }
        );

        const allowedBranchPatternToPush: string[] = []

        // See https://docs.gitlab.com/ee/ci/cloud_services/aws/ for how the pattern needs to look like
        for (let branch of allowedBranchesToPush) {
            allowedBranchPatternToPush.push(`project_path:${allowedRepoToPush}:ref_type:branch:ref:${branch}`)
        }

        const stringEqualsCondition: {
            [key: string]: string[]
        } = {}
        stringEqualsCondition[`${gitlabHost}:sub`] = allowedBranchPatternToPush

        this.gitlabPipelineRole = new iam.Role(this, "GitlabPipelineRole", {
            // Trust policy
            assumedBy: new iam.WebIdentityPrincipal(
                gitlabOIDCProvider.openIdConnectProviderArn,
                {
                    StringEquals: stringEqualsCondition,
                }
            ),
            roleName: `gitlab-oidc-${projectName}`,
            description: `Role to assume from gitlab pipeline of ${projectName}`,
        });

        // Configure the role to allow whatever the CICD pipeline should be able to do.
        // In this case, allow this role to assume the cdk roles, to run cdk diff/deploy
        this.gitlabPipelineRole.addToPolicy(iam.PolicyStatement.fromJson({
                    "Effect": "Allow",
                    "Action": ["sts:AssumeRole"],
                    "Resource": [
                        "arn:aws:iam::*:role/cdk-*-lookup-role-*",
                        "arn:aws:iam::*:role/cdk-*-image-publishing-role-*",
                        "arn:aws:iam::*:role/cdk-*-file-publishing-role-*",
                        "arn:aws:iam::*:role/cdk-*-deploy-role-*",
                        // this has full administrator access!
                        // "arn:aws:iam::*:role/cdk-*-cfn-exec-role-*",
                    ]
                }
            )
        )

        // for pushing a docker image to the corresponding ECR repo
        // https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push.html
        this.gitlabPipelineRole.addToPolicy(iam.PolicyStatement.fromJson({
                    "Effect": "Allow",
                    "Action": [
                        "ecr:CompleteLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:InitiateLayerUpload",
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:PutImage"
                    ],
                    "Resource": `arn:aws:ecr:${this.region}:${this.account}:repository/dbt-run`
                }
            )
        );
        this.gitlabPipelineRole.addToPolicy(iam.PolicyStatement.fromJson({
                    "Effect": "Allow",
                    "Action": "ecr:GetAuthorizationToken",
                    "Resource": "*"
                }
            )
        )

        // output the role arn for easier copy and paste into the gitlab pipeline
        new cdk.CfnOutput(this, 'PipelineRoleArn', {
            value: this.gitlabPipelineRole.roleArn,
            description: `The arn of the role which can be assumed from a gitlab pipeline on https://${gitlabHost} within the following repos+branches: ${allowedBranchPatternToPush}`,
            exportName: 'PipelineRoleArn',
        });
    }
}
