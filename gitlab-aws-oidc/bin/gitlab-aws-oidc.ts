#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import {GitlabAWSOIDCStack} from '../lib/gitlab-aws-oidc-stack';

const app = new cdk.App();


const projectName = "xw-batch-deployment";

new GitlabAWSOIDCStack(app, 'GitlabCICDIdentityStack', {
    projectName,
    // Allow pushes by repo and branch. * is allowed, but be careful
    // and make sure you include your full repositories name
    allowedRepoToPush: "engineering/data-engineering/xw-data-toolkit",
    allowedBranchesToPush: [
        "main",
        // For testing purpose, add your PR branch here!
        //"jan-create-deployment-pipeline",
    ],
    // The gitlab instance hostname excluding https:// and without a slash at the end!
    gitlabHost: "gitlab.kreuzwerker.de",
    env: {
        region: "eu-central-1",
    },
    tags: {
        project: projectName,
        repoLink: "https://gitlab.kreuzwerker.de/engineering/data-engineering/xw-data-toolkit",
    },
});