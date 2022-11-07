from aws_cdk.aws_ec2 import (
    Vpc,
    SubnetType,
    InterfaceVpcEndpointAwsService,
    GatewayVpcEndpointAwsService,
    GatewayVpcEndpointOptions,
)
from constructs import Construct


class XwVpc(Construct):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.vpc = Vpc(
            self,
            id,
            max_azs=1,
            nat_gateways=0,
            gateway_endpoints={"S3": GatewayVpcEndpointOptions(service=GatewayVpcEndpointAwsService.S3)},
            subnet_configuration=[
                {
                    "cidrMask": 24,
                    "name": "ingress",
                    "subnetType": SubnetType.PUBLIC,
                },
                {
                    "cidrMask": 24,
                    "name": "application",
                    "subnetType": SubnetType.PRIVATE_ISOLATED,
                },
                {
                    "cidrMask": 28,
                    "name": "egress",
                    "subnetType": SubnetType.PRIVATE_WITH_EGRESS,
                },
            ],
        )

        self.vpc.add_interface_endpoint(
            "AthenaEndpoint",
            service=InterfaceVpcEndpointAwsService.ATHENA,
        )

        self.vpc.add_interface_endpoint(
            "EcrEndpoint",
            service=InterfaceVpcEndpointAwsService.ECR,
        )

        self.vpc.add_interface_endpoint(
            "CloudWatchEndpoint",
            service=InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        )

        self.vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=InterfaceVpcEndpointAwsService.ECR_DOCKER,
        )

    def get_vpc(self):
        return self.vpc
