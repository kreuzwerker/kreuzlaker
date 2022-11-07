from copyreg import constructor
from aws_cdk import aws_ecs_patterns as ecs
from aws_cdk.aws_ecs import ContainerImage
from aws_cdk.aws_ec2 import Vpc
from constructs import Construct


class Superset(Construct):
    def __init__(self, scope: Construct, id: str, vpc: Vpc, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        ecs.ApplicationLoadBalancedFargateService(
            self,
            "SuperSetFargateService",
            vpc=vpc,
            task_image_options=ecs.ApplicationLoadBalancedTaskImageOptions(
                image=ContainerImage.from_registry("apache/superset:latest"),
                container_name="Superset",
            ),
        )
