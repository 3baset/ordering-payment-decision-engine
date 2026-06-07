#!/usr/bin/env python3
import aws_cdk as cdk
from maxab_stack import MaxabStack

app = cdk.App()

MaxabStack(
    app, "MaxabStack",
    description="MaxAB case study — event-driven ordering decisioning pipeline",
    env=cdk.Environment(
        account=app.node.try_get_context("account") or None,
        region=app.node.try_get_context("region") or "us-east-1",
    ),
)

app.synth()
