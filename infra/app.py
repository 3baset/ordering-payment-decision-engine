#!/usr/bin/env python3
import aws_cdk as cdk
from oda_stack import OdaStack

app = cdk.App()

OdaStack(
    app, "OdaStack",
    description="ODA — event-driven ordering decisioning pipeline",
    env=cdk.Environment(
        account=app.node.try_get_context("account") or None,
        region=app.node.try_get_context("region") or "us-east-1",
    ),
)

app.synth()
