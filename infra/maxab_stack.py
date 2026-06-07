import json
import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    SecretValue,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudwatch as cw,
    aws_secretsmanager as sm,
)
from constructs import Construct

LAMBDA_ROOT = os.path.join(os.path.dirname(__file__), "..", "lambdas")


class MaxabStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Tables ──────────────────────────────────────────────────────────
        orders_table = dynamodb.Table(
            self, "OrdersTable",
            table_name="maxab-orders",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.DESTROY,
        )
        orders_table.add_global_secondary_index(
            index_name="customer_id-index",
            partition_key=dynamodb.Attribute(name="customer_id", type=dynamodb.AttributeType.STRING),
        )

        action_log_table = dynamodb.Table(
            self, "ActionLogTable",
            table_name="maxab-action-log",
            partition_key=dynamodb.Attribute(name="action_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── Shared Lambda environment ────────────────────────────────────────
        common_env = {
            "ORDERS_TABLE": orders_table.table_name,
            "ACTION_LOG_TABLE": action_log_table.table_name,
            "LOG_LEVEL": "INFO",
        }

        # ── Decision Lambda ──────────────────────────────────────────────────
        decision_log_group = logs.LogGroup(
            self, "DecisionLogGroup",
            log_group_name="/aws/lambda/maxab-decision",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        decision_fn = lambda_.Function(
            self, "DecisionLambda",
            function_name="maxab-decision",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(LAMBDA_ROOT, "decision")),
            environment=common_env,
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=decision_log_group,
            tracing=lambda_.Tracing.ACTIVE,
        )
        orders_table.grant_read_write_data(decision_fn)

        # Trigger: INSERT events on orders table → Decision Lambda
        decision_fn.add_event_source(
            event_sources.DynamoEventSource(
                orders_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                bisect_batch_on_error=True,
                retry_attempts=2,
                filters=[
                    lambda_.FilterCriteria.filter({
                        "eventName": lambda_.FilterRule.is_equal("INSERT"),
                    })
                ],
            )
        )

        # ── Action Lambda ────────────────────────────────────────────────────
        action_log_group = logs.LogGroup(
            self, "ActionLogGroup",
            log_group_name="/aws/lambda/maxab-action",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        action_fn = lambda_.Function(
            self, "ActionLambda",
            function_name="maxab-action",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(LAMBDA_ROOT, "action")),
            environment=common_env,
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=action_log_group,
            tracing=lambda_.Tracing.ACTIVE,
        )
        orders_table.grant_read_write_data(action_fn)
        action_log_table.grant_write_data(action_fn)

        # Trigger: MODIFY events where decision EXISTS
        # Note: AWS DynamoDB Streams FilterCriteria has a known quirk where combining
        # {exists:true} and {exists:false} on sibling keys in NewImage silently drops
        # all records. Idempotency is handled in handler code instead:
        #   - Lambda checks order.get("post_decision_action") and skips if already set
        #   - UpdateItem uses ConditionExpression="attribute_not_exists(post_decision_action)"
        action_fn.add_event_source(
            event_sources.DynamoEventSource(
                orders_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                bisect_batch_on_error=True,
                retry_attempts=2,
                filters=[
                    lambda_.FilterCriteria.filter({
                        "eventName": lambda_.FilterRule.is_equal("MODIFY"),
                        "dynamodb": {
                            "NewImage": {
                                "decision": lambda_.FilterRule.exists(),
                            }
                        },
                    })
                ],
            )
        )

        # ── IAM Evaluator User ───────────────────────────────────────────────
        evaluator = iam.User(self, "EvaluatorUser", user_name="maxab-evaluator")
        for policy_name in [
            "AmazonDynamoDBReadOnlyAccess",
            "AWSLambda_ReadOnlyAccess",
            "CloudWatchReadOnlyAccess",
            "AmazonS3ReadOnlyAccess",
        ]:
            evaluator.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(policy_name)
            )

        evaluator_key = iam.CfnAccessKey(
            self, "EvaluatorAccessKey",
            user_name=evaluator.user_name,
        )

        sm.Secret(
            self, "EvaluatorCredentials",
            secret_name="maxab-evaluator-credentials",
            secret_string_value=SecretValue.unsafe_plain_text(
                json.dumps({
                    "access_key_id": evaluator_key.ref,
                    "secret_access_key": evaluator_key.attr_secret_access_key,
                    "region": self.region,
                    "note": "Read-only evaluator access for MaxAB case study review",
                })
            ),
        )

        # ── CloudWatch Dashboard ─────────────────────────────────────────────
        dashboard = cw.Dashboard(self, "MaxabDashboard", dashboard_name="MaxAB-Pipeline")

        decision_errors = cw.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": decision_fn.function_name},
            period=Duration.minutes(5),
            statistic="Sum",
        )
        action_errors = cw.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": action_fn.function_name},
            period=Duration.minutes(5),
            statistic="Sum",
        )
        decision_invocations = cw.Metric(
            namespace="AWS/Lambda",
            metric_name="Invocations",
            dimensions_map={"FunctionName": decision_fn.function_name},
            period=Duration.minutes(5),
            statistic="Sum",
        )
        action_invocations = cw.Metric(
            namespace="AWS/Lambda",
            metric_name="Invocations",
            dimensions_map={"FunctionName": action_fn.function_name},
            period=Duration.minutes(5),
            statistic="Sum",
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Lambda Invocations",
                left=[decision_invocations, action_invocations],
                width=12,
            ),
            cw.GraphWidget(
                title="Lambda Errors",
                left=[decision_errors, action_errors],
                width=12,
            ),
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(self, "OrdersTableName", value=orders_table.table_name)
        CfnOutput(self, "ActionLogTableName", value=action_log_table.table_name)
        CfnOutput(self, "DecisionLambdaArn", value=decision_fn.function_arn)
        CfnOutput(self, "ActionLambdaArn", value=action_fn.function_arn)
        CfnOutput(self, "EvaluatorSecretArn",
                  value=f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:maxab-evaluator-credentials")
        CfnOutput(self, "DashboardUrl",
                  value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home#dashboards:name=MaxAB-Pipeline")
