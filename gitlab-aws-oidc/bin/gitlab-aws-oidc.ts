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
    // See https://stackoverflow.com/a/69247499/1380673 for a way how to obtain this thumbprint
    // for some reason, the default one, if created without any thumbprint, was not the one from below
    thumbprints: [
        '933c6ddee95c9c41a40f9f50493d82be03ad87bf',
    ],
    env: {
        region: "eu-central-1",
    },
    tags: {
        project: projectName,
        repoLink: "https://gitlab.kreuzwerker.de/engineering/data-engineering/xw-data-toolkit",
    },
});